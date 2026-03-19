# Competitive Positioning Brief

This document defines how the Livability Risk Engine is positioned against the alternatives a buyer is likely already using or considering. Use it to sharpen the pitch, handle objections, and explain differentiation without overselling.

---

## Alternative 1 — The City of Chicago Data Portal (direct use)

**What it is**: The official city open data portal at `data.cityofchicago.org`. Buyers can search permit and closure records directly.

**Who uses it**: Analysts who already know the portal exists and are willing to manually interpret raw records.

**Why buyers still use it**: It's free, official, and technically has all the same underlying data.

**Why the Livability Risk Engine wins**:
- The portal is a raw record browser, not a scoring engine. A buyer must know what dataset to look for, which fields matter, how to assess proximity, and how to weigh multiple overlapping records — all manually.
- There is no quantified score. The output is a table of rows, not a signal a non-technical stakeholder can act on.
- A single lookup on the portal can take 15–45 minutes for someone unfamiliar with the data structure. Our API returns the same signal in under 500ms.
- The portal does not aggregate or rank signals by distance and timing relevance. We do.

**Positioning statement**: "We turn the city's raw data into a decision-ready signal. The portal gives you the ingredients; we give you the answer."

**Objection to handle**: "We can just use the city portal for free." → "Absolutely — and if you have an analyst who can spend 30–60 minutes per address parsing permit tables, that works. Our API handles that work in under a second, which matters when you're checking 50 addresses in a due diligence sprint or routing 200 deliveries a day."

---

## Alternative 2 — General GIS / Data Platforms (ArcGIS, Esri, CARTO)

**What they are**: Enterprise GIS platforms that can ingest the same city permit and closure data and visualize it on a map or in a dataset.

**Who uses them**: City planners, infrastructure teams, and large enterprises with GIS staff.

**Why buyers use them**: Powerful spatial analysis, visualization, and integration with other data sources.

**Why the Livability Risk Engine wins**:
- GIS platforms are general-purpose tools that require significant setup, expertise, and licensing cost ($5,000–$50,000+/year) to operationalize for a specific use case like disruption scoring.
- They produce maps and datasets, not API-ready scores. A non-technical CRE analyst or dispatch manager cannot self-serve on ArcGIS.
- We are purpose-built: our data model, scoring rubric, and output format are designed specifically for near-term construction disruption at the address level.
- Our Professional tier is $299/month. ArcGIS Online starts at ~$500/user/year for basic access, and operationalizing a custom disruption-scoring workflow on top costs far more.

**Positioning statement**: "GIS platforms give you the map. We give you the specific answer a buyer, analyst, or dispatcher actually needs."

**Objection to handle**: "We already have ArcGIS / an internal GIS team." → "That's great for spatial analysis and visualization. Our API adds an address-level disruption score as a data field you can pull into your existing workflow — it's not a replacement for GIS, it's an enrichment layer."

---

## Alternative 3 — Manual Research (analyst-driven, ad hoc)

**What it is**: An analyst or operations person manually checking city permit portals, news sources, Google Maps, or local blogs before a deal or dispatch decision.

**Who uses it**: Most buyers, most of the time, for most Chicago addresses right now.

**Why buyers use it**: It's free, flexible, and doesn't require learning a new tool.

**Why the Livability Risk Engine wins**:
- Manual research is slow (15–60 minutes per address), inconsistent (results depend on analyst skill), and not reproducible (there is no audit trail of what was checked).
- It misses signals that are in public data but not in obvious places — especially the Socrata permit feeds that most analysts don't know how to query.
- It scales poorly: checking 10 addresses manually is feasible; checking 100 is not.
- Our API creates a consistent, auditable, time-stamped signal for every address — repeatable by any team member without domain expertise.

**Positioning statement**: "We systematize what your best analyst does manually on their best day, and make it available for every address, every time."

**Objection to handle**: "Our team already does this kind of research." → "Exactly — and that tells us the need is real. The question is whether you want your analysts spending their time on data assembly or on the judgment call that comes after. We handle the assembly."

---

## Alternative 4 — PropTech Data Aggregators (CoStar, ATTOM, Regrid)

**What they are**: Commercial data providers that aggregate property, permit, and neighborhood data for the CRE and proptech markets.

**Who uses them**: CRE professionals and proptech platforms that already pay for data enrichment.

**Why buyers use them**: Broad property data coverage, established integrations, trusted brand.

**Why the Livability Risk Engine wins**:
- These platforms aggregate historical and general permit data, but do not specialize in near-term construction disruption scoring.
- Their data products are designed for property valuation and market analysis, not for flagging imminent access disruption at a specific address in the next 30 days.
- They are significantly more expensive ($500–$10,000+/month) and require a contract and sales process to access.
- We provide a purpose-built disruption score with daily-refreshed data and plain-English explanation — not a general property data field.

**Positioning statement**: "The big aggregators tell you what a property is worth and what permits it has had. We tell you what will happen to the block in the next 30 days."

**Objection to handle**: "We already have CoStar / ATTOM data." → "Those are great for property history and comps. We're adding a forward-looking signal that those platforms don't include — near-term disruption risk based on active permits and planned closures, updated daily."

---

## Summary: where we win and where we don't

| Situation | We win | We don't win |
| --- | --- | --- |
| Buyer needs a quantified, address-level disruption score | ✓ | |
| Buyer needs broad spatial analysis across a whole city | | ✓ Use GIS |
| Buyer needs a fast, API-ready signal for integration | ✓ | |
| Buyer needs historical property data or comp analysis | | ✓ Use aggregator |
| Buyer checks 10+ addresses in a single workflow | ✓ | |
| Buyer needs real-time GPS traffic or IoT sensor data | | ✓ Out of MVP scope |
| Buyer is outside Chicago | | ✓ Post-MVP |

**The clearest win**: a buyer who already does manual research or portal lookups and is frustrated by the time and inconsistency of that process. That is the fastest conversion.
