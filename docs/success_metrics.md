# 90-Day Post-Launch Success Metrics

These metrics cover the first 90 days after the Livability Risk Engine Chicago MVP goes live with real customers. All metrics tie directly to the buyer personas in `docs/buyer_personas.md` and the pricing tiers in `docs/pricing_model.md`. The goal is to know within 30 days whether the GTM motion is working and have enough time to course-correct before day 90.

---

## Primary KPIs (review weekly)

### 1. Paying customers

**Target**: 10 paying customers by day 90.

**Breakdown by tier**:
- Spot: 5+ customers (self-serve, low friction, proof of demand)
- Professional: 3+ customers ($299/mo, meaningful MRR signal)
- Enterprise: 1+ customer (first annual contract, proof of B2B repeatability)

**Why this matters**: Ten paying customers at any mix of tiers validates that the product solves a real pain, that buyers can complete the purchase motion, and that at least one segment is showing repeatable demand.

**Leading indicator (day 30 checkpoint)**: At least 3 paying customers by day 30. If fewer than 3, diagnose: is the problem awareness, demo conversion, or pricing friction?

---

### 2. Monthly Recurring Revenue (MRR)

**Target**: $3,000 MRR by day 90.

**How it breaks down**:
- 5 Spot customers at average $50/mo usage = $250
- 3 Professional customers = $897
- 1 Enterprise at $1,500/mo = $1,500
- Overage and misc = ~$350+

**Why this matters**: $3,000 MRR is modest but real — it confirms buyers find the product worth a recurring commitment, not just a one-time trial.

**Leading indicator (day 30 checkpoint)**: At least $500 MRR by day 30 (1 Professional + a few Spot signups). If MRR is zero at day 30, the pricing or acquisition motion needs adjustment.

---

### 3. Design-partner feedback sessions completed

**Target**: 3 structured feedback sessions (one per persona) by day 45.

**What counts**: A 30-minute call where the design partner walked through the output on at least 5 real addresses from their workflow and shared explicit feedback on signal quality, missing context, or integration friction.

**Why this matters**: Design-partner feedback is the primary product input for the first iteration. Without it, the team is guessing about what to improve.

**Leading indicator (day 14 checkpoint)**: At least 2 design-partner pilots underway (signed or verbally committed) by day 14 of outreach.

---

### 4. API call volume per paying customer

**Target**: Average 50+ calls/month per paying customer by day 90.

**Why this matters**: Low call volume (< 10 calls/month) suggests the product is not yet embedded in a real workflow — buyers tried it but did not integrate it. High call volume (> 100 calls/month) signals a workflow dependency that makes churn less likely.

**Leading indicator**: Track calls per customer weekly starting from day 1. Flag any customer with fewer than 5 calls in their first two weeks as at-risk for churn before their first renewal.

---

### 5. Score accuracy complaints

**Target**: Fewer than 3 accuracy complaints in the first 90 days.

**What counts as a complaint**: A design partner or paying customer explicitly flags that the disruption score for a specific address was materially wrong in a way that affected a real decision.

**Why this matters**: The scoring model is heuristic-based and will not be perfect. But if complaints come in early and frequently, the confidence calibration or explanation copy needs adjustment before the product is shown to more buyers.

**Leading indicator**: After each design-partner session, ask directly: "Was there any address where the score felt clearly wrong?" Log every response, not just formal complaints.

---

## Secondary metrics (review monthly)

| Metric | Day 30 target | Day 90 target |
| --- | --- | --- |
| Demo-to-trial conversion rate | — | ≥ 40% |
| Trial-to-paid conversion rate | — | ≥ 30% |
| Inbound demo requests | 3 | 15 |
| Referrals from design partners | 0 | 2 |
| Net Promoter Score (informal) | — | Positive (most partners would recommend) |

---

## What success looks like at day 90

**Minimum viable success**: 5 paying customers, $1,500+ MRR, 3 design-partner sessions complete, fewer than 3 accuracy complaints. This is enough to justify the next build cycle with confidence.

**Base case success**: 10 paying customers, $3,000+ MRR, at least one customer using the API more than 100 times per month. This is enough to begin Series A or seed fundraising conversations.

**Strong success**: 15+ paying customers, $5,000+ MRR, 1 Enterprise contract signed, 2+ referrals from design partners. This is enough to start hiring for data engineering or sales.

---

## Course-correction triggers

If any of the following are true at the day-30 checkpoint, the team should explicitly discuss a response:

- **Zero paying customers at day 30**: Stop outreach and run 5 discovery calls with non-paying prospects to understand if it is a fit, pricing, or awareness problem.
- **Three or more accuracy complaints in the first 30 days**: Pause new outreach and prioritize a confidence-calibration fix before the next demo.
- **No design-partner feedback sessions by day 30**: Simplify the pilot ask — offer to score 10 addresses for free in exchange for a 15-minute async Loom review instead of a live call.
- **High trial signups but zero conversions to paid**: The pricing step is broken — investigate whether the self-serve billing flow works and whether the value at Spot tier is clear enough to justify $0.10/call.
