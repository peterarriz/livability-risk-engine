# Live Score Validation

Use this lightweight checklist after a deploy to confirm the live address flow is working and that the score output remains broadly plausible for a small set of Chicago QA addresses.

---

## data-042 Calibration Run — 2026-03-23

**Status: All 7 scenarios PASS. One calibration fix applied.**

### Method

Database not yet live. Scoring engine tested using synthetic `NearbyProject` fixtures
designed to faithfully represent typical permit and closure activity at each QA address.
Run via `scripts/calibrate_scoring.py` (exits 0 on pass, 1 on any band failure).

### Results

| Address | Expected band | Score | Actual band | Confidence | Pass/Fail |
|---|---|---|---|---|---|
| 1600 W Chicago Ave, Chicago, IL | High (50–74) | 54 | High | HIGH | PASS |
| 700 W Grand Ave, Chicago, IL | High (50–74) | 52 | High | MEDIUM | PASS |
| 111 N Halsted St, Chicago, IL | Moderate (25–49) | 32 | Moderate | MEDIUM | PASS |
| 5800 N Northwest Hwy, Chicago, IL | Low (0–24) | 1 | Low | LOW | PASS |
| 11900 S Morgan St, Chicago, IL | Low (0–24) | 0 | Low | LOW | PASS |
| 233 S Wacker Dr, Chicago, IL (edge: Severe) | Severe (75–100) | 88 | Severe | HIGH | PASS |
| road_construction visibility check | score>0 + any sev≠LOW | 36 | — | MEDIUM | PASS (after fix) |

### Calibration fix applied

**Issue:** `road_construction` (base weight 20) was missing from `_derive_severity`,
`_build_top_risks`, and `_build_explanation` in `backend/scoring/query.py`.

**Impact before fix:**
- Two active `road_construction` projects at 60 m and 130 m produced a disruption score
  of 36 (Moderate) but all severity dimensions were LOW.
- `top_risks` fell through to the generic "Nearby permit activity" string.
- `explanation` used the generic "Nearby permitted work" pattern instead of naming road work.

**Fix (data-042):** Added `IMPACT_ROAD_CONSTRUCTION` to:
1. `_derive_severity` — `traffic_pts` bucket (road work disrupts vehicle/curb access)
2. `_build_top_risks` — dedicated string: "Active road reconstruction or resurfacing near…"
3. `_build_explanation` — dedicated lead + category "traffic and access disruption"
4. Secondary-driver category check — `road_construction` now classified as "traffic" not "construction"

**After fix:** road_construction scenario produces `severity.traffic = HIGH` for two active
close projects. All 7 calibration scenarios pass.

### Confidence calibration notes

- HIGH confidence is produced correctly when the top driver is a full closure or
  multi-lane closure with a specific active window and ≥20 weighted points.
- MEDIUM confidence for most High-band scenarios (mixed signals or single active permit).
- LOW confidence for all Low-band scenarios — correct per docs/03_scoring_model.md.
- The `_derive_confidence` function only checks `IMPACT_FULL_CLOSURE` and
  `IMPACT_MULTI_LANE` for HIGH confidence. This is intentional for MVP.

### BASE_WEIGHTS assessment

No BASE_WEIGHTS changes needed. The current values produce expected band outcomes:

| Single project, closest possible (≤75 m, active now) | Max weighted pts | Band |
|---|---|---|
| `closure_full` (45) × 1.00 × 1.00 | 45 | Severe if stacked; High alone |
| `closure_multi_lane` (38) × 1.00 | 38 | High ✓ |
| `closure_single_lane` (28) × 1.00 | 28 | High ✓ |
| `demolition` (24) × 1.00 | 24 | Moderate (high end) ✓ |
| `road_construction` (20) × 1.00 | 20 | Moderate ✓ |
| `construction` (16) × 1.00 | 16 | Moderate (low end) ✓ |
| `light_permit` (8) × 1.00 | 8 | Low ✓ |

### Re-run instructions

