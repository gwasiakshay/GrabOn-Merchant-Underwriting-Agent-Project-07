"""
Standalone scoring engine test — no external dependencies.
Validates that all 10 merchants land in their expected tiers.
"""

from merchant_profiles import MERCHANT_PROFILES, CATEGORY_BENCHMARKS, compute_derived_metrics

# ── Weights & Thresholds ──────────────────────────────────────────────────

SCORING_WEIGHTS = {
    "gmv_stability": 0.25,
    "growth_trajectory": 0.20,
    "customer_loyalty": 0.20,
    "refund_risk": 0.15,
    "platform_commitment": 0.10,
    "data_sufficiency": 0.10,
}

TIER_1_MIN = 72
TIER_2_MIN = 50
TIER_3_MIN = 30

MIN_ACTIVE_MONTHS = 6
MAX_REFUND_RATE_ABSOLUTE = 0.12
MAX_GMV_DECLINE_RATE = -0.50


# ── Scoring Functions ─────────────────────────────────────────────────────

def score_gmv_stability(metrics, profile):
    cv = metrics["gmv_cv"]
    if cv is None or metrics["avg_monthly_gmv"] == 0:
        return 10.0

    # Travel seasonality adjustment
    if profile["category"] == "Travel" and profile["seasonality_index"] > 3.0:
        cv = cv * 0.6

    if cv <= 0.08:    cv_score = 100
    elif cv <= 0.15:  cv_score = 85
    elif cv <= 0.25:  cv_score = 65
    elif cv <= 0.35:  cv_score = 45
    elif cv <= 0.50:  cv_score = 30
    else:             cv_score = 15

    bench = CATEGORY_BENCHMARKS.get(profile["category"], {})
    bench_gmv = bench.get("avg_monthly_gmv_lakhs", 20.0)
    gmv_ratio = metrics["avg_monthly_gmv"] / bench_gmv
    gmv_bonus = min(15, max(0, (gmv_ratio - 0.5) * 20))

    return min(100, cv_score + gmv_bonus)


def score_growth_trajectory(metrics):
    growth = metrics["gmv_growth_rate"]
    if growth is None:
        return 10.0

    if growth >= 0.30:    score = 95
    elif growth >= 0.15:  score = 80
    elif growth >= 0.05:  score = 65
    elif growth >= -0.05: score = 50
    elif growth >= -0.15: score = 30
    elif growth >= -0.30: score = 15
    else:                 score = 5

    slope = metrics["gmv_slope"]
    if slope is not None:
        if slope > 1.0 and growth > 0:
            score = min(100, score + 5)
        elif slope < -1.0 and growth < 0:
            score = max(0, score - 5)

    return score


def score_customer_loyalty(profile):
    bench = CATEGORY_BENCHMARKS.get(profile["category"], {})
    bench_return = bench.get("avg_customer_return_rate", 0.50)
    bench_redemption = bench.get("avg_redemption_rate", 0.60)

    rr = profile["customer_return_rate"] / bench_return if bench_return > 0 else 0
    if rr >= 1.3:    return_score = 95
    elif rr >= 1.0:  return_score = 75
    elif rr >= 0.7:  return_score = 55
    elif rr >= 0.5:  return_score = 35
    else:            return_score = 15

    rd = profile["coupon_redemption_rate"] / bench_redemption if bench_redemption > 0 else 0
    if rd >= 1.2:    redemption_score = 90
    elif rd >= 1.0:  redemption_score = 70
    elif rd >= 0.8:  redemption_score = 50
    elif rd >= 0.6:  redemption_score = 30
    else:            redemption_score = 10

    return return_score * 0.6 + redemption_score * 0.4


def score_refund_risk(profile):
    bench = CATEGORY_BENCHMARKS.get(profile["category"], {})
    bench_refund = bench.get("avg_return_rate", 0.05)
    ratio = profile["return_and_refund_rate"] / bench_refund if bench_refund > 0 else 2.0

    if ratio <= 0.3:    return 100
    elif ratio <= 0.5:  return 90
    elif ratio <= 0.75: return 75
    elif ratio <= 1.0:  return 60
    elif ratio <= 1.3:  return 40
    elif ratio <= 1.8:  return 20
    else:               return 5


