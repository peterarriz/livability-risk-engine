# API Contracts

## `/score` endpoint
- **Method**: `GET`
- **Query param**: `address` (required, Chicago address string)

### Response fields
- `address`: normalized user input string echoed back in the response.
- `disruption_score`: integer from `0` to `100`. This is a practical near-term disruption indicator, not a scientific forecast of exact delay, decibel level, or project duration.
- `confidence`: `HIGH` | `MEDIUM` | `LOW`.
- `severity`: object with `noise`, `traffic`, and `dust`, each using `LOW` | `MEDIUM` | `HIGH`.
- `top_risks`: ordered list of up to 3 short plain-English risk bullets.
- `explanation`: 1 short paragraph explaining the dominant driver.

### Interpretation notes
- `disruption_score` should align with the score bands in `docs/03_scoring_model.md`: low, moderate, high, and severe.
- `disruption_score` should reflect the weighted contribution of the strongest nearby signals rather than a broad average of every weak record in the area.
- `confidence` should describe evidence quality and specificity, not severity. In the MVP, use:
  - `LOW` for stale, incomplete, or weakly located/timed evidence
  - `MEDIUM` for plausible but still somewhat ambiguous evidence
  - `HIGH` for recent, specific, and directly relevant evidence
- `severity.noise` reflects audible construction disruption.
- `severity.traffic` reflects access friction, including lane/street impacts and related curb-access disruption.
- In buyer-facing copy, `traffic` should be understood as **traffic and curb access** when parking, loading, pickup, or dropoff friction is part of the nearby disruption story.
- `severity.dust` reflects demolition, excavation, or similarly physical site activity likely to create dust or vibration nuisance.

### Example response
```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "disruption_score": 62,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "LOW",
    "traffic": "HIGH",
    "dust": "LOW"
  },
  "top_risks": [
    "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
    "Active closure window runs through 2026-03-22",
    "Traffic is the dominant near-term disruption signal at this address"
  ],
  "explanation": "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic disruption even though noise and dust are limited."
}
```

## Response conventions
- Keep the response minimal and demo-ready.
- `disruption_score` is the only numeric headline field returned to the frontend.
- The score should be interpretable by a non-technical reviewer without exposing raw model internals.
- `top_risks` should be implementation-ready display strings; the frontend should not need to reconstruct them from lower-level project data.
- `explanation` should be deterministic and consistent with the rules in `docs/03_scoring_model.md`.
- `explanation` should be led by the single dominant signal; only mention a secondary driver when it materially changes how a reviewer should interpret the address.
- When `severity.traffic` is driven mainly by curb occupancy or pickup/loading friction, the wording should say so explicitly instead of implying only broad roadway congestion.
