"""
GrabOn Merchant Underwriting Agent

Two modes:
  - GrabCredit: working capital credit limit, interest rate, tenure options
  - GrabInsurance: coverage amount, premium quote, policy type

Each decision includes a 3-5 sentence rationale referencing specific data points.
Uses Claude API for narrative generation, with a deterministic fallback.

Architecture:
  1. Score merchant (scoring_engine)
  2. Generate offer parameters (deterministic — tier-based formulas)
  3. Generate rationale narrative (Claude API or fallback)
  4. Package into UnderwritingDecision
"""

import os
import json
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
from datetime import datetime, timezone
from typing import Optional

from merchant_profiles import MERCHANT_PROFILES, CATEGORY_BENCHMARKS, compute_derived_metrics


# ── Offer Generation (deterministic) ──────────────────────────────────────

# Import scoring from our validated engine
from test_scoring import compute_risk_score


def generate_credit_offer(profile: dict, metrics: dict, risk: dict) -> Optional[dict]:
    """Generate GrabCredit working capital offer based on risk tier."""
    if risk["tier"] == "Rejected":
        return None

    avg_gmv = metrics["avg_monthly_gmv"]

    tier_config = {
        "Tier 1": {"multiplier": 3.0, "rate": 12.5, "rate_label": "Tier 1 — Preferential Rate (Poonawalla Prime)", "tenures": [6, 12, 18, 24]},
        "Tier 2": {"multiplier": 2.0, "rate": 16.0, "rate_label": "Tier 2 — Standard Rate", "tenures": [6, 12, 18]},
        "Tier 3": {"multiplier": 1.0, "rate": 21.0, "rate_label": "Tier 3 — Risk-Adjusted Rate", "tenures": [6, 12]},
    }

    config = tier_config[risk["tier"]]
    credit_limit = round(avg_gmv * config["multiplier"], 1)
    rate = config["rate"]
    tenures = config["tenures"]

    # EMI calculation for mid tenure
    mid_tenure = tenures[len(tenures) // 2]
    monthly_rate = rate / 100 / 12
    principal = credit_limit * 100000  # convert lakhs to rupees
    emi = (principal * monthly_rate * (1 + monthly_rate) ** mid_tenure) / \
          ((1 + monthly_rate) ** mid_tenure - 1)

    return {
        "credit_limit_lakhs": credit_limit,
        "interest_rate_percent": rate,
        "interest_rate_tier": config["rate_label"],
        "tenure_options_months": tenures,
        "monthly_emi_estimate": round(emi, 0),
        "emi_tenure_months": mid_tenure,
    }


def generate_insurance_offer(profile: dict, metrics: dict, risk: dict) -> Optional[dict]:
    """Generate GrabInsurance business interruption offer."""
    if risk["tier"] == "Rejected":
        return None

    coverage_config = {
        "Tier 1": {"months": 3, "premium_pct": 0.015},
        "Tier 2": {"months": 2, "premium_pct": 0.025},
        "Tier 3": {"months": 1, "premium_pct": 0.040},
    }

    config = coverage_config[risk["tier"]]
    coverage = round(metrics["avg_monthly_gmv"] * config["months"], 1)
    annual_premium = round(coverage * 100000 * config["premium_pct"], 0)

    # Policy type based on category
    policy_map = {
        "Fashion": "Inventory & Stock Protection",
        "Food": "Business Interruption Cover",
        "Travel": "Revenue Protection Plan",
        "Electronics": "Inventory & Stock Protection",
        "Health": "Business Interruption Cover",
        "Beauty": "Inventory & Stock Protection",
        "Gaming": "Revenue Protection Plan",
    }
    policy_type = policy_map.get(profile["category"], "Business Interruption Cover")

    total_gmv = metrics["total_gmv_12m"]
    premium_pct_of_gmv = round(annual_premium / (total_gmv * 100000) * 100, 3) if total_gmv > 0 else 0

    return {
        "policy_type": policy_type,
        "coverage_amount_lakhs": coverage,
        "coverage_months": config["months"],
        "annual_premium_inr": annual_premium,
        "premium_as_pct_of_gmv": premium_pct_of_gmv,
        "coverage_details": (
            f"{config['months']}-month revenue coverage at ₹{coverage}L. "
            f"Covers business interruption due to supply chain disruption, "
            f"platform downtime, or force majeure events. "
            f"Claim settlement within 15 working days."
        ),
    }


# ── Claude Rationale Generation ───────────────────────────────────────────

RATIONALE_SYSTEM_PROMPT = """You are an underwriting analyst at GrabOn, India's #1 coupon platform.
You produce concise, data-backed rationale narratives for merchant credit and insurance decisions.

Rules:
- Write exactly 3-5 sentences.
- Reference SPECIFIC numbers from the merchant data (GMV figures, percentages, rates).
- Compare metrics against category benchmarks where relevant.
- For approvals: explain WHY the merchant qualifies and what strengths drove the decision.
- For rejections: explain clearly what disqualified them and what would need to change.
- For Tier 3 (manual review): acknowledge the risk factors while noting any positives.
- Never use generic phrases like "based on our analysis" — be specific.
- Use ₹ symbol for Indian rupees. Use "L" for lakhs.
- Tone: professional, direct, like a senior credit analyst writing for a lending committee."""

def build_rationale_prompt(profile: dict, metrics: dict, risk: dict, mode: str,
                           credit_offer: Optional[dict], insurance_offer: Optional[dict]) -> str:
    """Build the user prompt for Claude rationale generation."""

    benchmark = CATEGORY_BENCHMARKS.get(profile["category"], {})

    growth_str = f"{metrics['gmv_growth_rate']:.1%}" if metrics['gmv_growth_rate'] is not None else "N/A (insufficient data)"
    cv_str = f"{metrics['gmv_cv']:.3f}" if metrics['gmv_cv'] is not None else "N/A"

    prompt = f"""Generate an underwriting rationale for this merchant.

MERCHANT PROFILE:
- Name: {profile['merchant_name']}
- Category: {profile['category']}
- Monthly GMV (12 months, oldest→newest): {profile['monthly_gmv_12m']}
- Average Monthly GMV: ₹{metrics['avg_monthly_gmv']}L
- Total Annual GMV: ₹{metrics['total_gmv_12m']}L
- H2 vs H1 Growth Rate: {growth_str}
- GMV Coefficient of Variation: {cv_str}
- Active Months on Platform: {metrics['num_active_months']}
- Coupon Redemption Rate: {profile['coupon_redemption_rate']:.0%}
- Unique Customers: {profile['unique_customer_count']:,}
- Customer Return Rate: {profile['customer_return_rate']:.0%}
- Average Order Value: ₹{profile['avg_order_value']:,.0f}
- Seasonality Index: {profile['seasonality_index']:.2f}
- Deal Exclusivity Rate: {profile['deal_exclusivity_rate']:.0%}
- Return & Refund Rate: {profile['return_and_refund_rate']:.1%}

CATEGORY BENCHMARKS ({profile['category']}):
- Avg Return/Refund Rate: {benchmark.get('avg_return_rate', 'N/A')}
- Avg Redemption Rate: {benchmark.get('avg_redemption_rate', 'N/A')}
- Avg Customer Return Rate: {benchmark.get('avg_customer_return_rate', 'N/A')}
- Avg Monthly GMV: ₹{benchmark.get('avg_monthly_gmv_lakhs', 'N/A')}L

RISK ASSESSMENT:
- Weighted Score: {risk['weighted_total']}/100
- Risk Tier: {risk['tier']}
- Flags: {', '.join(risk['flags']) if risk['flags'] else 'None'}
- Score Breakdown: {json.dumps(risk['scores'], indent=2)}

MODE: {mode}
"""

    if mode == "GrabCredit" and credit_offer:
        prompt += f"""
CREDIT OFFER GENERATED:
- Credit Limit: ₹{credit_offer['credit_limit_lakhs']}L
- Interest Rate: {credit_offer['interest_rate_percent']}% p.a. ({credit_offer['interest_rate_tier']})
- Tenure Options: {credit_offer['tenure_options_months']} months
- Estimated EMI: ₹{credit_offer['monthly_emi_estimate']:,.0f}/month for {credit_offer['emi_tenure_months']} months

Write a 3-5 sentence rationale explaining why this credit limit and rate tier were assigned.
"""
    elif mode == "GrabInsurance" and insurance_offer:
        prompt += f"""
INSURANCE OFFER GENERATED:
- Policy Type: {insurance_offer['policy_type']}
- Coverage: ₹{insurance_offer['coverage_amount_lakhs']}L ({insurance_offer['coverage_months']} months revenue)
- Annual Premium: ₹{insurance_offer['annual_premium_inr']:,.0f} ({insurance_offer['premium_as_pct_of_gmv']:.3f}% of GMV)

Write a 3-5 sentence rationale explaining why this coverage level and policy type were recommended.
"""
    elif risk["tier"] == "Rejected":
        prompt += """
DECISION: REJECTED

Write a 3-5 sentence rationale explaining why this merchant was rejected.
Be specific about which data points caused the rejection and what the merchant
would need to demonstrate to become eligible in the future.
"""

    return prompt


def build_key_factors_prompt(profile: dict, metrics: dict, risk: dict, mode: str) -> str:
    """Build prompt for key factor extraction (2-5 bullet points)."""
    return f"""Based on this merchant's underwriting assessment, list 2-5 key decision factors as short phrases.

Merchant: {profile['merchant_name']} ({profile['category']})
Risk Tier: {risk['tier']} (Score: {risk['weighted_total']})
Flags: {', '.join(risk['flags']) if risk['flags'] else 'None'}
Mode: {mode}

Key metrics:
- GMV Growth: {f"{metrics['gmv_growth_rate']:.1%}" if metrics['gmv_growth_rate'] is not None else "insufficient data"}
- Refund Rate: {profile['return_and_refund_rate']:.1%} (category avg: {CATEGORY_BENCHMARKS.get(profile['category'], {}).get('avg_return_rate', 'N/A')})
- Customer Return Rate: {profile['customer_return_rate']:.0%}
- Active Months: {metrics['num_active_months']}
- Avg Monthly GMV: ₹{metrics['avg_monthly_gmv']}L

Respond with ONLY a JSON array of strings, no other text. Example:
["Strong YoY GMV growth of 29.6%", "Refund rate 3.1% — well below category average of 8%"]"""


async def call_claude_api(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Claude API for rationale generation. Returns None on failure."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not HAS_HTTPX:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data["content"][0]["text"]
    except Exception as e:
        print(f"Claude API error: {e}")

    return None


# ── Deterministic Fallback Rationale ──────────────────────────────────────

def generate_fallback_rationale(profile: dict, metrics: dict, risk: dict, mode: str,
                                 credit_offer: Optional[dict], insurance_offer: Optional[dict]) -> str:
    """
    Deterministic rationale when Claude API is unavailable.
    Still references specific data points — not generic boilerplate.
    """
    name = profile["merchant_name"]
    cat = profile["category"]
    tier = risk["tier"]
    bench = CATEGORY_BENCHMARKS.get(cat, {})
    growth = metrics["gmv_growth_rate"]
    growth_str = f"{growth:.1%}" if growth is not None else "insufficient data to calculate"
    refund = profile["return_and_refund_rate"]
    bench_refund = bench.get("avg_return_rate", 0.05)
    active = metrics["num_active_months"]

    if tier == "Rejected":
        if metrics["num_active_months"] < 6:
            return (
                f"{name} has only {active} months of transaction history on the GrabOn platform, "
                f"which falls below our minimum requirement of 6 months for underwriting eligibility. "
                f"With just {profile['unique_customer_count']:,} unique customers and ₹{metrics['avg_monthly_gmv']}L average monthly GMV, "
                f"the data volume is insufficient to establish reliable creditworthiness patterns. "
                f"We recommend reassessing after {name} completes at least 6 months of active transactions "
                f"with a minimum of 3,000 unique customers."
            )
        else:
            return (
                f"{name} shows a significant GMV decline of {growth_str} (H2 vs H1), "
                f"dropping from ₹{sum(profile['monthly_gmv_12m'][:6])/6:.1f}L to ₹{sum(profile['monthly_gmv_12m'][6:])/6:.1f}L monthly average. "
                f"The return and refund rate of {refund:.1%} is {refund/bench_refund:.1f}x the {cat} category average of {bench_refund:.0%}, "
                f"indicating serious operational or quality issues. "
                f"Combined with a customer return rate of just {profile['customer_return_rate']:.0%} "
                f"and coupon redemption rate of {profile['coupon_redemption_rate']:.0%}, "
                f"the risk profile does not meet minimum underwriting thresholds for either GrabCredit or GrabInsurance."
            )

    if tier == "Tier 3":
        return (
            f"{name} presents a mixed risk profile with a weighted score of {risk['weighted_total']}/100. "
            f"While the {cat} category and ₹{metrics['avg_monthly_gmv']}L average monthly GMV show market presence, "
            f"concerns include a refund rate of {refund:.1%} "
            f"({'above' if refund > bench_refund else 'near'} the category average of {bench_refund:.0%}) "
            f"and a customer return rate of {profile['customer_return_rate']:.0%}. "
            f"{'GMV volatility suggests inconsistent revenue patterns. ' if risk.get('flags') and 'VOLATILE' in risk['flags'] else ''}"
            f"This merchant is flagged for manual review before any offer can be extended."
        )

    # Tier 1 or Tier 2 — approval
    if mode == "GrabCredit" and credit_offer:
        return (
            f"{name} qualifies for a ₹{credit_offer['credit_limit_lakhs']}L working capital line at "
            f"{credit_offer['interest_rate_percent']}% p.a. under {credit_offer['interest_rate_tier']}. "
            f"This is supported by {growth_str} GMV growth over the past 12 months, "
            f"with average monthly GMV of ₹{metrics['avg_monthly_gmv']}L across {profile['unique_customer_count']:,} unique customers. "
            f"The refund rate of {refund:.1%} is {'well below' if refund < bench_refund * 0.7 else 'below'} "
            f"the {cat} category benchmark of {bench_refund:.0%}, indicating strong operational quality. "
            f"A customer return rate of {profile['customer_return_rate']:.0%} "
            f"and coupon redemption rate of {profile['coupon_redemption_rate']:.0%} "
            f"confirm sustained demand and platform engagement."
        )
    elif mode == "GrabInsurance" and insurance_offer:
        return (
            f"{name} is recommended for {insurance_offer['policy_type']} with "
            f"₹{insurance_offer['coverage_amount_lakhs']}L coverage ({insurance_offer['coverage_months']}-month revenue equivalent) "
            f"at an annual premium of ₹{insurance_offer['annual_premium_inr']:,.0f}. "
            f"The coverage level reflects {metrics['avg_monthly_gmv']}L average monthly GMV "
            f"and a {growth_str} growth trajectory, ensuring the policy keeps pace with business scale. "
            f"With a refund rate of {refund:.1%} against the {cat} average of {bench_refund:.0%} "
            f"and {profile['unique_customer_count']:,} unique customers, "
            f"the operational risk profile supports favorable premium pricing at "
            f"{insurance_offer['premium_as_pct_of_gmv']:.3f}% of annual GMV."
        )

    return f"{name} assessed at {tier} with score {risk['weighted_total']}/100."


def generate_fallback_key_factors(profile: dict, metrics: dict, risk: dict) -> list[str]:
    """Deterministic key factors extraction."""
    factors = []
    bench = CATEGORY_BENCHMARKS.get(profile["category"], {})

    # Growth
    if metrics["gmv_growth_rate"] is not None:
        g = metrics["gmv_growth_rate"]
        if g > 0.15:
            factors.append(f"Strong GMV growth of {g:.1%} (H2 vs H1)")
        elif g > 0:
            factors.append(f"Moderate GMV growth of {g:.1%}")
        elif g > -0.15:
            factors.append(f"GMV declining at {g:.1%} — needs monitoring")
        else:
            factors.append(f"Severe GMV decline of {g:.1%} — critical risk")

    # Refund rate vs benchmark
    bench_refund = bench.get("avg_return_rate", 0.05)
    refund = profile["return_and_refund_rate"]
    if refund < bench_refund * 0.6:
        factors.append(f"Refund rate {refund:.1%} — well below {profile['category']} avg of {bench_refund:.0%}")
    elif refund <= bench_refund:
        factors.append(f"Refund rate {refund:.1%} — within {profile['category']} benchmark")
    else:
        factors.append(f"Refund rate {refund:.1%} — exceeds {profile['category']} avg of {bench_refund:.0%}")

    # Customer loyalty
    if profile["customer_return_rate"] >= 0.65:
        factors.append(f"High customer loyalty at {profile['customer_return_rate']:.0%} repeat rate")
    elif profile["customer_return_rate"] < 0.35:
        factors.append(f"Low repeat rate of {profile['customer_return_rate']:.0%} — weak customer retention")

    # Data sufficiency
    if metrics["num_active_months"] < 6:
        factors.append(f"Only {metrics['num_active_months']} months of data — below 6-month minimum")

    # Volatility
    if risk["flags"] and "VOLATILE" in risk["flags"]:
        factors.append(f"High GMV volatility (CV: {metrics['gmv_cv']:.3f})")

    # Platform commitment
    if profile["deal_exclusivity_rate"] >= 0.45:
        factors.append(f"Strong GrabOn commitment — {profile['deal_exclusivity_rate']:.0%} deal exclusivity")

    return factors[:5]  # cap at 5


# ── Main Underwriting Function ────────────────────────────────────────────

async def run_underwriting(
    profile: dict,
    mode: str = "GrabCredit",
    use_claude: bool = True,
) -> dict:
    """
    Run the full underwriting pipeline for a merchant.

    Args:
        profile: merchant profile dict
        mode: "GrabCredit" or "GrabInsurance"
        use_claude: whether to attempt Claude API for rationale (falls back if unavailable)

    Returns:
        Complete underwriting decision dict
    """
    # Step 1: Compute risk score
    risk = compute_risk_score(profile)
    metrics = compute_derived_metrics(profile)

    # Step 2: Generate offer (deterministic)
    credit_offer = None
    insurance_offer = None

    if mode == "GrabCredit":
        credit_offer = generate_credit_offer(profile, metrics, risk)
    elif mode == "GrabInsurance":
        insurance_offer = generate_insurance_offer(profile, metrics, risk)

    # Step 3: Generate rationale (Claude API with fallback)
    rationale = None
    key_factors = None

    if use_claude:
        rationale_prompt = build_rationale_prompt(profile, metrics, risk, mode, credit_offer, insurance_offer)
        rationale = await call_claude_api(RATIONALE_SYSTEM_PROMPT, rationale_prompt)

        if rationale:
            factors_prompt = build_key_factors_prompt(profile, metrics, risk, mode)
            factors_raw = await call_claude_api(
                "You output only valid JSON arrays. No markdown, no explanation.",
                factors_prompt,
            )
            if factors_raw:
                try:
                    key_factors = json.loads(factors_raw.strip().strip("```json").strip("```"))
                except json.JSONDecodeError:
                    key_factors = None

    # Fallback if Claude unavailable or failed
    if rationale is None:
        rationale = generate_fallback_rationale(profile, metrics, risk, mode, credit_offer, insurance_offer)
    if key_factors is None:
        key_factors = generate_fallback_key_factors(profile, metrics, risk)

    # Step 4: Determine offer status
    if risk["tier"] == "Rejected":
        offer_status = "Rejected"
    elif risk["tier"] == "Tier 3":
        offer_status = "Manual Review Required"
    else:
        offer_status = "Pre-Approved"

    # Step 5: Build rejection reasons if applicable
    rejection_reasons = None
    if risk["tier"] == "Rejected":
        rejection_reasons = []
        if "DATA_INSUFFICIENT" in risk["flags"]:
            rejection_reasons.append(
                f"Insufficient transaction history: {metrics['num_active_months']} months "
                f"(minimum 6 required)"
            )
        if "DECLINING_GMV" in risk["flags"]:
            rejection_reasons.append(
                f"Severe GMV decline: {metrics['gmv_growth_rate']:.1%} growth rate (H2 vs H1)"
            )
        if "HIGH_REFUND" in risk["flags"]:
            rejection_reasons.append(
                f"Excessive refund rate: {profile['return_and_refund_rate']:.1%} "
                f"(absolute threshold: 12%)"
            )
        if not rejection_reasons:
            rejection_reasons.append(
                f"Weighted risk score of {risk['weighted_total']}/100 below minimum threshold of 30"
            )

    # Package result
    decision = {
        "merchant_id": profile["merchant_id"],
        "merchant_name": profile["merchant_name"],
        "category": profile["category"],
        "whatsapp_number": profile["whatsapp_number"],
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "risk_score": {
            "scores": risk["scores"],
            "weighted_total": risk["weighted_total"],
            "risk_tier": risk["tier"],
            "flags": risk["flags"],
        },
        "offer_status": offer_status,
        "credit_offer": credit_offer,
        "insurance_offer": insurance_offer,
        "rationale": rationale,
        "key_factors": key_factors,
        "rejection_reasons": rejection_reasons,
        "derived_metrics": metrics,
    }

    return decision


# ── Batch Processing ──────────────────────────────────────────────────────

async def run_all_merchants(mode: str = "GrabCredit", use_claude: bool = True) -> list[dict]:
    """Run underwriting for all 10 merchants."""
    results = []
    for profile in MERCHANT_PROFILES:
        decision = await run_underwriting(profile, mode=mode, use_claude=use_claude)
        results.append(decision)
    return results


# ── Sync wrapper for testing ──────────────────────────────────────────────

def run_underwriting_sync(profile: dict, mode: str = "GrabCredit") -> dict:
    """Synchronous version using fallback rationale (no Claude API needed)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # If there's already an event loop, use it
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                run_underwriting(profile, mode=mode, use_claude=False)
            ).result()
    except RuntimeError:
        return asyncio.run(run_underwriting(profile, mode=mode, use_claude=False))


# ── Test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 80)
        print("UNDERWRITING AGENT — FULL PIPELINE TEST (fallback rationale)")
        print("=" * 80)

        for profile in MERCHANT_PROFILES:
            # Run both modes
            for mode in ["GrabCredit", "GrabInsurance"]:
                decision = await run_underwriting(profile, mode=mode, use_claude=False)

                print(f"\n{'─' * 70}")
                print(f"  {decision['merchant_name']} | {decision['category']} | {mode}")
                print(f"  Risk: {decision['risk_score']['risk_tier']} (Score: {decision['risk_score']['weighted_total']})")
                print(f"  Status: {decision['offer_status']}")

                if decision["credit_offer"]:
                    co = decision["credit_offer"]
                    print(f"  Credit: ₹{co['credit_limit_lakhs']}L @ {co['interest_rate_percent']}% | {co['tenure_options_months']} months | EMI: ₹{co['monthly_emi_estimate']:,.0f}")

                if decision["insurance_offer"]:
                    io = decision["insurance_offer"]
                    print(f"  Insurance: {io['policy_type']} | ₹{io['coverage_amount_lakhs']}L cover | Premium: ₹{io['annual_premium_inr']:,.0f}/yr")

                if decision["rejection_reasons"]:
                    for r in decision["rejection_reasons"]:
                        print(f"  ✗ {r}")

                print(f"\n  RATIONALE:")
                # Wrap rationale text at ~90 chars for readability
                words = decision["rationale"].split()
                line = "    "
                for w in words:
                    if len(line) + len(w) > 90:
                        print(line)
                        line = "    " + w
                    else:
                        line += " " + w if line.strip() else w
                if line.strip():
                    print(line)

                print(f"\n  KEY FACTORS:")
                for f in decision["key_factors"]:
                    print(f"    • {f}")

            print()

    asyncio.run(test())
