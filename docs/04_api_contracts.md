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
- `mode`: `"live"` when the score was computed from the live database; `"demo"` when the approved fallback response was used. Added in app-019.
- `fallback_reason`: `null` when `mode` is `"live"`. A string explaining why demo mode was used when `mode` is `"demo"`. Values: `"db_not_configured"` | `"geocode_failed"` | `"scoring_error"`. Added in app-019.

**Backward compatibility**: `mode` and `fallback_reason` are additive fields. Existing consumers that do not read them are unaffected.

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

### Approved demo example (product-012)

The following response is the approved canonical example for demo walkthroughs and stakeholder reviews. It represents a High-band address with a dominant traffic signal. Use this example verbatim when demoing the API output.

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
    "Traffic and curb access are the dominant near-term disruption signals at this address"
  ],
  "explanation": "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic and curb access disruption even though noise and dust are limited."
}
```

**Why this example was chosen**: 1600 W Chicago Ave is a recognizable West Town arterial with documented active closure history, making it credible to a Chicago-area buyer or investor. The score of 62 sits clearly in the High band without overstating a Severe outcome, and the single dominant traffic signal demonstrates the model's clean, interpretable output. Confidence is MEDIUM because the closure timing is specific but the data is not address-level GPS-precise.

### Approved buyer-facing demo responses per score band (product-016)

Use these four responses when walking a buyer or investor through the full range of model outputs. Each example is approved for use in demos, pitch decks, and stakeholder presentations.

#### Low band (0–24) — 11900 S Morgan St, Chicago, IL (West Pullman)
```json
{
  "address": "11900 S Morgan St, Chicago, IL",
  "disruption_score": 8,
  "confidence": "LOW",
  "severity": {
    "noise": "LOW",
    "traffic": "LOW",
    "dust": "LOW"
  },
  "top_risks": [
    "No active street closures or major permits found within 500 meters",
    "Background permit activity in the area is minor and distant",
    "Disruption risk is low based on available city data"
  ],
  "explanation": "There is little evidence of meaningful near-term construction disruption near this address. Available city permit and closure records show only minor background activity, so normal access and livability conditions are expected."
}
```

#### Moderate band (25–49) — 3150 N Southport Ave, Chicago, IL (Lakeview)
```json
{
  "address": "3150 N Southport Ave, Chicago, IL",
  "disruption_score": 34,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "MEDIUM",
    "traffic": "LOW",
    "dust": "LOW"
  },
  "top_risks": [
    "Active building permit for exterior renovation work within roughly 90 meters",
    "Work window extends through the next 30 days",
    "Construction noise is the most likely near-term impact at this address"
  ],
  "explanation": "Nearby construction activity is the main driver, so this address has moderate short-term noise disruption. The permit covers exterior work within close range, but no street or lane closures are confirmed, so traffic access remains largely unaffected."
}
```

#### High band (50–74) — 1600 W Chicago Ave, Chicago, IL (West Town)
*(See approved demo example above.)*

#### Severe band (75–100) — 1200 W Fulton Market, Chicago, IL (Fulton Market)
```json
{
  "address": "1200 W Fulton Market, Chicago, IL",
  "disruption_score": 81,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "HIGH",
    "traffic": "HIGH",
    "dust": "MEDIUM"
  },
  "top_risks": [
    "Multi-lane closure on W Fulton Market within roughly 60 meters, active through next 14 days",
    "Active large-scale construction permit adjacent to the address generating sustained noise",
    "Dust and vibration likely given excavation scope of nearby site work"
  ],
  "explanation": "Multiple reinforcing signals make this address severely disrupted in the near term. A multi-lane closure and an adjacent active construction site combine to create high traffic and curb access friction plus sustained noise disruption within a very short distance."
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
