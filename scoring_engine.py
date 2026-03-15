"""
Risk Scoring Engine for GrabOn Merchant Underwriting.

Scoring approach:
  6 factors, each scored 0-100, with explicit weights.
  Weighted total maps to risk tier via thresholds.
  Hard rejection rules override scoring (data insufficiency, extreme decline).

This is intentionally NOT a black box — every score is traceable to a formula.
"""

from schemas import (
    MerchantProfile, DerivedMetrics, RiskScoreBreakdown, RiskTier,
    GrabCreditOffer, GrabInsuranceOffer, InsurancePolicyType,
)
from merchant_profiles import CATEGORY_BENCHMARKS, compute_derived_metrics


# ── Weights ────────────────────────────────────────────────────────────────

SCORING_WEIGHTS = {
    "gmv_stability": 0.25,        # most important — is the business stable?
    "growth_trajectory": 0.20,    # is it growing or declining?
    "customer_loyalty": 0.20,     # repeat customers + redemption rate
    "refund_risk": 0.15,          # high refunds = operational risk
    "platform_commitment": 0.10,  # exclusivity + deal engagement with GrabOn
    "data_sufficiency": 0.10,     # do we have enough history to decide?
}

# ── Tier Thresholds ────────────────────────────────────────────────────────

TIER_THRESHOLDS = {
    "tier_1_min": 72,   # >= 72 → Tier 1
    "tier_2_min": 50,   # >= 50 → Tier 2
    "tier_3_min": 30,   # >= 30 → Tier 3
    # below 30 → Rejected
}

# ── Hard Rejection Rules (override scoring) ────────────────────────────────

MIN_ACTIVE_MONTHS = 6
MAX_REFUND_RATE_ABSOLUTE = 0.12      # >12% refund = auto reject
MAX_GMV_DECLINE_RATE = -0.50         # >50% decline H2 vs H1 = auto reject


# ── Individual Factor Scoring Functions ────────────────────────────────────

def score_gmv_stability(metrics: DerivedMetrics, profile: MerchantProfile) -> float:
    """
    Combines coefficient of variation (volatility) with absolute GMV level.
    Low CV + decent GMV = high score. High CV = penalized.
    Travel category gets a seasonality adjustment.
    """
    if metrics.gmv_cv is None or metrics.avg_monthly_gmv == 0:
        return 10.0  # minimal score if we can't compute

    cv = metrics.gmv_cv
    
    # Seasonality adjustment: travel businesses get a gentler CV penalty
    if profile.category == "Travel" and profile.seasonality_index > 3.0:
        cv = cv * 0.6  # reduce effective CV by 40% for known seasonal categories
    
    # CV scoring: 0.0 = perfect stability (100), 0.5+ = very volatile (low score)
    if cv <= 0.08:
        cv_score = 100
    elif cv <= 0.15:
        cv_score = 85
    elif cv <= 0.25:
        cv_score = 65
    elif cv <= 0.35:
        cv_score = 45
    elif cv <= 0.50:
        cv_score = 30
    else:
        cv_score = 15

    # GMV level bonus: higher avg GMV relative to category benchmark = small boost
    benchmark = CATEGORY_BENCHMARKS.get(profile.category, {})
    benchmark_gmv = benchmark.get("avg_monthly_gmv_lakhs", 20.0)
    gmv_ratio = metrics.avg_monthly_gmv / benchmark_gmv
    gmv_level_bonus = min(15, max(0, (gmv_ratio - 0.5) * 20))

    return min(100, cv_score + gmv_level_bonus)


def score_growth_trajectory(metrics: DerivedMetrics) -> float:
    """
    Based on H2 vs H1 growth rate and GMV slope direction.
    Positive growth = high score. Decline = low score. Steep decline = very low.
    """
    if metrics.gmv_growth_rate is None:
        return 10.0

    growth = metrics.gmv_growth_rate
    
    if growth >= 0.30:
        score = 95
    elif growth >= 0.15:
        score = 80
    elif growth >= 0.05:
        score = 65
    elif growth >= -0.05:
        score = 50  # flat is okay, not great
    elif growth >= -0.15:
        score = 30
    elif growth >= -0.30:
        score = 15
    else:
        score = 5  # severe decline

    # Slope reinforcement: if slope confirms the growth direction, adjust
    if metrics.gmv_slope is not None:
        if metrics.gmv_slope > 1.0 and growth > 0:
            score = min(100, score + 5)
        elif metrics.gmv_slope < -1.0 and growth < 0:
            score = max(0, score - 5)

    return score


