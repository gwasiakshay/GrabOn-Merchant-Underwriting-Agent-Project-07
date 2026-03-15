"""
GrabOn Merchant Profiles — 10 diverse merchants for underwriting agent demo
Distribution: 3 Tier 1, 3 Tier 2, 2 Tier 3, 2 Rejections
Categories: Fashion, Travel, Food, Electronics, Health, Beauty, Gaming
"""

MERCHANT_PROFILES = [
    # =========================================================================
    # TIER 1 — LOW RISK, BEST RATES (3 merchants)
    # =========================================================================
    {
        "merchant_id": "GRB-M001",
        "merchant_name": "TrendVault Fashion",
        "category": "Fashion",
        "whatsapp_number": "+919654676210",  # Twilio sandbox target
        "monthly_gmv_12m": [
            45.2,
            48.1,
            52.3,
            50.8,
            55.6,
            58.2,
            61.0,
            59.4,
            63.7,
            67.1,
            72.5,
            78.3,
        ],  # in ₹ lakhs — steady upward trend, classic Tier 1
        "coupon_redemption_rate": 0.74,  # 74% — high, shows engaged user base
        "unique_customer_count": 18500,
        "customer_return_rate": 0.68,  # 68% repeat customers — strong loyalty
        "avg_order_value": 2850.0,  # ₹2,850
        "seasonality_index": 1.73,  # peak/trough = 78.3/45.2 — moderate seasonality
        "deal_exclusivity_rate": 0.45,  # 45% exclusive deals with GrabOn
        "return_and_refund_rate": 0.031,  # 3.1% — well below fashion avg of ~8%
    },
    {
        "merchant_id": "GRB-M002",
        "merchant_name": "FreshBasket Foods",
        "category": "Food",
        "whatsapp_number": "+919654676210",
        "monthly_gmv_12m": [
            32.1,
            33.5,
            34.8,
            35.2,
            36.0,
            37.1,
            38.5,
            39.2,
            40.1,
            41.0,
            42.3,
            43.8,
        ],  # in ₹ lakhs — extremely stable, low variance growth
        "coupon_redemption_rate": 0.81,  # 81% — food coupons convert very well
        "unique_customer_count": 22000,
        "customer_return_rate": 0.76,  # 76% — high for food, sticky user base
        "avg_order_value": 680.0,  # ₹680 — typical food order
        "seasonality_index": 1.36,  # very low seasonality — food is consistent
        "deal_exclusivity_rate": 0.52,  # 52% exclusive — strong GrabOn relationship
        "return_and_refund_rate": 0.018,  # 1.8% — excellent for food category
    },
    {
        "merchant_id": "GRB-M003",
        "merchant_name": "MediCare Plus",
        "category": "Health",
        "whatsapp_number": "+919876543212",
        "monthly_gmv_12m": [
            18.5,
            19.2,
            20.1,
            21.3,
            22.0,
            23.5,
            24.8,
            25.1,
            26.3,
            27.0,
            28.5,
            30.2,
        ],  # in ₹ lakhs — smaller but very consistent growth
        "coupon_redemption_rate": 0.69,
        "unique_customer_count": 12000,
        "customer_return_rate": 0.72,  # health products = recurring purchases
        "avg_order_value": 1450.0,
        "seasonality_index": 1.63,
        "deal_exclusivity_rate": 0.38,
        "return_and_refund_rate": 0.022,  # 2.2% — low, health products rarely returned
    },
    # =========================================================================
    # TIER 2 — MODERATE RISK, STANDARD RATES (3 merchants)
    # =========================================================================
    {
        "merchant_id": "GRB-M004",
        "merchant_name": "WanderLust Travels",
        "category": "Travel",
        "whatsapp_number": "+919876543213",
        "monthly_gmv_12m": [
            12.3,
            8.5,
            7.2,
            6.8,
            15.2,
            22.5,
            28.3,
            18.6,
            14.1,
            9.8,
            25.6,
            35.2,
        ],  # EDGE CASE: wild seasonality but healthy overall
        # avg ~17L/month, but peak/trough ratio is extreme
        # Agent should recognize this as seasonal business, not instability
        "coupon_redemption_rate": 0.62,
        "unique_customer_count": 9500,
        "customer_return_rate": 0.45,  # lower repeat — travel is infrequent by nature
        "avg_order_value": 8500.0,  # high AOV — travel bookings
        "seasonality_index": 5.18,  # 35.2/6.8 — very high, but expected for travel
        "deal_exclusivity_rate": 0.30,
        "return_and_refund_rate": 0.058,  # 5.8% — cancellations common in travel
    },
    {
        "merchant_id": "GRB-M005",
        "merchant_name": "GadgetWorld Electronics",
        "category": "Electronics",
        "whatsapp_number": "+919876543214",
        "monthly_gmv_12m": [
            28.5,
            30.2,
            27.8,
            29.1,
            31.5,
            26.3,
            33.0,
            35.2,
            30.8,
            28.6,
            42.1,
            55.3,
        ],  # decent overall but inconsistent month-to-month
        # big spike in last 2 months (festive season) — need to check if sustainable
        "coupon_redemption_rate": 0.58,
        "unique_customer_count": 14200,
        "customer_return_rate": 0.41,  # electronics = lower repeat than fashion/food
        "avg_order_value": 5200.0,
        "seasonality_index": 2.10,  # festive-driven spikes
        "deal_exclusivity_rate": 0.22,  # low exclusivity — sells on many platforms
        "return_and_refund_rate": 0.065,  # 6.5% — slightly elevated for electronics
    },
    {
        "merchant_id": "GRB-M006",
        "merchant_name": "GlowUp Beauty",
        "category": "Beauty",
        "whatsapp_number": "+919876543215",
        "monthly_gmv_12m": [
            14.2,
            15.8,
            13.5,
            14.9,
            16.1,
            17.3,
            15.8,
            14.5,
            17.9,
            18.2,
            16.1,
            18.5,
        ],  # small, somewhat inconsistent — not a clear upward trend
        "coupon_redemption_rate": 0.59,  # slightly below benchmark
        "unique_customer_count": 8800,
        "customer_return_rate": 0.52,
        "avg_order_value": 1200.0,
        "seasonality_index": 1.44,
        "deal_exclusivity_rate": 0.28,  # lower exclusivity — hedging across platforms
        "return_and_refund_rate": 0.062,  # 6.2% — above beauty avg of 5%, product mismatch
    },
    # =========================================================================
    # TIER 3 — HIGH RISK, REQUIRES MANUAL REVIEW (2 merchants)
    # =========================================================================
    {
        "merchant_id": "GRB-M007",
        "merchant_name": "PixelArena Gaming",
        "category": "Gaming",
        "whatsapp_number": "+919876543216",
        "monthly_gmv_12m": [
            8.2,
            12.5,
            6.3,
            15.8,
            9.1,
            5.2,
            18.3,
            7.6,
            11.2,
            4.8,
            14.5,
            10.3,
        ],  # extremely volatile — no clear trend, high variance
        "coupon_redemption_rate": 0.38,  # very low redemption — deal quality issues
        "unique_customer_count": 5200,
        "customer_return_rate": 0.25,  # very low repeat — one-time buyers
        "avg_order_value": 3800.0,
        "seasonality_index": 3.81,  # 18.3/4.8 — volatile, not seasonal
        "deal_exclusivity_rate": 0.12,  # minimal commitment to GrabOn
        "return_and_refund_rate": 0.092,  # 9.2% — high refund rate
    },
    {
        "merchant_id": "GRB-M008",
        "merchant_name": "QuickBite Snacks",
        "category": "Food",
        "whatsapp_number": "+919876543217",
        "monthly_gmv_12m": [
            22.1,
            20.8,
            19.5,
            18.2,
            17.6,
            16.3,
            15.8,
            16.1,
            14.9,
            13.5,
            14.2,
            13.8,
        ],  # DECLINING trend — this is a red flag
        # started at 22L, now at 13.8L — ~37% decline over 12 months
        "coupon_redemption_rate": 0.55,
        "unique_customer_count": 11000,
        "customer_return_rate": 0.39,  # dropping loyalty
        "avg_order_value": 520.0,
        "seasonality_index": 1.64,
        "deal_exclusivity_rate": 0.28,
        "return_and_refund_rate": 0.071,  # 7.1% — high for food, quality concerns
    },
    # =========================================================================
    # REJECTIONS (2 merchants — distinct rejection reasons)
    # =========================================================================
    {
        "merchant_id": "GRB-M009",
        "merchant_name": "LuxeThread Couture",
        "category": "Fashion",
        "whatsapp_number": "+919876543218",
        # REJECTION REASON: Financial deterioration + extreme refund rate
        "monthly_gmv_12m": [
            38.5,
            35.2,
            31.8,
            28.1,
            24.5,
            20.3,
            17.8,
            15.2,
            12.6,
            10.1,
            8.5,
            7.2,
        ],  # catastrophic decline — 38.5L to 7.2L, ~81% drop
        "coupon_redemption_rate": 0.35,  # very low — users not engaging with deals
        "unique_customer_count": 6200,
        "customer_return_rate": 0.22,  # almost no repeat business
        "avg_order_value": 4500.0,  # high AOV but low volume
        "seasonality_index": 5.35,  # misleading — this is decline, not seasonality
        "deal_exclusivity_rate": 0.12,
        "return_and_refund_rate": 0.145,  # 14.5% — extremely high, operational issues
    },
    {
        "merchant_id": "GRB-M010",
        "merchant_name": "NovaTech Accessories",
        "category": "Electronics",
        "whatsapp_number": "+919876543219",
        # REJECTION REASON: Insufficient data / too new on platform
        "monthly_gmv_12m": [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            2.1,
            3.5,
            4.8,
        ],  # only 3 months of data — joined recently
        "coupon_redemption_rate": 0.42,  # too early to tell
        "unique_customer_count": 850,  # very small base
        "customer_return_rate": 0.28,  # low but sample size is tiny
        "avg_order_value": 1800.0,
        "seasonality_index": 2.29,  # meaningless with only 3 data points
        "deal_exclusivity_rate": 0.60,  # high exclusivity — but could be because they're new
        "return_and_refund_rate": 0.038,  # looks ok but insufficient volume to trust
    },
]


