# Proposed Pricing Model and Go-to-Market Packaging

This document defines the proposed pricing concept and go-to-market motion for the Livability Risk Engine. It is a roadmap and sales-planning artifact, not a statement of currently automated billing behavior.

Current stage: design-partner pilots. API keys, batch endpoints, and usage counters exist, but paid subscriptions, monthly quota enforcement, overages, self-serve billing, and plan-specific entitlements are not yet enforced by the backend. Pilot usage should be monitored manually with each partner.

---

## Pricing philosophy

**Charge for API calls, not seats.**

The core unit of value is a score lookup for a specific address. Buyers understand this intuitively — they pay more when they use it more. It also lets us capture value from bulk use cases (CRE portfolio reviews, batch logistics planning) without gating the product behind a high monthly minimum that slows adoption.

Secondary axis: response freshness. Customers who want guaranteed same-day data pay a premium. Customers who can tolerate 48-hour-old data pay less. This maps directly to our daily ingest cadence and lets us charge for the operational investment in keeping data current.

---

## Proposed pricing tiers

### Tier 1 — Spot (self-serve, usage-based)

**Target**: Individual CRE analysts, small logistics teams, solo developers evaluating the API.

**Price**: $0.10 per API call, no monthly minimum.

**Included**:
- Full `/score` response with all five fields
- Standard data freshness (refreshed within 48 hours)
- 100 free calls/month to enable evaluation

**Rationale**: Removes friction for a single analyst or developer to try the product without a contract. $0.10/call is priced below the cost of 30 seconds of analyst time ($250/hr = $0.07/min), making the ROI calculation trivial.

**Monthly revenue range**: $10–$500 per customer depending on use volume.

---

### Tier 2 — Professional (subscription, monthly)

**Target**: CRE firms running regular due diligence, mid-size logistics operators, and proptech platforms with moderate call volume.

**Price**: $299/month for 1,000 calls, then $0.08/call for overages.

**Included**:
- Everything in Spot
- Guaranteed data freshness (refreshed within 24 hours)
- Priority email support with 24-hour response SLA
- CSV batch submission for up to 100 addresses per request

**Rationale**: $299/month is a rounding error on a single CRE deal. It positions the product firmly in the "tools budget" of any analyst team, not the "software procurement" cycle. Overage pricing keeps us from leaving money on the table for seasonal or burst-volume customers.

**Monthly revenue range**: $299–$900 per customer at typical overages.

---

### Tier 3 — Enterprise (contract, annual)

**Target**: Large CRE firms, enterprise logistics companies, and proptech platforms with high call volume or white-label needs.

**Price**: Starting at $1,500/month (annual contract), custom quote above 10,000 calls/month.

**Included**:
- Everything in Professional
- Guaranteed data freshness (refreshed within 12 hours)
- Dedicated Slack or Teams support channel
- Custom SLA with uptime guarantee
- White-label API subdomain option (scores.yourcorp.com) for proptech embeds
- Quarterly data quality review call

**Rationale**: Enterprise contracts lock in predictable ARR and give us leverage to invest in reliability and SLAs. The white-label option is a meaningful differentiator for proptech customers who do not want to expose a third-party API in their own product.

**Annual contract range**: $18,000–$60,000/year depending on volume and SLA scope.

---

## Go-to-market motion

### Phase 1 — Design partner (weeks 1–4 after MVP launch)

**Goal**: Sign 3 paying design partners at reduced rate ($99–$199/month) who will use the API in a real workflow and provide structured feedback.

**Target**: One from each persona segment (CRE analyst, logistics operator, proptech builder).

**Motion**: Direct outreach from the founding team. Warm introductions from real estate networks, Chicago tech community, and proptech forums. Demo video shared on LinkedIn and Twitter/X targeting Chicago CRE and logistics communities.

**Success metric**: 3 signed design partners + at least 1 providing a usable testimonial within 4 weeks.

---

### Phase 2 — Self-serve onramp (post-pilot)

**Goal**: Enable Spot-tier self-serve so inbound interest converts without sales involvement.

**What is needed** (not MVP — these are post-MVP product decisions):
- API key provisioning and a lightweight developer dashboard
- Stripe or usage-based billing integration
- Public API documentation site

**Motion**: Developer content (blog post, Chicago Open Data community post) + Product Hunt launch + direct listings on API marketplaces (RapidAPI, Postman Public APIs).

**Success metric**: 20+ Spot-tier signups within 60 days of self-serve launch; 5+ converting to Professional.

---

### Phase 3 — Enterprise pipeline (months 3–6)

**Goal**: 3 Enterprise contracts signed, $5,000+ MRR committed annually.

**Target**: Chicago-area CRE funds ($50M+ AUM), mid-size courier and logistics operators, and proptech platforms with >10,000 monthly users in Chicago.

**Motion**: Warm introduction-led outreach using design partner references. Tailored demo using the buyer's own portfolio addresses as live examples. Anchor the pitch on time savings in due diligence or cost avoidance in dispatch.

**Success metric**: $15,000 MRR by month 6 post-launch (50 Professional + 3 Enterprise customers at blended $300 ARPU).

---

## Pricing defensibility

**Why buyers will not simply use the city portal instead**:
- The portal is unstructured, requires domain knowledge to interpret, and does not produce a quantified score.
- A single analyst hour costs $50–$250. The API costs $0.08–$0.10 per lookup. The ROI is not a close call.

**Why buyers will not build it themselves**:
- The ingestion, normalization, scoring, and API infrastructure takes 4–8 engineer-weeks to build cleanly.
- We maintain the data pipeline and handle source changes so they do not have to.
- The Professional tier costs less than one day of a mid-level engineer's time per month.

**Why this is hard to commoditize**:
- Data pipeline reliability and data quality are ongoing operational work, not a one-time build.
- The scoring rubric, confidence calibration, and explanation language are product-differentiated IP, not raw data.
- Customer inertia once embedded in a workflow is strong — switching costs are high once `/score` is in a real dispatch or diligence process.

---

## Revenue model summary

| Metric | Conservative | Base | Aggressive |
| --- | --- | --- | --- |
| Month 6 paying customers | 20 | 50 | 120 |
| Blended ARPU | $200 | $300 | $400 |
| Month 6 MRR | $4,000 | $15,000 | $48,000 |
| Month 12 ARR run rate | $48,000 | $180,000 | $576,000 |

These projections assume the current nationwide product direction with evidence depth varying by city and source. Growth is driven by the three buyer personas and the proposed pricing tiers defined above.