def score_customer_loyalty(profile: MerchantProfile) -> float:
    """
    Combines customer return rate and coupon redemption rate.
    High repeat + high engagement = strong loyalty signal.
    """
    benchmark = CATEGORY_BENCHMARKS.get(profile.category, {})
    bench_return = benchmark.get("avg_customer_return_rate", 0.50)
    bench_redemption = benchmark.get("avg_redemption_rate", 0.60)

    # Return rate: score relative to benchmark
    return_ratio = profile.customer_return_rate / bench_return if bench_return > 0 else 0
    if return_ratio >= 1.3:
        return_score = 95
    elif return_ratio >= 1.0:
        return_score = 75
    elif return_ratio >= 0.7:
        return_score = 55
    elif return_ratio >= 0.5:
        return_score = 35
    else:
        return_score = 15

    # Redemption rate: score relative to benchmark
    redemption_ratio = profile.coupon_redemption_rate / bench_redemption if bench_redemption > 0 else 0
    if redemption_ratio >= 1.2:
        redemption_score = 90
    elif redemption_ratio >= 1.0:
        redemption_score = 70
    elif redemption_ratio >= 0.8:
        redemption_score = 50
    elif redemption_ratio >= 0.6:
        redemption_score = 30
    else:
        redemption_score = 10

    return return_score * 0.6 + redemption_score * 0.4


def score_refund_risk(profile: MerchantProfile) -> float:
    """
    Lower refund rate = higher score. Compared against category benchmark.
    This is an INVERSE score — low refunds are good.
    """
    benchmark = CATEGORY_BENCHMARKS.get(profile.category, {})
    bench_refund = benchmark.get("avg_return_rate", 0.05)

    ratio = profile.return_and_refund_rate / bench_refund if bench_refund > 0 else 2.0

    if ratio <= 0.3:
        return 100  # way below benchmark — excellent
    elif ratio <= 0.5:
        return 90
    elif ratio <= 0.75:
        return 75
    elif ratio <= 1.0:
        return 60  # at benchmark — acceptable
    elif ratio <= 1.3:
        return 40
    elif ratio <= 1.8:
        return 20
    else:
        return 5  # way above benchmark — serious concern


def score_platform_commitment(profile: MerchantProfile) -> float:
    """
    Deal exclusivity rate + customer count as proxy for GrabOn engagement.
    """
    excl = profile.deal_exclusivity_rate
    if excl >= 0.50:
        excl_score = 90
    elif excl >= 0.35:
        excl_score = 70
    elif excl >= 0.20:
        excl_score = 45
    else:
        excl_score = 20

    # Customer count as a minor signal — larger base = more data confidence
    if profile.unique_customer_count >= 15000:
        cust_bonus = 10
    elif profile.unique_customer_count >= 8000:
        cust_bonus = 5
    else:
        cust_bonus = 0

    return min(100, excl_score + cust_bonus)


def score_data_sufficiency(metrics: DerivedMetrics) -> float:
    """
    How many months of active data do we have?
    12 months = full confidence. <6 = risky. <3 = reject-level.
    """
    months = metrics.num_active_months
    if months >= 12:
        return 100
    elif months >= 9:
        return 80
    elif months >= 6:
        return 60
    elif months >= 4:
        return 30
    else:
        return 5  # near-zero confidence


# ── Main Scoring Function ─────────────────────────────────────────────────

