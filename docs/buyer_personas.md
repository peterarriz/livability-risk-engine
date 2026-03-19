# Buyer Personas and Monetization Targets

This document defines the primary buyer personas for the Livability Risk Engine Chicago MVP. Every persona is anchored to a real decision that the `/score` output directly supports. No persona requires features beyond the MVP API contract.

---

## Persona 1 — The Commercial Real Estate Analyst

**Role**: Research analyst, acquisitions associate, or asset manager at a CRE firm, REIT, or property investment fund.

**Core pain**: Before closing a deal or renewing a lease, analysts spend hours manually checking city portals, calling permit offices, and scanning news for near-term construction risk near a target property. The signal they get is inconsistent, slow, and not quantified.

**Trigger event**: A deal is under contract or a portfolio review is in progress. The analyst has 48–72 hours to flag any near-term site risk that could affect tenant satisfaction, foot traffic, or closing price.

**What the MVP gives them**: A single `disruption_score` (0–100) with `confidence`, `severity`, and a plain-English `explanation` for any Chicago address — in under 500ms. They can instantly see whether a property is in a High or Severe disruption window before committing capital.

**MVP fields they care about most**:
- `disruption_score` — the headline go/no-go signal
- `severity.traffic` — access friction that affects tenants and deliveries
- `severity.noise` — quality-of-life signal for office and residential tenants
- `explanation` — the one-paragraph summary they can paste into a deal memo

**Estimated willingness to pay**: $200–$800/month for bulk address lookups (50–500 addresses/month) as part of a due diligence workflow. Single-address spot checks at $5–$15/call.

**Why they pay**: Time savings on due diligence ($250+/hour analyst time) and risk mitigation on deals where a bad call costs six figures or more.

---

## Persona 2 — The Urban Logistics Operations Manager

**Role**: City operations lead, fleet routing manager, or last-mile logistics planner at a courier, grocery delivery, or field-service company operating in Chicago.

**Core pain**: Street closures and permit work cause missed delivery windows, driver complaints, and rerouting costs. Dispatchers learn about closures reactively — from drivers radioing in, not from proactive planning data.

**Trigger event**: Planning weekly or daily dispatch routes; reviewing a new service zone; or responding to a customer complaint about chronic delivery delays at a specific address.

**What the MVP gives them**: On-demand disruption scoring for any delivery or service address in Chicago. A `disruption_score` above 50 at a frequently visited address is an early warning to pre-plan alternate routing or adjust delivery windows.

**MVP fields they care about most**:
- `disruption_score` — threshold trigger for route adjustment
- `severity.traffic` — the most direct signal for vehicle and curb access problems
- `top_risks` — the 1–3 bullets they can forward to a dispatcher or driver as context
- `confidence` — tells them how seriously to weight the signal vs. treat it as background noise

**Estimated willingness to pay**: $150–$500/month for a bulk address API integration in their dispatch system. Higher for enterprise contracts with SLA guarantees ($1,000–$3,000/month for dedicated access).

**Why they pay**: Each failed delivery costs $8–$25 in re-attempt labor. A single avoided disruption-driven failure day at a busy hub recovers weeks of subscription cost.

---

## Persona 3 — The Proptech or Mobility Platform Builder

**Role**: Product manager, data engineer, or founder at a proptech startup, rental platform, or mobility/mapping product that wants to embed a disruption signal into their own user experience.

**Core pain**: Their platform surfaces Chicago addresses (listings, routes, service areas) but has no reliable, machine-readable source of near-term construction disruption. Building their own ingestion pipeline would take months; buying a generic data feed produces too much noise.

**Trigger event**: A competitor adds neighborhood-quality signals; a user requests "is there construction nearby?" context in a listing; or the product team prioritizes local liveability signals for a new feature sprint.

**What the MVP gives them**: A clean JSON API they can integrate in one sprint — one GET request, one response, five meaningful fields. They embed the `disruption_score` and `explanation` directly into their UI without building any scoring logic.

**MVP fields they care about most**:
- All five response fields — they embed them wholesale into their product UI
- `top_risks` — the display strings they render as bullet points without reformatting
- `confidence` — a trust indicator they can surface to end users ("Data quality: Medium")

**Estimated willingness to pay**: $500–$2,000/month for API access (usage-based at 1,000–10,000 calls/month). Potential for revenue-share or white-label licensing on higher-volume integrations.

**Why they pay**: The alternative is a 2–3 month internal data pipeline build. The MVP API gives them launch-ready signal for the cost of one engineer-week in licensing fees.

---

## Summary: Monetization target stack

| Persona | Segment | Monthly ACV range | Volume potential | Acquisition motion |
| --- | --- | --- | --- | --- |
| CRE Analyst | Commercial real estate | $200–$800 | High (thousands of firms in Chicago metro) | Direct sales, broker partnerships |
| Logistics Ops Manager | Urban logistics / delivery | $150–$3,000 | Medium (dozens of operators, enterprise upside) | Direct sales, API marketplace listing |
| Proptech / Mobility Builder | B2B SaaS / developer | $500–$2,000 | Medium (100s of builders, high usage per customer) | API self-serve, developer docs, product-led growth |

**Priority for Chicago MVP monetization**: CRE analysts are the fastest path to revenue because they have an existing budget for due diligence data, their buying decision is individual (not IT procurement), and the MVP output maps directly to a quantifiable business risk they already manage. Logistics operators are the highest revenue ceiling but require more integration work. Proptech builders are the best word-of-mouth multiplier if the API is reliable and well-documented.

---

## Active outbound persona (product-027)

**Selected persona: The Commercial Real Estate Analyst**

**Selection rationale:**
- Fastest path to a paid design-partner relationship — budget exists, decision is individual, no IT procurement required
- The MVP output maps directly to a decision they make multiple times per week (deal-level risk review)
- `disruption_score` + `explanation` maps to a specific deliverable they already produce (deal memo language)
- First conversations can happen with or without a live DB — the approved demo response is credible enough for initial outreach
- Lowest friction from first contact to pilot agreement using `docs/pilot_terms.md`

**Primary MVP fields tied to this persona's pain:**
- `disruption_score` — the go/no-go headline signal for a deal under review
- `explanation` — the one-paragraph summary they paste into a deal memo
- `severity.traffic` — access friction affecting tenants, deliveries, and foot traffic

**Selection approved:** 2026-03-19

**Next step:** Use the CRE Analyst template in `docs/outreach_templates.md` and the list-building criteria in `docs/handoffs/product.md` to identify first 25 targets.
