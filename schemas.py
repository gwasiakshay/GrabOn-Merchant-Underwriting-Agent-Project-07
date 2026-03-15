"""
Pydantic models for the GrabOn Merchant Underwriting Agent.
Covers: merchant profiles, underwriting decisions, risk tiers, offers, and audit trail.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────

class MerchantCategory(str, Enum):
    FASHION = "Fashion"
    FOOD = "Food"
    TRAVEL = "Travel"
    ELECTRONICS = "Electronics"
    HEALTH = "Health"
    BEAUTY = "Beauty"
    GAMING = "Gaming"


class RiskTier(str, Enum):
    TIER_1 = "Tier 1"  # Low risk, best rates
    TIER_2 = "Tier 2"  # Moderate risk, standard rates
    TIER_3 = "Tier 3"  # High risk, manual review required
    REJECTED = "Rejected"


class UnderwritingMode(str, Enum):
    GRAB_CREDIT = "GrabCredit"
    GRAB_INSURANCE = "GrabInsurance"


class OfferStatus(str, Enum):
    PRE_APPROVED = "Pre-Approved"
    MANUAL_REVIEW = "Manual Review Required"
    REJECTED = "Rejected"
    ACCEPTED = "Accepted"       # merchant accepted the offer
    NACH_INITIATED = "NACH Mandate Initiated"


class InsurancePolicyType(str, Enum):
    BUSINESS_INTERRUPTION = "Business Interruption Cover"
    REVENUE_PROTECTION = "Revenue Protection Plan"
    INVENTORY_PROTECTION = "Inventory & Stock Protection"


# ── Merchant Profile ───────────────────────────────────────────────────────

class MerchantProfile(BaseModel):
    merchant_id: str
    merchant_name: str
    category: MerchantCategory
    whatsapp_number: str
    monthly_gmv_12m: list[float] = Field(
        ..., min_length=12, max_length=12,
        description="Monthly GMV in ₹ lakhs for last 12 months (index 0 = oldest)"
    )
    coupon_redemption_rate: float = Field(..., ge=0.0, le=1.0)
    unique_customer_count: int = Field(..., ge=0)
    customer_return_rate: float = Field(..., ge=0.0, le=1.0)
    avg_order_value: float = Field(..., ge=0.0, description="In ₹")
    seasonality_index: float = Field(..., ge=1.0, description="Peak GMV / Trough GMV")
    deal_exclusivity_rate: float = Field(..., ge=0.0, le=1.0)
    return_and_refund_rate: float = Field(..., ge=0.0, le=1.0)


# ── Derived Metrics (computed from profile) ────────────────────────────────

class DerivedMetrics(BaseModel):
    total_gmv_12m: float
    avg_monthly_gmv: float
    num_active_months: int
    gmv_growth_rate: Optional[float] = Field(
        None, description="H2 avg vs H1 avg growth rate"
    )
    gmv_slope: Optional[float] = Field(
        None, description="Linear trend slope of monthly GMV"
    )
    gmv_cv: Optional[float] = Field(
        None, description="Coefficient of variation — volatility measure"
    )
    latest_3m_avg_gmv: float


# ── Risk Score Breakdown ───────────────────────────────────────────────────

class RiskScoreBreakdown(BaseModel):
    """Individual scoring factors — each 0 to 100, weighted to final score."""
    gmv_stability_score: float = Field(..., ge=0, le=100)
    growth_trajectory_score: float = Field(..., ge=0, le=100)
    customer_loyalty_score: float = Field(..., ge=0, le=100)
    refund_risk_score: float = Field(..., ge=0, le=100)
    platform_commitment_score: float = Field(..., ge=0, le=100)
    data_sufficiency_score: float = Field(..., ge=0, le=100)
    weighted_total: float = Field(..., ge=0, le=100)
    risk_tier: RiskTier
    
    # flags
    is_data_insufficient: bool = False
    is_declining_gmv: bool = False
    is_high_refund: bool = False
    is_volatile: bool = False


# ── GrabCredit Offer ───────────────────────────────────────────────────────

class GrabCreditOffer(BaseModel):
    credit_limit_lakhs: float = Field(..., description="Working capital limit in ₹ lakhs")
    interest_rate_percent: float = Field(..., description="Annual interest rate %")
    interest_rate_tier: str = Field(
        ..., description="e.g. 'Tier 1 — Preferential Rate'"
    )
    tenure_options_months: list[int] = Field(
        ..., description="Available tenure options e.g. [6, 12, 18]"
    )
    monthly_emi_estimate: Optional[float] = Field(
        None, description="Estimated monthly EMI in ₹ for mid tenure option"
    )


# ── GrabInsurance Offer ────────────────────────────────────────────────────

class GrabInsuranceOffer(BaseModel):
    policy_type: InsurancePolicyType
    coverage_amount_lakhs: float
    annual_premium_inr: float
    premium_as_pct_of_gmv: float = Field(
        ..., description="Premium as % of annual GMV — affordability metric"
    )
    coverage_details: str


# ── Underwriting Decision (the main output) ────────────────────────────────

class UnderwritingDecision(BaseModel):
    merchant_id: str
    merchant_name: str
    category: MerchantCategory
    mode: UnderwritingMode
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # risk assessment
    risk_score: RiskScoreBreakdown
    offer_status: OfferStatus
    
    # offers (populated based on mode and approval)
    credit_offer: Optional[GrabCreditOffer] = None
    insurance_offer: Optional[GrabInsuranceOffer] = None
    
    # explainability — the key differentiator
    rationale: str = Field(
        ..., min_length=100,
        description="3-5 sentence explanation referencing specific data points"
    )
    key_factors: list[str] = Field(
        ..., min_length=2, max_length=5,
        description="Bullet-point summary of decision drivers"
    )
    
    # rejection specifics
    rejection_reasons: Optional[list[str]] = None


# ── WhatsApp Notification ──────────────────────────────────────────────────

class WhatsAppNotification(BaseModel):
    merchant_id: str
    merchant_name: str
    whatsapp_number: str
    message_body: str
    sent_at: Optional[datetime] = None
    delivery_status: str = "pending"  # pending | sent | delivered | failed
    twilio_sid: Optional[str] = None


# ── NACH Mandate (mock) ───────────────────────────────────────────────────

class NACHMandate(BaseModel):
    merchant_id: str
    mandate_id: str
    amount_lakhs: float
    frequency: str = "monthly"
    bank_account_last4: str = "XXXX"
    status: str = "initiated"  # initiated | confirmed | active | cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Audit Log Entry ───────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    merchant_id: str
    action: str  # e.g. "underwriting_run", "offer_sent", "offer_accepted"
    mode: Optional[UnderwritingMode] = None
    details: dict = Field(default_factory=dict)