def compute_risk_score(profile: MerchantProfile) -> RiskScoreBreakdown:
    """
    Compute the full risk score breakdown for a merchant.
    Returns tier assignment with all individual factor scores.
    """
    raw_data = profile.model_dump()
    metrics = DerivedMetrics(**compute_derived_metrics(raw_data))

    # compute individual scores
    gmv_stab = score_gmv_stability(metrics, profile)
    growth = score_growth_trajectory(metrics)
    loyalty = score_customer_loyalty(profile)
    refund = score_refund_risk(profile)
    commitment = score_platform_commitment(profile)
    data_suff = score_data_sufficiency(metrics)

    # weighted total
    weighted = (
        gmv_stab * SCORING_WEIGHTS["gmv_stability"]
        + growth * SCORING_WEIGHTS["growth_trajectory"]
        + loyalty * SCORING_WEIGHTS["customer_loyalty"]
        + refund * SCORING_WEIGHTS["refund_risk"]
        + commitment * SCORING_WEIGHTS["platform_commitment"]
        + data_suff * SCORING_WEIGHTS["data_sufficiency"]
    )

    # detect flags
    is_data_insufficient = metrics.num_active_months < MIN_ACTIVE_MONTHS
    is_declining = (
        metrics.gmv_growth_rate is not None
        and metrics.gmv_growth_rate < MAX_GMV_DECLINE_RATE
    )
    is_high_refund = profile.return_and_refund_rate > MAX_REFUND_RATE_ABSOLUTE
    is_volatile = metrics.gmv_cv is not None and metrics.gmv_cv > 0.45

    # ── Hard rejection overrides ──
    if is_data_insufficient:
        tier = RiskTier.REJECTED
    elif is_declining and is_high_refund:
        tier = RiskTier.REJECTED
    elif is_declining and profile.return_and_refund_rate > 0.10:
        tier = RiskTier.REJECTED
    # ── Score-based tiering ──
    elif weighted >= TIER_THRESHOLDS["tier_1_min"]:
        tier = RiskTier.TIER_1
    elif weighted >= TIER_THRESHOLDS["tier_2_min"]:
        tier = RiskTier.TIER_2
    elif weighted >= TIER_THRESHOLDS["tier_3_min"]:
        tier = RiskTier.TIER_3
    else:
        tier = RiskTier.REJECTED

    return RiskScoreBreakdown(
        gmv_stability_score=round(gmv_stab, 1),
        growth_trajectory_score=round(growth, 1),
        customer_loyalty_score=round(loyalty, 1),
        refund_risk_score=round(refund, 1),
        platform_commitment_score=round(commitment, 1),
        data_sufficiency_score=round(data_suff, 1),
        weighted_total=round(weighted, 1),
        risk_tier=tier,
        is_data_insufficient=is_data_insufficient,
        is_declining_gmv=is_declining,
        is_high_refund=is_high_refund,
        is_volatile=is_volatile,
    )


# ── Offer Generation ──────────────────────────────────────────────────────

