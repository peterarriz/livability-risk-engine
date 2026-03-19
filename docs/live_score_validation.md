# Live Score Validation

Use this lightweight checklist after a deploy to confirm the live address flow is working and that the score output remains broadly plausible for a small set of Chicago QA addresses.

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

1. Start the backend and confirm `/health` reports `db_configured: true` and `db_connection: true`.
2. For each address, call `/score` or submit it through the frontend.
3. Record the returned `disruption_score`, `mode`, `confidence`, and dominant driver.
4. Mark the row `pass` only when all of the following are true:
   - `actual_mode` is `live`
   - `actual_score` is in or near the expected band
   - the dominant driver broadly matches the expectation
   - the explanation sounds plausible for the score band
5. If any row is a fail, capture the exact API response or screenshot and hand it off before changing scoring logic.

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
