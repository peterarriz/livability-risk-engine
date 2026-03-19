# Product Lane Handoff Guide

## Mission
Keep Product work focused on scope clarity, scoring guidance, and demo-readiness without expanding the MVP.

## Completed in this handoff
- Added score interpretation bands so the 0–100 output has practical user-facing meaning.
- Added confidence language guidance, including evidence-quality drivers and API label mapping.
- Added a fixed MVP disruption taxonomy and clarified how the narrower API severity fields map to it.
- Added scoring assumptions v1 so Product, Data, and App can distinguish heuristics from known source facts.
- Added a concrete v1 weighting rubric covering base project weights, distance decay, time weighting, aggregation, and severity-alignment guardrails.
- Added explicit score-band threshold guidance and dominant-signal tie-break rules so Data and App can explain outputs consistently.
- Decided that buyer-facing `traffic` language should explicitly include curb and parking access when those impacts are materially part of the story.
- Added a Product QA checklist for trust, calibration, explanation tone, and category consistency reviews.
- Clarified the API contract so `disruption_score`, `confidence`, and `severity` are more interpretable without changing the response shape.
- Completed QA pass over all 18 Chicago QA addresses with expected score bands, dominant signals, confidence, and tone documented in `docs/03_scoring_model.md`.
- Approved the canonical demo example (1600 W Chicago Ave, High band) and four buyer-facing demo responses per score band in `docs/04_api_contracts.md`.
- **Monetization foundation complete**: buyer personas, investor pitch narrative, investor demo script, and pricing model are all documented in `docs/`.

## Launch-readiness questions (product-008)

These are the open questions that must be resolved — or explicitly accepted as known risks — before the MVP is demo-ready for investors or design partners.

### Data lane sign-off required
1. **Ingestion reliability**: Have building permits (data-002) and street closures (data-004) been successfully pulled into a running PostGIS instance at least once? If not, are the scripts confirmed error-free by Data?
2. **Geometry coverage**: What percentage of the permit and closure records in the raw tables have valid lat/lon? A geometry gap above ~30% would materially reduce score accuracy for many addresses.
3. **Freshness lag**: Is daily ingestion automated or manual for the MVP? If manual, what is the maximum acceptable data lag before a demo response becomes misleading?
4. **Normalization status**: Are data-005 (canonical projects table), data-006 (permit normalization), and data-007 (closure normalization) scheduled? App cannot wire the live `/score` endpoint until data-009 (radius query) is also complete.

### App lane sign-off required
5. **Mocked smoke check**: Has the mocked `/score` endpoint been verified against the canonical demo example (1600 W Chicago Ave, score 62) using the smoke-check steps in `docs/handoffs/app.md`?
6. **Demo fallback behavior**: When the live backend is unavailable, does the frontend gracefully display the approved demo data without surfacing a configuration error?
7. **API contract alignment**: Are all five response fields (`address`, `disruption_score`, `confidence`, `severity`, `top_risks`, `explanation`) rendered in the frontend with no missing or extra fields?

### Product decisions still open
8. **Design-partner timeline**: When does Product want to begin outreach to design-partner candidates? This determines whether the live backend or only the mocked demo is needed for first conversations.
9. **Demo address rotation**: Should the demo default to the approved 1600 W Chicago Ave example, or should presenters be able to enter any Chicago address live? (Live entry requires the real backend to be running.)
10. **Pricing tier sign-off**: Has the Spot/Professional/Enterprise tier structure in `docs/pricing_model.md` been reviewed by at least one other team member before any external pricing communication?

### Known accepted risks
- The MVP score is heuristic-based and will produce plausible but not perfectly accurate results for some addresses, especially those with sparse permit data.
- Confidence will be `LOW` or `MEDIUM` for most addresses until the canonical projects normalization pipeline is complete.
- The demo relies on mocked data if the live backend is not running — this is acceptable for early investor conversations but must be disclosed to design partners who expect live scoring.

## Still open

## Next product actions (updated 2026-03-19)
1. Run the live-output trust review (product-026) once the DB is connected — see `docs/product_qa_checklist.md`.
2. Confirm the selected design-partner persona and start outbound (product-027, product-028).
3. Run the pre-demo launch-readiness checklist before any investor or partner meeting (product-029, see `docs/product_qa_checklist.md`).
4. Review `docs/pricing_model.md` with the team before any external pricing communication.

## Design-partner list spec (product-028)

### Selected persona
**CRE Analyst** — the fastest path to revenue and feedback. See `docs/buyer_personas.md` for full profile.

### Ideal target profile
- **Title**: Research analyst, acquisitions associate, asset manager, or VP of Acquisitions
- **Company type**: CRE investment firm, REIT, property fund, or commercial brokerage with a Chicago portfolio
- **Chicago footprint indicator**: Active in Chicago acquisitions, lease renewals, or asset management; company has Chicago office or regional presence
- **Deal velocity**: Works on deals with 48–72 hour due diligence windows where a quick disruption signal would save time

### List-building criteria (for LinkedIn or CoStar prospecting)
1. Title contains one of: "real estate analyst", "acquisitions", "asset manager", "portfolio manager", "CRE"
2. Company is a known CRE firm, REIT, or investment fund with Chicago exposure
3. Individual is likely the buyer, not an IT gatekeeper — analyst or associate level preferred for first contact
4. Company size: 10–500 employees (large enough to have dedicated analysts; small enough for fast decisions)

### Next-step ask
A 20-minute discovery call to confirm the due diligence workflow and whether a `disruption_score` API would save time. **Do not pitch pricing on the first call.** Lead with the specific time savings for their existing workflow.

### Owner
Product lane. Outreach sequence uses `docs/outreach_templates.md` (CRE Analyst template).

### Build target
First 25 contacts. Quality over quantity — 25 well-matched targets beats 200 cold ones. Tie to pilot terms in `docs/pilot_terms.md` for any interested contact.

## What to hand off to other lanes
- To **Data**: keep the dominant-signal framing aligned with the score-band interpretation, confidence drivers, and severity mapping notes.
- To **App**: preserve the minimal response shape, but render score/confidence as user-facing trust signals rather than raw technical fields.

## Review checklist
- Does the task stay inside the Chicago MVP scope?
- Does it avoid changing the scoring model beyond documenting Product decisions?
- Is the next Product task specific enough for a human or AI agent to execute without guessing?
