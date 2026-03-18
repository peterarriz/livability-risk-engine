# API Contracts

## `/score` endpoint
- **Method**: `GET`
- **Query param**: `address` (required, Chicago address string)

### Response fields
- `address`: normalized user input string echoed back in the response.
- `disruption_score`: integer from `0` to `100`.
- `confidence`: `HIGH` | `MEDIUM` | `LOW`.
- `severity`: object with `noise`, `traffic`, and `dust`, each using `LOW` | `MEDIUM` | `HIGH`.
- `top_risks`: ordered list of up to 3 short plain-English risk bullets.
- `explanation`: 1 short paragraph explaining the dominant driver.

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
- `top_risks` should be implementation-ready display strings; the frontend should not need to reconstruct them from lower-level project data.
- `explanation` should be deterministic and consistent with the rules in `docs/03_scoring_model.md`.
