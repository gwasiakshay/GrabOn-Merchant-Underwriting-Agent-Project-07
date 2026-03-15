"""
GrabOn Merchant Underwriting Agent — FastAPI Server

Endpoints:
  GET  /api/merchants                    — list all merchants with latest decisions
  GET  /api/merchants/{id}               — single merchant detail
  POST /api/underwrite/{id}              — run underwriting for one merchant
  POST /api/underwrite-all               — run underwriting for all merchants
  POST /api/whatsapp/send/{id}           — send offer via WhatsApp (Twilio)
  POST /api/offer/accept/{id}            — accept offer → trigger NACH mandate
  GET  /api/audit-log                    — full audit trail
  GET  /api/dashboard/summary            — dashboard stats
  GET  /health                           — health check

CORS enabled for React frontend on localhost:5173 (Vite default).
"""

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from merchant_profiles import MERCHANT_PROFILES, compute_derived_metrics
from underwriting_agent import run_underwriting


# ── Twilio Setup ──────────────────────────────────────────────────────────

try:
    from twilio.rest import Client as TwilioClient
    HAS_TWILIO = True
except ImportError:
    HAS_TWILIO = False


def get_twilio_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if sid and token and HAS_TWILIO:
        return TwilioClient(sid, token)
    return None


TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


# ── In-Memory State ───────────────────────────────────────────────────────

decisions_store: dict[str, dict[str, dict]] = {}   # merchant_id → {mode → decision}
nach_store: dict[str, dict] = {}                    # merchant_id → NACH mandate
audit_log: list[dict] = []
AUDIT_LOG_FILE = Path("audit_log.jsonl")


def log_audit(merchant_id: str, action: str, mode: Optional[str] = None, details: Optional[dict] = None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "merchant_id": merchant_id,
        "action": action,
        "mode": mode,
        "details": details or {},
    }
    audit_log.append(entry)
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ── Request Models ────────────────────────────────────────────────────────

class UnderwriteRequest(BaseModel):
    mode: str = "GrabCredit"
    use_claude: bool = True


class WhatsAppRequest(BaseModel):
    mode: str = "GrabCredit"


class AcceptOfferRequest(BaseModel):
    mode: str = "GrabCredit"
    bank_account_last4: str = "XXXX"


# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting GrabOn Underwriting Agent...")
    print(f"  Twilio: {'ready' if HAS_TWILIO and os.getenv('TWILIO_ACCOUNT_SID') else 'mock mode'}")
    print(f"  Claude API: {'ready' if os.getenv('ANTHROPIC_API_KEY') else 'fallback mode'}")

    for profile in MERCHANT_PROFILES:
        mid = profile["merchant_id"]
        decisions_store[mid] = {}
        for mode in ["GrabCredit", "GrabInsurance"]:
            decision = await run_underwriting(profile, mode=mode, use_claude=False)
            decisions_store[mid][mode] = decision
            log_audit(mid, "underwriting_run", mode, {
                "risk_tier": decision["risk_score"]["risk_tier"],
                "weighted_score": decision["risk_score"]["weighted_total"],
                "offer_status": decision["offer_status"],
            })

    print(f"  Pre-loaded {len(MERCHANT_PROFILES)} merchants (both modes)")
    yield
    print("Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────

app = FastAPI(
    title="GrabOn Merchant Underwriting Agent",
    description="AI-powered merchant underwriting for GrabCredit & GrabInsurance",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────

def find_profile(merchant_id: str) -> dict:
    for p in MERCHANT_PROFILES:
        if p["merchant_id"] == merchant_id:
            return p
    raise HTTPException(status_code=404, detail=f"Merchant {merchant_id} not found")


def build_merchant_summary(profile: dict) -> dict:
    mid = profile["merchant_id"]
    metrics = compute_derived_metrics(profile)
    credit = decisions_store.get(mid, {}).get("GrabCredit")
    insurance = decisions_store.get(mid, {}).get("GrabInsurance")
    nach = nach_store.get(mid)

    summary = {
        "merchant_id": mid,
        "merchant_name": profile["merchant_name"],
        "category": profile["category"],
        "whatsapp_number": profile["whatsapp_number"],
        "avg_monthly_gmv": metrics["avg_monthly_gmv"],
        "total_gmv_12m": metrics["total_gmv_12m"],
        "gmv_growth_rate": metrics["gmv_growth_rate"],
        "num_active_months": metrics["num_active_months"],
        "unique_customers": profile["unique_customer_count"],
        "return_and_refund_rate": profile["return_and_refund_rate"],
        "customer_return_rate": profile["customer_return_rate"],
        "coupon_redemption_rate": profile["coupon_redemption_rate"],
        "deal_exclusivity_rate": profile["deal_exclusivity_rate"],
        "seasonality_index": profile["seasonality_index"],
        "monthly_gmv_12m": profile["monthly_gmv_12m"],
    }

    if credit:
        summary["credit"] = {
            "risk_tier": credit["risk_score"]["risk_tier"],
            "weighted_score": credit["risk_score"]["weighted_total"],
            "scores": credit["risk_score"]["scores"],
            "flags": credit["risk_score"]["flags"],
            "offer_status": credit["offer_status"],
            "offer": credit.get("credit_offer"),
            "rationale": credit["rationale"],
            "key_factors": credit["key_factors"],
            "rejection_reasons": credit.get("rejection_reasons"),
        }

    if insurance:
        summary["insurance"] = {
            "risk_tier": insurance["risk_score"]["risk_tier"],
            "weighted_score": insurance["risk_score"]["weighted_total"],
            "scores": insurance["risk_score"]["scores"],
            "flags": insurance["risk_score"]["flags"],
            "offer_status": insurance["offer_status"],
            "offer": insurance.get("insurance_offer"),
            "rationale": insurance["rationale"],
            "key_factors": insurance["key_factors"],
            "rejection_reasons": insurance.get("rejection_reasons"),
        }

    if nach:
        summary["nach_mandate"] = nach

    return summary


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "merchants_loaded": len(MERCHANT_PROFILES),
        "decisions_cached": sum(len(v) for v in decisions_store.values()),
        "twilio_available": HAS_TWILIO and bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "claude_available": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.get("/api/merchants")
async def list_merchants():
    return {
        "merchants": [build_merchant_summary(p) for p in MERCHANT_PROFILES],
        "total": len(MERCHANT_PROFILES),
    }


@app.get("/api/decisions")
async def list_decisions():
    """Return all decisions in a flat list for the dashboard."""
    results = []
    for mid, modes in decisions_store.items():
        for mode_name, decision in modes.items():
            results.append(decision)
    return {"decisions": results, "total": len(results)}


@app.get("/api/merchants/{merchant_id}")
async def get_merchant(merchant_id: str):
    profile = find_profile(merchant_id)
    metrics = compute_derived_metrics(profile)
    return {
        "profile": profile,
        "derived_metrics": metrics,
        "decisions": decisions_store.get(merchant_id, {}),
        "nach_mandate": nach_store.get(merchant_id),
        "audit_trail": [e for e in audit_log if e["merchant_id"] == merchant_id],
    }


@app.post("/api/underwrite/{merchant_id}")
async def underwrite_merchant(merchant_id: str, req: UnderwriteRequest):
    profile = find_profile(merchant_id)
    if req.mode not in ("GrabCredit", "GrabInsurance"):
        raise HTTPException(status_code=400, detail="Mode must be GrabCredit or GrabInsurance")

    decision = await run_underwriting(profile, mode=req.mode, use_claude=req.use_claude)

    if merchant_id not in decisions_store:
        decisions_store[merchant_id] = {}
    decisions_store[merchant_id][req.mode] = decision

    log_audit(merchant_id, "underwriting_run", req.mode, {
        "risk_tier": decision["risk_score"]["risk_tier"],
        "weighted_score": decision["risk_score"]["weighted_total"],
        "offer_status": decision["offer_status"],
        "used_claude": req.use_claude,
    })
    return decision


@app.post("/api/underwrite-all")
async def underwrite_all(req: UnderwriteRequest):
    results = []
    for profile in MERCHANT_PROFILES:
        mid = profile["merchant_id"]
        decision = await run_underwriting(profile, mode=req.mode, use_claude=req.use_claude)
        if mid not in decisions_store:
            decisions_store[mid] = {}
        decisions_store[mid][req.mode] = decision
        log_audit(mid, "underwriting_run", req.mode, {
            "risk_tier": decision["risk_score"]["risk_tier"],
            "offer_status": decision["offer_status"],
        })
        results.append(decision)
    return {"results": results, "total": len(results), "summary": {"total_processed": len(results)}}


# ── WhatsApp ──────────────────────────────────────────────────────────────

def format_whatsapp_message(decision: dict) -> str:
    name = decision["merchant_name"]
    mode = decision["mode"]
    status = decision["offer_status"]

    lines = [
        f"*GrabOn {mode} — Pre-Approved Offer*",
        "---",
        f"Dear *{name}*,",
        "",
    ]

    if status == "Rejected":
        lines.extend([
            f"After reviewing your transaction history on GrabOn, we're unable to extend a {mode} offer at this time.",
            "",
            "*Reason:*",
        ])
        for r in (decision.get("rejection_reasons") or []):
            lines.append(f"- {r}")
        lines.extend(["", "We'll reassess your eligibility in 90 days."])

    elif status == "Manual Review Required":
        tier = decision["risk_score"]["risk_tier"]
        lines.extend([
            f"Your {mode} application is under review.",
            f"Risk Assessment: *{tier}* (Score: {decision['risk_score']['weighted_total']}/100)",
            "",
            "A relationship manager will contact you within 3 business days.",
        ])

    elif mode == "GrabCredit" and decision.get("credit_offer"):
        co = decision["credit_offer"]
        lines.extend([
            "Congratulations! You've been pre-approved for working capital credit.",
            "",
            f"*Credit Limit:* Rs.{co['credit_limit_lakhs']}L",
            f"*Interest Rate:* {co['interest_rate_percent']}% p.a.",
            f"*Rate Tier:* {co['interest_rate_tier']}",
            f"*Tenure Options:* {', '.join(str(t) + 'mo' for t in co['tenure_options_months'])}",
            f"*Est. EMI:* Rs.{co['monthly_emi_estimate']:,.0f}/month ({co['emi_tenure_months']}mo)",
            "",
            "*Why you qualified:*",
            decision["rationale"][:500],
        ])

    elif mode == "GrabInsurance" and decision.get("insurance_offer"):
        io = decision["insurance_offer"]
        lines.extend([
            "Congratulations! You've been pre-approved for business insurance.",
            "",
            f"*Policy:* {io['policy_type']}",
            f"*Coverage:* Rs.{io['coverage_amount_lakhs']}L",
            f"*Annual Premium:* Rs.{io['annual_premium_inr']:,.0f}",
            "",
            "*Why we recommend this:*",
            decision["rationale"][:500],
        ])

    lines.extend([
        "",
        "---",
        "Reply ACCEPT to proceed or CALL to speak with a relationship manager.",
        "_Powered by GrabOn x Poonawalla Fincorp_",
    ])

    return "\n".join(lines)


@app.post("/api/whatsapp/send/{merchant_id}")
async def send_whatsapp(merchant_id: str, req: WhatsAppRequest):
    profile = find_profile(merchant_id)
    decision = decisions_store.get(merchant_id, {}).get(req.mode)

    if not decision:
        raise HTTPException(status_code=400, detail=f"No {req.mode} decision found. Run underwriting first.")

    message_body = format_whatsapp_message(decision)
    whatsapp_number = profile["whatsapp_number"]

    result = {
        "merchant_id": merchant_id,
        "merchant_name": profile["merchant_name"],
        "whatsapp_number": whatsapp_number,
        "mode": req.mode,
        "message_body": message_body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    twilio_client = get_twilio_client()
    if twilio_client:
        try:
            message = twilio_client.messages.create(
                body=message_body,
                from_=TWILIO_WHATSAPP_FROM,
                to=f"whatsapp:{whatsapp_number}",
            )
            result["delivery_status"] = "sent"
            result["twilio_sid"] = message.sid
            result["twilio_status"] = message.status
        except Exception as e:
            result["delivery_status"] = "failed"
            result["error"] = str(e)
    else:
        result["delivery_status"] = "mock"
        result["note"] = (
            "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN env vars. "
            "For sandbox: send 'join <keyword>' to whatsapp:+14155238886 first."
        )

    log_audit(merchant_id, "whatsapp_sent", req.mode, {
        "delivery_status": result["delivery_status"],
        "twilio_sid": result.get("twilio_sid"),
    })

    return result


# ── Accept Offer + NACH ───────────────────────────────────────────────────

@app.post("/api/offer/accept/{merchant_id}")
async def accept_offer(merchant_id: str, req: AcceptOfferRequest):
    profile = find_profile(merchant_id)
    decision = decisions_store.get(merchant_id, {}).get(req.mode)

    if not decision:
        raise HTTPException(status_code=400, detail=f"No {req.mode} decision found.")
    if decision["offer_status"] == "Rejected":
        raise HTTPException(status_code=400, detail="Cannot accept a rejected offer.")

    decision["offer_status"] = "Accepted"

    mandate_id = f"NACH-{uuid.uuid4().hex[:8].upper()}"

    if req.mode == "GrabCredit" and decision.get("credit_offer"):
        amount = decision["credit_offer"]["credit_limit_lakhs"]
        frequency = "monthly"
    elif req.mode == "GrabInsurance" and decision.get("insurance_offer"):
        amount = decision["insurance_offer"]["annual_premium_inr"] / 100000
        frequency = "annual"
    else:
        amount = 0
        frequency = "monthly"

    nach = {
        "mandate_id": mandate_id,
        "merchant_id": merchant_id,
        "merchant_name": profile["merchant_name"],
        "mode": req.mode,
        "amount_lakhs": round(amount, 2),
        "frequency": frequency,
        "bank_account_last4": req.bank_account_last4,
        "status": "initiated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_activation": "3-5 business days",
    }

    nach_store[merchant_id] = nach

    log_audit(merchant_id, "offer_accepted", req.mode, {"mandate_id": mandate_id})
    log_audit(merchant_id, "nach_initiated", req.mode, {"mandate_id": mandate_id, "amount_lakhs": nach["amount_lakhs"]})

    return {
        "message": f"Offer accepted for {profile['merchant_name']}",
        "offer_status": "Accepted",
        "nach_mandate": nach,
    }


# ── Audit Log ─────────────────────────────────────────────────────────────

@app.get("/api/audit-log")
async def get_audit_log(
    merchant_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    entries = audit_log
    if merchant_id:
        entries = [e for e in entries if e["merchant_id"] == merchant_id]
    if action:
        entries = [e for e in entries if e["action"] == action]
    return {"entries": entries[-limit:], "total": len(audit_log), "filtered": len(entries)}


# ── Dashboard Summary ─────────────────────────────────────────────────────

@app.get("/api/dashboard/summary")
async def dashboard_summary():
    tier_counts = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0, "Rejected": 0}
    total_credit = 0
    total_coverage = 0
    total_premium = 0

    for mid, modes in decisions_store.items():
        credit = modes.get("GrabCredit", {})
        insurance = modes.get("GrabInsurance", {})

        if credit:
            tier = credit.get("risk_score", {}).get("risk_tier", "Unknown")
            if tier in tier_counts:
                tier_counts[tier] += 1
            if credit.get("credit_offer"):
                total_credit += credit["credit_offer"]["credit_limit_lakhs"]

        if insurance and insurance.get("insurance_offer"):
            total_coverage += insurance["insurance_offer"]["coverage_amount_lakhs"]
            total_premium += insurance["insurance_offer"]["annual_premium_inr"]

    return {
        "total_merchants": len(MERCHANT_PROFILES),
        "tier_distribution": tier_counts,
        "total_credit_deployed_lakhs": round(total_credit, 1),
        "total_insurance_coverage_lakhs": round(total_coverage, 1),
        "total_annual_premium_inr": round(total_premium, 0),
        "offers_sent_via_whatsapp": len([e for e in audit_log if e["action"] == "whatsapp_sent"]),
        "offers_accepted": len([e for e in audit_log if e["action"] == "offer_accepted"]),
        "nach_mandates_active": len(nach_store),
    }


# ── Serve Dashboard ───────────────────────────────────────────────────────

from fastapi.responses import FileResponse
import pathlib

DASHBOARD_PATH = pathlib.Path(__file__).parent / "dashboard.html"

@app.get("/")
async def serve_dashboard():
    """Serve the dashboard UI."""
    if DASHBOARD_PATH.exists():
        return FileResponse(DASHBOARD_PATH, media_type="text/html")
    return {"message": "Dashboard not found. Place dashboard.html in the same directory as server.py."}


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n  🚀 GrabOn Underwriting Agent")
    print(f"  📊 Dashboard: http://localhost:8000")
    print(f"  📡 API Docs:  http://localhost:8000/docs")
    print(f"  {'✅' if os.getenv('ANTHROPIC_API_KEY') else '⚠️ '} Claude API: {'configured' if os.getenv('ANTHROPIC_API_KEY') else 'not set (using fallback rationale)'}")
    print(f"  {'✅' if os.getenv('TWILIO_ACCOUNT_SID') else '⚠️ '} Twilio:     {'configured' if os.getenv('TWILIO_ACCOUNT_SID') else 'not set (WhatsApp simulated)'}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
