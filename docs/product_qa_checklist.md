# Product QA Checklist

Use this checklist when reviewing mocked or future live `/score` responses for the Chicago MVP.

## Trust and interpretation checks
- Does the score band match the explanation tone?
- Does the explanation sound appropriately cautious for low-confidence cases?
- Does the output avoid sounding more certain than the underlying evidence supports?
- Would a normal homebuyer understand the headline takeaway without seeing internal model details?

## Confidence checks
- Does the confidence label match the quality of the source evidence?
- Does the confidence label reflect timing specificity, not just severity?
- Does precise address-level and date-level evidence score more confidently than broad permit evidence?

## Top-risk checks
- Are the top risks understandable to a normal homebuyer?
- Are the top risks phrased as practical impacts rather than internal system terms?
- Do the top risks reinforce the same dominant driver described in the explanation?

## Category and severity checks
- Are risk categories internally consistent across score, severity, top risks, and explanation?
- Does `traffic` behave like access friction rather than general neighborhood inconvenience?
- Do `noise` and `dust` only rise when the supporting work type reasonably suggests those impacts?
- Are HIGH severity labels reserved for clearly decision-relevant disruption?

## QA address review checks
- For each of the 18 QA addresses, is the expected disruption tier still plausible?
- Do high-band examples feel materially more disruptive than moderate-band examples?
- Do low-band examples avoid alarming language unless evidence clearly warrants it?

## Output discipline checks
- Does the response stay inside the documented API contract?
- Is the explanation short, concrete, and deterministic?
- Would the response still feel credible if shown in a buyer-facing demo?

---

## Live-output trust review process (product-026)

Use this process whenever the backend is connected to a live DB and before
any investor or design-partner demo. The goal is to confirm outputs are
believable, not to validate ground truth.

### Who runs this
Any product or app team member. Does not require data engineering involvement.
Tools needed: a running backend with `POSTGRES_HOST` set, and access to
`docs/04_api_contracts.md` for the approved score bands.

### Step 1 — Confirm the backend is in live mode
Run the `/health` check from `docs/handoffs/app.md`. Confirm:
- `db_configured: true`
- `db_connection: true`

If either is false, do not proceed with the trust review — there is no live output to evaluate.

### Step 2 — Score all four canonical addresses
Run `/score` for each of the four approved demo addresses from `docs/04_api_contracts.md`:

| Address | Expected band | Expected dominant signal |
|---|---|---|
| 11900 S Morgan St, Chicago, IL | Low (0–24) | None / very weak |
| 3150 N Southport Ave, Chicago, IL | Moderate (25–49) | Noise |
| 1600 W Chicago Ave, Chicago, IL | High (50–74) | Traffic |
| 1200 W Fulton Market, Chicago, IL | Severe (75–100) | Traffic + noise |

### Step 3 — Apply plausibility checks to each response
For each address, check:
- [ ] `disruption_score` falls within the expected band (±10 is acceptable for live data; ±20 warrants a flag)
- [ ] `confidence` is consistent with evidence quality — Low addresses should be LOW, high addresses MEDIUM–HIGH
- [ ] `severity` fields reflect the dominant signal (e.g. High address should have at least one HIGH severity dim)
- [ ] `explanation` tone matches the score band (see tone guide in `docs/03_scoring_model.md`)
- [ ] `top_risks` strings are buyer-readable — no schema terms, no raw field names
- [ ] `mode` is `"live"` and `fallback_reason` is null — if not, address this before the demo

### Step 4 — Apply the red-flag checklist from the QA review section above
Any red flag (e.g. Severe score with LOW confidence, traffic HIGH but no closure in top_risks)
must be investigated before the demo proceeds.

### Escalation path for suspicious outputs
If a response looks implausible:
1. Run `/debug/score` on the same address and check `nearby_projects_count` and `nearby_projects_sample`.
2. If count is 0 — the ingest pipeline may not have run or the address is outside the data coverage area. Flag to the data lane.
3. If count > 0 but the score seems wrong — check the project `impact_type` and `distance_m` in the sample against the scoring rubric in `docs/03_scoring_model.md`.
4. If the explanation is off-tone but the score is plausible — this is a scoring engine calibration issue; document it and defer to a post-launch fix rather than blocking the demo.
5. If the response returns `mode: "demo"` when live is expected — check `/health` and the backend logs. This is a configuration issue, not a data issue.

### Recommended cadence
- Run before every investor or design-partner demo.
- Run once after each data ingest cycle (after data-010 freshness checks are in place).
- Take no more than 15 minutes end-to-end.