def generate_credit_offer(
    profile: MerchantProfile,
    metrics: DerivedMetrics,
    risk: RiskScoreBreakdown,
) -> GrabCreditOffer | None:
    """Generate a GrabCredit working capital offer based on risk tier."""
    if risk.risk_tier == RiskTier.REJECTED:
        return None

    avg_gmv = metrics.avg_monthly_gmv

    # Credit limit: multiple of avg monthly GMV, scaled by tier
    tier_multipliers = {
        RiskTier.TIER_1: 3.0,   # up to 3x monthly GMV
        RiskTier.TIER_2: 2.0,   # up to 2x
        RiskTier.TIER_3: 1.0,   # up to 1x — conservative
    }
    multiplier = tier_multipliers[risk.risk_tier]
    credit_limit = round(avg_gmv * multiplier, 1)

    # Interest rates by tier (annual)
    tier_rates = {
        RiskTier.TIER_1: (12.5, "Tier 1 — Preferential Rate (Poonawalla Prime)"),
        RiskTier.TIER_2: (16.0, "Tier 2 — Standard Rate"),
        RiskTier.TIER_3: (21.0, "Tier 3 — Risk-Adjusted Rate"),
    }
    rate, rate_label = tier_rates[risk.risk_tier]

    # Tenure options by tier
    tier_tenures = {
        RiskTier.TIER_1: [6, 12, 18, 24],
        RiskTier.TIER_2: [6, 12, 18],
        RiskTier.TIER_3: [6, 12],
    }
    tenures = tier_tenures[risk.risk_tier]

    # Estimate monthly EMI for the mid tenure option
    mid_tenure = tenures[len(tenures) // 2]
    monthly_rate = rate / 100 / 12
    emi = (
        credit_limit * 100000 * monthly_rate * (1 + monthly_rate) ** mid_tenure
    ) / ((1 + monthly_rate) ** mid_tenure - 1)

    return GrabCreditOffer(
        credit_limit_lakhs=credit_limit,
        interest_rate_percent=rate,
        interest_rate_tier=rate_label,
        tenure_options_months=tenures,
        monthly_emi_estimate=round(emi, 0),
    )


def generate_insurance_offer(
    profile: MerchantProfile,
    metrics: DerivedMetrics,
    risk: RiskScoreBreakdown,
) -> GrabInsuranceOffer | None:
    """Generate a GrabInsurance business interruption offer."""
    if risk.risk_tier == RiskTier.REJECTED:
        return None

    # Coverage: based on avg monthly GMV × months of coverage
    coverage_months = {
        RiskTier.TIER_1: 3,  # 3 months revenue coverage
        RiskTier.TIER_2: 2,
        RiskTier.TIER_3: 1,
    }
    months = coverage_months[risk.risk_tier]
    coverage = round(metrics.avg_monthly_gmv * months, 1)

    # Premium: % of coverage amount, adjusted by risk
    premium_pct = {
        RiskTier.TIER_1: 0.015,  # 1.5% of coverage
        RiskTier.TIER_2: 0.025,  # 2.5%
        RiskTier.TIER_3: 0.040,  # 4.0%
    }
    pct = premium_pct[risk.risk_tier]
    annual_premium = round(coverage * 100000 * pct, 0)

    # Policy type selection based on category
    category_policy_map = {
        "Fashion": InsurancePolicyType.INVENTORY_PROTECTION,
        "Food": InsurancePolicyType.BUSINESS_INTERRUPTION,
        "Travel": InsurancePolicyType.REVENUE_PROTECTION,
        "Electronics": InsurancePolicyType.INVENTORY_PROTECTION,
        "Health": InsurancePolicyType.BUSINESS_INTERRUPTION,
        "Beauty": InsurancePolicyType.INVENTORY_PROTECTION,
        "Gaming": InsurancePolicyType.REVENUE_PROTECTION,
    }
    policy_type = category_policy_map.get(
        profile.category, InsurancePolicyType.BUSINESS_INTERRUPTION
    )

    # Coverage details string
    details = (
        f"{months}-month revenue coverage at ₹{coverage}L. "
        f"Covers business interruption due to supply chain disruption, "
        f"platform downtime, or force majeure events. "
        f"Claim settlement within 15 working days."
    )

    return GrabInsuranceOffer(
        policy_type=policy_type,
        coverage_amount_lakhs=coverage,
        annual_premium_inr=annual_premium,
        premium_as_pct_of_gmv=round(annual_premium / (metrics.total_gmv_12m * 100000) * 100, 3)
        if metrics.total_gmv_12m > 0 else 0,
        coverage_details=details,
    )


# ── Test Harness ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from merchant_profiles import MERCHANT_PROFILES

    expected = [
        "Tier 1", "Tier 1", "Tier 1",
        "Tier 2", "Tier 2", "Tier 2",
        "Tier 3", "Tier 3",
        "Rejected", "Rejected",
    ]

    print(f"\n{'Merchant':<25} {'Expected':<12} {'Actual':<12} {'Score':>7} {'Match':>6}")
    print("=" * 70)

    mismatches = 0
    for merchant_data, exp in zip(MERCHANT_PROFILES, expected):
        profile = MerchantProfile(**merchant_data)
        risk = compute_risk_score(profile)
        match = "✓" if risk.risk_tier.value == exp else "✗"
        if match == "✗":
            mismatches += 1
        print(
            f"{profile.merchant_name:<25} "
            f"{exp:<12} "
            f"{risk.risk_tier.value:<12} "
            f"{risk.weighted_total:>6.1f} "
            f"{match:>6}"
        )
        # Print breakdown for debugging
        print(
            f"  GMV-stab={risk.gmv_stability_score:.0f} "
            f"Growth={risk.growth_trajectory_score:.0f} "
            f"Loyalty={risk.customer_loyalty_score:.0f} "
            f"Refund={risk.refund_risk_score:.0f} "
            f"Commit={risk.platform_commitment_score:.0f} "
            f"Data={risk.data_sufficiency_score:.0f}"
        )
        flags = []
        if risk.is_data_insufficient: flags.append("DATA_INSUFFICIENT")
        if risk.is_declining_gmv: flags.append("DECLINING_GMV")
        if risk.is_high_refund: flags.append("HIGH_REFUND")
        if risk.is_volatile: flags.append("VOLATILE")
        if flags:
            print(f"  FLAGS: {', '.join(flags)}")
        print()

    print(f"\n{'All tiers match expected!' if mismatches == 0 else f'{mismatches} MISMATCHES — need tuning'}")