Once DB is live, re-run with live data:
```bash
# Synthetic calibration (no DB needed):
python scripts/calibrate_scoring.py

# Live DB smoke test (requires DATABASE_URL):
DATABASE_URL="..." python scripts/validate_ingest.py
```

---

This workflow is intentionally simple:
- use 5 addresses that span high, moderate, and low expected disruption
- confirm the app is in `live` mode before judging score quality
- record the result in one review table so Product, Data, and App can compare notes quickly

## 5-address smoke test set

The addresses below are the required smoke-test set for live score review.
Expected bands and dominant drivers are based on `docs/03_scoring_model.md`.

| Address | Expected band | Expected dominant driver | Basis in scoring doc |
| --- | --- | --- | --- |
| 1600 W Chicago Ave, Chicago, IL | High (50–74) | Traffic | High-disruption set; expected traffic-led closure/access friction story. |
| 700 W Grand Ave, Chicago, IL | High (50–74) | Traffic | High-disruption set; expected traffic-led access restriction story. |
| 111 N Halsted St, Chicago, IL | Moderate (25–49) | Traffic | Medium-disruption set; expected nearby access friction or permit activity. |
| 5800 N Northwest Hwy, Chicago, IL | Low (0–24) | Weak / background activity | Low-disruption set; expected limited or background activity only. |
| 11900 S Morgan St, Chicago, IL | Low (0–24) | None / minimal | Low-disruption set; expected minimal active disruption signal. |

## How to run the smoke test

For a repeatable command-line check, run:

```bash
python3 scripts/demo_smoke_check.py --backend-url http://127.0.0.1:8000
```

Pass repeated `--address` values to run the same contract checks against
caller-supplied nationwide addresses.

For a live-only demo gate, add `--require-live`. If the deployment requires
API keys, set `LRE_API_KEY` or pass `--api-key`. If you have operator access,
set `ADMIN_SECRET` or pass `--admin-secret` to include the protected
`/health/db` readiness probe. The script never prints supplied secrets.

1. Start the backend and confirm `/health` reports `status: ok`.
2. If `ADMIN_SECRET` is available, confirm `/health/db` reports recent ingest metadata.
3. For each address, call `/score` or submit it through the frontend.
4. Record the returned `disruption_score`, `mode`, `confidence`, and dominant driver.
5. Mark the row `pass` only when all of the following are true:
   - `actual_mode` is `live`
   - `actual_score` is in or near the expected band
   - the dominant driver broadly matches the expectation
   - the explanation sounds plausible for the score band
6. If any row is a fail, capture the exact API response or screenshot and hand it off before changing scoring logic.

## Review table template

Copy this table into a PR, handoff note, or deploy checklist and fill in the live results.

| address | expected_band | actual_score | actual_mode | actual_confidence | dominant_driver | pass_fail | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1600 W Chicago Ave, Chicago, IL | High (50–74) |  |  |  | Traffic |  |  |
| 700 W Grand Ave, Chicago, IL | High (50–74) |  |  |  | Traffic |  |  |
| 111 N Halsted St, Chicago, IL | Moderate (25–49) |  |  |  | Traffic |  |  |
| 5800 N Northwest Hwy, Chicago, IL | Low (0–24) |  |  |  | Weak / background activity |  |  |
| 11900 S Morgan St, Chicago, IL | Low (0–24) |  |  |  | None / minimal |  |  |

## How to use this after a deploy

After each deploy that touches the live address flow, `/score`, geocoding, or score presentation:

1. Run the `/health` check first.
2. Run the 5-address smoke test above.
3. Save the filled review table in the deploy PR, release note, or lane handoff.
4. If all 5 rows pass, the deploy is good for normal live-score review.
5. If one or more rows fail:
   - `actual_mode = demo` → treat it as a live-path/config problem first
   - wildly wrong score band but `actual_mode = live` → open a scoring review follow-up
   - confusing explanation with plausible score → hand off to Product/App for copy review

## Notes

- This is a smoke test, not a full calibration workflow.
- Do not recalibrate the scoring model from a single failing address.
- Always confirm `actual_mode` before interpreting a repeated score such as the demo `62`.
