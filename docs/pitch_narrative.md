# Investor-Facing Pitch Narrative

## The problem

Every day in Chicago, permits are issued and streets are closed for construction work that will materially disrupt the people and businesses nearby. There is no simple, reliable way to know — in advance — how badly a specific address will be affected.

A real estate investor closing a $3M deal does not know whether a full street closure starts next week on the block they are buying. A logistics company routing 500 deliveries a day does not know which addresses will have their curb lane blocked tomorrow. A tenant signing a two-year lease does not know whether the next six months will include a demolition project 80 meters from their window.

This information exists. It is sitting in Chicago's public permit and street closure databases, updated daily. The problem is that no one has assembled it into a fast, accurate, interpretable signal — until now.

---

## The solution

**Livability Risk Engine** turns Chicago's raw permit and street closure data into a single, quantified disruption risk score for any address.

One API call. One score (0–100). Five structured fields. Under 500ms.

```
GET /score?address=1600+W+Chicago+Ave+Chicago+IL

→ disruption_score: 62
→ confidence: MEDIUM
→ severity: { traffic: HIGH, noise: LOW, dust: LOW }
→ top_risks: ["2-lane closure within 120m", "Active through 2026-03-22", ...]
→ explanation: "A nearby lane closure is the main driver..."
```

The model scores proximity, scale, and timing of every nearby permit and closure record, then returns a structured, plain-English result that any buyer, analyst, dispatcher, or product team can act on immediately.

---

## Why now

Three conditions make this the right moment to build and sell this product:

1. **The data is free and structured.** Chicago's Socrata open data portal provides machine-readable permit and closure records updated daily. No scraping, no partnerships, no licensing fees. The raw material is free.

2. **The decision-makers are ready.** Post-COVID, urban disruption anxiety is elevated. CRE buyers are more diligent. Logistics operators face tighter SLAs. Proptech platforms are under pressure to add differentiated local signals. Willingness to pay for a clean disruption signal has never been higher.

3. **No one has built this cleanly.** Existing solutions are either raw data portals (unstructured, slow, non-quantified) or enterprise GIS platforms (expensive, general-purpose, not optimized for disruption scoring). A lightweight, API-first disruption score product does not exist in the market today.

---

## Market opportunity

**Immediate addressable market (Chicago MVP)**:
- ~800 active CRE investment and brokerage firms in the Chicago metro area
- ~150 logistics and last-mile delivery operators active in Chicago
- ~200 proptech and mobility platform builders with Chicago coverage

Conservative early revenue assumption at $300 average MRR per paying customer:
- 50 paying customers = **$15,000 MRR / $180,000 ARR**
- 200 paying customers = **$60,000 MRR / $720,000 ARR**

This is a Chicago-only, API-only MVP. Multi-city expansion is a deliberate next chapter, not a prerequisite.

---

## What we are asking for

The Chicago MVP is 8 weeks to a working, demo-ready API with a validated data pipeline, a production-grade `/score` endpoint, and a polished frontend demo. The core infrastructure is already partially built.

**What we need**:
- Seed capital or a paid pilot commitment to complete the 8-week build
- One or two design-partner customers from the CRE or logistics segment who will provide feedback and pay a reduced early-access rate
- Any warm introductions to Chicago-area CRE funds, logistics operators, or proptech founders who could be early customers

**What we offer in return**:
- A working API before a single dollar of customer revenue is collected
- A transparent, auditable data pipeline built entirely on public city data — no vendor lock-in
- First-mover advantage in a city with some of the richest public construction data in the US

---

## Team and traction

- 3-person team with a clear lane structure: Product, Data, and App
- MVP data pipeline targeting Chicago building permits and street closures — both sources live
- Frontend demo and mocked API endpoint already running
- Scoring model, confidence rubric, and explanation templates fully documented and reviewable
- No venture baggage, no prior pivots, no technical debt on the critical path

The Chicago MVP is a focused, buildable, defensible starting point for a category that has not been clearly named yet. We are calling it **disruption intelligence** — and we intend to own it.