# =========================================================================
# CATEGORY BENCHMARKS — used by underwriting agent for comparison
# =========================================================================
CATEGORY_BENCHMARKS = {
    "Fashion": {
        "avg_return_rate": 0.08,
        "avg_redemption_rate": 0.65,
        "avg_customer_return_rate": 0.55,
        "avg_monthly_gmv_lakhs": 35.0,
        "min_months_required": 6,
    },
    "Food": {
        "avg_return_rate": 0.04,
        "avg_redemption_rate": 0.75,
        "avg_customer_return_rate": 0.60,
        "avg_monthly_gmv_lakhs": 25.0,
        "min_months_required": 6,
    },
    "Travel": {
        "avg_return_rate": 0.07,
        "avg_redemption_rate": 0.55,
        "avg_customer_return_rate": 0.35,
        "avg_monthly_gmv_lakhs": 20.0,
        "min_months_required": 6,
    },
    "Electronics": {
        "avg_return_rate": 0.06,
        "avg_redemption_rate": 0.52,
        "avg_customer_return_rate": 0.38,
        "avg_monthly_gmv_lakhs": 30.0,
        "min_months_required": 6,
    },
    "Health": {
        "avg_return_rate": 0.03,
        "avg_redemption_rate": 0.60,
        "avg_customer_return_rate": 0.55,
        "avg_monthly_gmv_lakhs": 15.0,
        "min_months_required": 6,
    },
    "Beauty": {
        "avg_return_rate": 0.05,
        "avg_redemption_rate": 0.62,
        "avg_customer_return_rate": 0.50,
        "avg_monthly_gmv_lakhs": 18.0,
        "min_months_required": 6,
    },
    "Gaming": {
        "avg_return_rate": 0.07,
        "avg_redemption_rate": 0.50,
        "avg_customer_return_rate": 0.35,
        "avg_monthly_gmv_lakhs": 12.0,
        "min_months_required": 6,
    },
}


