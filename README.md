# GrabOn Merchant Underwriting Agent

**Project 07 — GrabOn Vibe Coder Challenge 2025**

An AI-powered underwriting agent that assesses GrabOn's merchant partners for two embedded financial products — **GrabCredit** (working capital loans via Poonawalla Fincorp) and **GrabInsurance** (business interruption coverage). The agent ingests merchant transaction data, runs a 6-factor risk scoring engine, generates explainable credit/insurance offers with data-backed rationale, and delivers pre-approved offers via WhatsApp.

---

## Live Demo

**Dashboard:** `http://localhost:8000` after starting the server.

**Loom Walkthrough:** (https://www.loom.com/share/fdadbfff6a994954ab5db54e8ed5bd0a)

---

## What I Built

### The Problem

GrabOn has 3,500+ active merchants with 12 months of rich transaction data — GMV trajectories, coupon redemption rates, customer return rates, refund patterns. Traditional banks don't have this data. The challenge is turning this behavioral signal into automated, explainable underwriting decisions for two products: working capital credit and business interruption insurance.

### The Solution

A full-stack underwriting pipeline:

1. **Risk Scoring Engine** — 6 weighted factors (GMV stability, growth trajectory, customer loyalty, refund risk, platform commitment, data sufficiency), each scored 0–100 against category benchmarks. Hard rejection rules override scoring for data insufficiency or severe decline.

2. **Underwriting Agent** — Two modes (GrabCredit / GrabInsurance). Generates tier-appropriate offers using deterministic formulas, then produces 3–5 sentence rationale narratives using Claude API (with a deterministic fallback that still references specific data points).

3. **WhatsApp Delivery** — Formatted business notifications via Twilio sandbox with four distinct templates: Pre-Approved, Manual Review, Rejected, and Insurance offers.

4. **Merchant Dashboard** — Single-page React app served from FastAPI. Merchant grid with tier badges and risk flags, drill-down with GMV chart + score breakdown bars + offer details + rationale, one-click Accept Offer triggering mock NACH mandate, and full audit trail.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  dashboard.html                       │
│         (React SPA served at localhost:8000)          │
└──────────────────────┬───────────────────────────────┘
                       │ REST API
┌──────────────────────▼───────────────────────────────┐
│                   server.py                           │
│              FastAPI + CORS + Lifespan                │
│  /api/merchants  /api/underwrite/{id}  /api/whatsapp │
│  /api/offer/accept  /api/audit-log  /api/dashboard   │
└───┬──────────┬──────────┬──────────┬─────────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
 scoring    underwriting  whatsapp   audit
 engine     agent         (Twilio)   (JSONL)
    │          │
    ▼          ▼
 merchant    Claude API
 profiles    (rationale)
 + benchmarks
```

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `server.py` | 530 | FastAPI server — all endpoints, WhatsApp integration, NACH mandate, audit logging |
| `underwriting_agent.py` | 579 | Core agent — offer generation, Claude rationale prompts, deterministic fallback |
| `scoring_engine.py` | 458 | 6-factor weighted scoring with category benchmarks and hard rejection rules |
| `merchant_profiles.py` | 330 | 10 merchant profiles, category benchmarks, derived metrics computation |
| `test_scoring.py` | 232 | Standalone scoring validation — verifies all 10 merchants hit expected tiers |
| `schemas.py` | 199 | Pydantic models for type safety and API documentation |
| `dashboard.html` | 158 | Single-file React dashboard (Babel-transpiled, no build step) |

---

## How to Run

### Prerequisites

- Python 3.10+
- Anthropic API key (for Claude-powered rationale — works without it using fallback)
- Twilio account (for live WhatsApp — works without it in simulation mode)

### Setup

```bash
git clone <repo-url> && cd grabon-underwriting-agent
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
python server.py
```

The server pre-loads all 10 merchants with underwriting decisions on startup. Open `http://localhost:8000`.

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Optional | Claude API for rich rationale narratives. Without it, the agent uses deterministic fallback that still references specific data points. |
| `TWILIO_ACCOUNT_SID` | Optional | Twilio sandbox for live WhatsApp delivery. Without it, messages are formatted and logged but not sent. |
| `TWILIO_AUTH_TOKEN` | Optional | Twilio auth. |
| `TWILIO_WHATSAPP_FROM` | Optional | Default: `whatsapp:+14155238886` (Twilio sandbox number). |

---

## Design Decisions

### Why deterministic scoring + AI rationale (not end-to-end LLM)?

The tier assignment and offer parameters (credit limit, interest rate, premium) are **deterministic** — driven by explicit formulas with traceable weights. This is intentional for a financial product: an underwriting decision must be auditable, reproducible, and explainable to a regulator. Claude generates the narrative rationale layer on top, not the decision itself. If the LLM is unavailable, the fallback rationale still references the exact same data points — no quality cliff.

### Why 6 scoring factors with explicit weights?

Each factor maps to a real underwriting concern: Can the merchant sustain repayments (GMV stability)? Is the business growing or declining (growth trajectory)? Do customers come back (loyalty)? Are there operational issues (refund risk)? Is the merchant committed to GrabOn (platform commitment)? Do we have enough data to decide (data sufficiency)? Evaluators can inspect each score and understand exactly why a merchant landed in a specific tier.

### Why hard rejection rules?

Two scenarios should never reach scoring: a merchant with only 3 months of data (NovaTech — we literally cannot assess them), and a merchant in catastrophic decline with extreme refund rates (LuxeThread — the scoring math would reject them anyway, but a hard rule makes the rejection reason clearer and the code more defensive). These are separate failure modes with separate explanations.

### Why category benchmarks?

A 5% refund rate means very different things in Fashion (below average) vs Food (above average). Every scoring function compares the merchant's metrics against their category benchmark, not an absolute threshold. This is how real underwriting works — a travel business with seasonal GMV swings (WanderLust) shouldn't be penalized the same way as a food business with the same volatility.

### Why single-file dashboard with no build step?

The evaluator will `git clone` and `python server.py`. No `npm install`, no webpack, no Vite config. The dashboard loads React + Babel from CDN and renders directly. One less thing to break during evaluation.

---

## 10 Merchant Profiles

| Merchant | Category | Tier | Score | Key Signal |
|----------|----------|------|-------|------------|
| TrendVault Fashion | Fashion | Tier 1 | 83.1 | 29.6% growth, 3.1% refund (vs 8% avg) |
| FreshBasket Foods | Food | Tier 1 | 90.1 | Highest score — low volatility, 1.8% refund |
| MediCare Plus | Health | Tier 1 | 82.8 | 29.9% growth, strong loyalty (72%) |
| WanderLust Travels | Travel | Tier 2 | 71.6 | 81.5% growth but extreme seasonality (CV: 0.516) |
| GadgetWorld Electronics | Electronics | Tier 2 | 71.9 | Decent GMV but 6.5% refund above benchmark |
| GlowUp Beauty | Beauty | Tier 2 | 70.2 | Small but growing; low exclusivity (28%) |
| PixelArena Gaming | Gaming | Tier 3 | 49.3 | Volatile GMV, 25% repeat rate, 9.2% refund |
| QuickBite Snacks | Food | Tier 3 | 44.7 | **Declining** -22.9% growth, 7.1% refund |
| LuxeThread Couture | Fashion | **Rejected** | 23.3 | -60% GMV decline + 14.5% refund = hard reject |
| NovaTech Accessories | Electronics | **Rejected** | 44.6 | Only 3 months data = insufficient for underwriting |

### Edge Cases

- **WanderLust Travels** — High growth (81.5%) looks great on paper, but CV of 0.516 is extreme. The scoring engine applies a travel-category seasonality adjustment (reduces effective CV by 40%) so it doesn't get falsely rejected. Still lands at Tier 2, not Tier 1.

- **Two distinct rejection reasons** — LuxeThread is rejected for *financial deterioration* (declining GMV + high refunds). NovaTech is rejected for *data insufficiency* (3 months). Different failure modes, different explanations, different remediation paths.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/merchants` | All merchants with profiles, metrics, and latest decisions |
| `GET` | `/api/merchants/{id}` | Single merchant detail |
| `POST` | `/api/underwrite/{id}` | Run underwriting (body: `{mode, use_claude}`) |
| `POST` | `/api/underwrite-all` | Batch underwrite all 10 merchants |
| `POST` | `/api/whatsapp/send/{id}` | Send offer via WhatsApp (body: `{mode}`) |
| `POST` | `/api/offer/accept/{id}` | Accept offer → NACH mandate (body: `{mode, bank_account_last4}`) |
| `GET` | `/api/audit-log` | Full audit trail (query: `?merchant_id=&action=&limit=`) |
| `GET` | `/api/dashboard/summary` | Aggregated stats for dashboard |
| `GET` | `/api/decisions` | All underwriting decisions |
| `GET` | `/health` | Server health + config status |

Interactive API docs: `http://localhost:8000/docs`

---

## What I Would Do Differently With More Time

1. **Real PayU sandbox integration** — The credit disbursement flow currently ends at NACH mandate initiation. With more time, I'd integrate PayU's sandbox for actual payment flow simulation.

2. **Claude-generated rationale with few-shot examples** — The current prompt is zero-shot. Adding 3–4 exemplar rationale narratives per tier in the system prompt would make Claude's output more consistent and analyst-like.

3. **Persistent storage** — Decisions are in-memory and reset on server restart. I'd add SQLite or a simple JSON file store so the audit trail survives restarts.

4. **Streaming rationale** — Currently the agent waits for Claude's full response before returning. Server-sent events (SSE) would let the dashboard show the rationale streaming in real-time.

5. **MCP server wrapping** — The brief asks for MCP-spec compliance. I'd wrap the underwriting agent as a proper MCP tool that Claude Desktop can connect to, enabling natural language queries like "Underwrite GRB-M004 for insurance."

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Pydantic, httpx
- **AI:** Claude Sonnet (claude-sonnet-4-20250514) via Anthropic API
- **WhatsApp:** Twilio REST API (sandbox mode)
- **Frontend:** React 18, Babel standalone (CDN, no build step)
- **Audit:** Append-only JSONL logging