def score_platform_commitment(profile):
    excl = profile["deal_exclusivity_rate"]
    if excl >= 0.50:    excl_score = 90
    elif excl >= 0.35:  excl_score = 70
    elif excl >= 0.20:  excl_score = 45
    else:               excl_score = 20

    if profile["unique_customer_count"] >= 15000:   cust_bonus = 10
    elif profile["unique_customer_count"] >= 8000:  cust_bonus = 5
    else:                                            cust_bonus = 0

    return min(100, excl_score + cust_bonus)


def score_data_sufficiency(metrics):
    months = metrics["num_active_months"]
    if months >= 12:   return 100
    elif months >= 9:  return 80
    elif months >= 6:  return 60
    elif months >= 4:  return 30
    else:              return 5


# ── Main Scoring ──────────────────────────────────────────────────────────

def compute_risk_score(profile):
    metrics = compute_derived_metrics(profile)

    scores = {
        "gmv_stability": score_gmv_stability(metrics, profile),
        "growth_trajectory": score_growth_trajectory(metrics),
        "customer_loyalty": score_customer_loyalty(profile),
        "refund_risk": score_refund_risk(profile),
        "platform_commitment": score_platform_commitment(profile),
        "data_sufficiency": score_data_sufficiency(metrics),
    }

    weighted = sum(scores[k] * SCORING_WEIGHTS[k] for k in scores)

    # Flags
    is_data_insufficient = metrics["num_active_months"] < MIN_ACTIVE_MONTHS
    is_declining = (
        metrics["gmv_growth_rate"] is not None
        and metrics["gmv_growth_rate"] < MAX_GMV_DECLINE_RATE
    )
    is_high_refund = profile["return_and_refund_rate"] > MAX_REFUND_RATE_ABSOLUTE
    is_volatile = metrics["gmv_cv"] is not None and metrics["gmv_cv"] > 0.45

    # Hard rejection overrides
    if is_data_insufficient:
        tier = "Rejected"
    elif is_declining and is_high_refund:
        tier = "Rejected"
    elif is_declining and profile["return_and_refund_rate"] > 0.10:
        tier = "Rejected"
    elif weighted >= TIER_1_MIN:
        tier = "Tier 1"
    elif weighted >= TIER_2_MIN:
        tier = "Tier 2"
    elif weighted >= TIER_3_MIN:
        tier = "Tier 3"
    else:
        tier = "Rejected"

    flags = []
    if is_data_insufficient: flags.append("DATA_INSUFFICIENT")
    if is_declining: flags.append("DECLINING_GMV")
    if is_high_refund: flags.append("HIGH_REFUND")
    if is_volatile: flags.append("VOLATILE")

    return {
        "scores": scores,
        "weighted_total": round(weighted, 1),
        "tier": tier,
        "flags": flags,
        "metrics": metrics,
    }


# ── Run Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    expected = [
        "Tier 1", "Tier 1", "Tier 1",
        "Tier 2", "Tier 2", "Tier 2",
        "Tier 3", "Tier 3",
        "Rejected", "Rejected",
    ]

    print(f"\n{'Merchant':<25} {'Expected':<12} {'Actual':<12} {'Score':>7} {'Match':>6}")
    print("=" * 70)

    mismatches = 0
    for profile, exp in zip(MERCHANT_PROFILES, expected):
        result = compute_risk_score(profile)
        match = "✓" if result["tier"] == exp else "✗"
        if match == "✗":
            mismatches += 1

        print(
            f"{profile['merchant_name']:<25} "
            f"{exp:<12} "
            f"{result['tier']:<12} "
            f"{result['weighted_total']:>6.1f} "
            f"{match:>6}"
        )
        s = result["scores"]
        print(
            f"  GMV-stab={s['gmv_stability']:.0f} "
            f"Growth={s['growth_trajectory']:.0f} "
            f"Loyalty={s['customer_loyalty']:.0f} "
            f"Refund={s['refund_risk']:.0f} "
            f"Commit={s['platform_commitment']:.0f} "
            f"Data={s['data_sufficiency']:.0f}"
        )
        if result["flags"]:
            print(f"  FLAGS: {', '.join(result['flags'])}")
        print()

    print(f"{'All tiers match expected!' if mismatches == 0 else f'{mismatches} MISMATCHES — tuning needed'}\n")