def compute_derived_metrics(merchant: dict) -> dict:
    """Compute derived metrics the underwriting agent will use."""
    gmv = merchant["monthly_gmv_12m"]
    active_months = [g for g in gmv if g > 0]

    total_gmv = sum(gmv)
    avg_monthly_gmv = sum(active_months) / len(active_months) if active_months else 0
    num_active_months = len(active_months)

    # YoY growth: compare last 6 months avg to first 6 months avg
    first_half = [g for g in gmv[:6] if g > 0]
    second_half = [g for g in gmv[6:] if g > 0]

    if first_half and second_half:
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        gmv_growth_rate = (second_avg - first_avg) / first_avg if first_avg > 0 else 0
    else:
        gmv_growth_rate = None  # insufficient data

    # GMV trend: linear slope over active months (simplified)
    if len(active_months) >= 3:
        n = len(active_months)
        x_mean = (n - 1) / 2
        y_mean = sum(active_months) / n
        numerator = sum((i - x_mean) * (active_months[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        gmv_slope = numerator / denominator if denominator != 0 else 0
    else:
        gmv_slope = None

    # Coefficient of variation (volatility measure)
    if active_months and avg_monthly_gmv > 0:
        variance = sum((g - avg_monthly_gmv) ** 2 for g in active_months) / len(
            active_months
        )
        gmv_cv = (variance**0.5) / avg_monthly_gmv
    else:
        gmv_cv = None

    return {
        "total_gmv_12m": round(total_gmv, 2),
        "avg_monthly_gmv": round(avg_monthly_gmv, 2),
        "num_active_months": num_active_months,
        "gmv_growth_rate": round(gmv_growth_rate, 4)
        if gmv_growth_rate is not None
        else None,
        "gmv_slope": round(gmv_slope, 4) if gmv_slope is not None else None,
        "gmv_cv": round(gmv_cv, 4) if gmv_cv is not None else None,
        "latest_3m_avg_gmv": round(sum(gmv[-3:]) / 3, 2) if any(gmv[-3:]) else 0,
    }


if __name__ == "__main__":
    print(
        f"{'Merchant':<25} {'Category':<12} {'Tier':<10} {'Avg GMV':>10} {'Growth':>10} {'Refund':>8} {'CV':>8}"
    )
    print("-" * 95)

    expected_tiers = [
        "Tier 1",
        "Tier 1",
        "Tier 1",
        "Tier 2",
        "Tier 2",
        "Tier 2",
        "Tier 3",
        "Tier 3",
        "REJECT",
        "REJECT",
    ]

    for merchant, tier in zip(MERCHANT_PROFILES, expected_tiers):
        metrics = compute_derived_metrics(merchant)
        growth = (
            f"{metrics['gmv_growth_rate']:.1%}"
            if metrics["gmv_growth_rate"] is not None
            else "N/A"
        )
        cv = f"{metrics['gmv_cv']:.3f}" if metrics["gmv_cv"] is not None else "N/A"
        print(
            f"{merchant['merchant_name']:<25} "
            f"{merchant['category']:<12} "
            f"{tier:<10} "
            f"{metrics['avg_monthly_gmv']:>8.1f}L "
            f"{growth:>10} "
            f"{merchant['return_and_refund_rate']:>7.1%} "
            f"{cv:>8}"
        )