---

## Pre-demo launch-readiness checklist (product-029)

Run this checklist before every investor or design-partner meeting where the
live product will be shown. Target: complete in under 5 minutes.

**Why this matters**: The most common demo failure for early-stage API products
is presenting a "live" demo that is silently in demo mode. This checklist
prevents that.

### Backend readiness
- [ ] `GET /health` returns `db_connection: true`
  - If false: **do not present as live**. Use the approved fallback script below.
- [ ] `GET /health` returns `mode: "live"`
- [ ] `/score` response for `1600 W Chicago Ave, Chicago, IL` includes `"mode": "live"`
- [ ] `/debug/score` for the same address shows `nearby_projects_count > 0`

### Frontend readiness
- [ ] Frontend is running and connects to the correct backend URL (`NEXT_PUBLIC_API_URL`)
- [ ] Submitting `1600 W Chicago Ave, Chicago, IL` renders a result (not an error state)
- [ ] The mode badge shows **"Live data"** in the results area
- [ ] Browser console shows no `[LRE] backend fallback_reason` log (or fallback_reason is expected and understood)

### Demo content readiness
- [ ] Presenter has reviewed `docs/demo_script.md` for talking points
- [ ] At least 3 example addresses are ready: one from each of Low, Moderate, High bands
- [ ] The Severe band example (1200 W Fulton Market) is also queued if the demo includes the full range

### If the backend is in demo mode (approved fallback messaging)
If `db_connection: false` or `mode: "demo"`, use this language:

> "The scoring engine is in demonstration mode today, which means we're showing
> you our approved representative outputs rather than a live database query.
> These responses reflect the same scoring logic and explanation templates the
> live system uses — the data connection is the only difference. We can schedule
> a live-data session once the database is fully provisioned."

**Do not** present demo mode outputs as live scores without this disclosure.

### Weekly cadence note
Consider running this checklist as part of any standing weekly meeting where a
demo may be requested, not only immediately before a scheduled call. This avoids
last-minute scrambles when a DB connection issue surfaces 10 minutes before a meeting.

---

## Score review workflow for golden addresses (product-030)

Use this workflow to validate scoring quality against a fixed set of canonical
Chicago addresses after any data ingest or backend change.

### Golden address set
Selected from the 18-address QA set in `docs/03_scoring_model.md` to span the
full score range with clear real-world rationale.

| # | Address | Expected band | Expected dominant signal | Confidence |
|---|---|---|---|---|
| 1 | 1600 W Chicago Ave, Chicago, IL | High (50–74) | Traffic | MEDIUM |
| 2 | 1200 W Fulton Market, Chicago, IL | Severe (75–100) | Traffic + noise | MEDIUM–HIGH |
| 3 | 111 N Halsted St, Chicago, IL | Moderate (25–49) | Noise | MEDIUM |
| 4 | 3150 N Southport Ave, Chicago, IL | Moderate (25–49) | Noise | LOW–MEDIUM |
| 5 | 11900 S Morgan St, Chicago, IL | Low (0–24) | None / minimal | LOW |
| 6 | 5800 N Northwest Hwy, Chicago, IL | Low (0–24) | None / minimal | LOW |

Addresses 1–2 anchor the high end. Addresses 3–4 anchor the moderate band.
Addresses 5–6 anchor the low end. This set exercises the full output range
without requiring all 18 addresses.

### How to run the review

1. Confirm `/health` shows `db_connection: true` (live mode only).
2. For each address, run `GET /score?address=<address>` and record the response.
3. Apply the checks below for each response.
4. Flag any address that falls outside its expected band by more than 10 points.

### Per-address checks
- [ ] `disruption_score` is within ±10 of the expected band midpoint
- [ ] `mode` is `"live"` and `fallback_reason` is null
- [ ] `confidence` matches the expected level for this band
- [ ] `severity` reflects the expected dominant signal
- [ ] `explanation` tone matches the band (see tone guide in `docs/03_scoring_model.md`)
- [ ] `top_risks` are buyer-readable with no schema terms

### Flagging and escalation
- A single address outside band by 10–20 points: **document, monitor next ingest**
- Two or more addresses outside band, or any address outside by >20 points: **flag to data lane before demo**
- Any golden address returning `mode: "demo"` when live expected: **check /health and data pipeline**

### Review cadence
- After each data ingest cycle
- After any backend scoring code change
- Before any investor or design-partner demo (combined with pre-demo checklist above)
- This review should take under 10 minutes for all 6 addresses
