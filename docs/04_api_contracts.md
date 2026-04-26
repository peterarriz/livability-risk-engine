# API Contracts

---

## `/score/batch` endpoint  (data-045)

- **Method**: `POST`
- **Content-Type**: `application/json`
- **Auth**: `X-API-Key` header required — always, regardless of `REQUIRE_API_KEY` env var
- **Limit**: maximum 200 addresses per request (422 if exceeded)

### Request body

```json
{
  "addresses": [
    "1600 W Chicago Ave, Chicago, IL",
    "700 W Grand Ave, Chicago, IL"
  ]
}
```

### Response

```json
{
  "batch_id": "a3f1c8d2-...",
  "scored": 2,
  "failed": 0,
  "results": [
    {
      "address": "1600 W Chicago Ave, Chicago, IL",
      "livability_score": 48,
      "disruption_score": 54,
      "confidence": "HIGH",
      "severity": {"noise": "LOW", "traffic": "HIGH", "dust": "LOW"},
      "top_risks": ["Multi-lane closure on W Chicago Ave within roughly 110 meters; active through 2026-03-26"],
      "explanation": "...",
      "mode": "live",
      "error": null
    },
    ...
  ]
}
```

### Per-address failure handling

When a single address fails (geocode failure, scoring error), it is returned inline with:
- `error`: string describing the failure
- All other fields: `null`

The overall request returns 200 even when some addresses fail. Check `failed` in the response envelope.

### Notes

- `batch_id` is a UUID generated per request and written to `score_history` for all successful results.
- Addresses are scored in parallel (up to 10 concurrent workers).
- `nearby_signals` is not included in batch output.

---

## `/score/batch/csv` endpoint  (data-045)

- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Auth**: `X-API-Key` header required — always
- **Limit**: maximum 200 addresses (rows beyond 200 are ignored)

### Request

Upload a CSV file as the `file` field (multipart). One address per row. An optional header row with value `address` (case-insensitive) is skipped automatically. Excel BOM is handled.

```
address
1600 W Chicago Ave, Chicago, IL
700 W Grand Ave, Chicago, IL
```

### Response

Returns a `text/csv` download (`livability_scores_<batch_id_prefix>.csv`) with columns:

| Column | Description |
|---|---|
| `address` | Input address echoed back |
| `disruption_score` | Backward-compatible disruption/risk subscore, 0-100 where higher means more risk (empty on error) |
| `confidence` | HIGH / MEDIUM / LOW (empty on error) |
| `severity_noise` | HIGH / MEDIUM / LOW |
| `severity_traffic` | HIGH / MEDIUM / LOW |
| `severity_dust` | HIGH / MEDIUM / LOW |
| `top_risk_1` | First top-risk string (empty if none) |
| `top_risk_2` | Second top-risk string (empty if none) |
| `top_risk_3` | Third top-risk string (empty if none) |
| `error` | Error message if address failed; empty on success |

---

## `/score` endpoint
- **Method**: `GET`
- **Query param**: `address` (required, US address string with city/state where possible)

### Response fields
- `address`: normalized user input string echoed back in the response.
- `livability_score`: current public headline score, integer from `0` to `100`. Higher means better address livability and lower near-term risk.
- `disruption_score`: backward-compatible disruption/risk subscore, integer from `0` to `100`. Higher means more near-term disruption risk. This is a practical indicator, not a scientific forecast of exact delay, decibel level, or project duration.
- `livability_breakdown`: weighted component details for the headline livability score when available. The `disruption_risk` component is inverted from `disruption_score`.
- `confidence`: `HIGH` | `MEDIUM` | `LOW`.
- `severity`: object with `noise`, `traffic`, and `dust`, each using `LOW` | `MEDIUM` | `HIGH`.
- `top_risks`: ordered list of up to 3 short plain-English risk bullets.
- `explanation`: 1 short paragraph explaining the dominant driver.
- `evidence_quality`: `strong` | `moderate` | `contextual_only` | `insufficient` when available. This is the clearest coverage/evidence signal for user-facing copy.
- `strong_signal_count`: count of nearby address-level signals that materially support the result when available.
- `confidence_reason`: short explanation of why the confidence level was assigned when available.
- `mode`: `"live"` when the score was computed from the live database; `"demo"` when the approved fallback response was used. Added in app-019.
- `fallback_reason`: `null` when `mode` is `"live"`. A string explaining why demo mode was used when `mode` is `"demo"`. Values: `"db_not_configured"` | `"geocode_failed"` | `"scoring_error"`. Added in app-019.

**Backward compatibility**: `disruption_score`, `mode`, and `fallback_reason` remain available for existing consumers. New public UI should use `livability_score` as the headline when present and keep `disruption_score` as a supporting risk subscore.

### Interpretation notes
- `livability_score` is the public headline: higher is better.
- `disruption_score` aligns with the disruption bands in `docs/03_scoring_model.md`: low, moderate, high, and severe. Higher is more disruption risk.
- `disruption_score` should reflect the weighted contribution of the strongest nearby signals rather than a broad average of every weak record in the area.
- `confidence` should describe evidence quality and specificity, not severity or score direction. Use:
  - `LOW` for stale, incomplete, or weakly located/timed evidence
  - `MEDIUM` for plausible but still somewhat ambiguous evidence
  - `HIGH` for recent, specific, and directly relevant evidence
- Coverage varies by city, source, and data type. Where permit or closure feeds are sparse, results rely more on neighborhood context and should be treated as directional.
- `severity.noise` reflects audible construction disruption.
- `severity.traffic` reflects access friction, including lane/street impacts and related curb-access disruption.
- In buyer-facing copy, `traffic` should be understood as **traffic and curb access** when parking, loading, pickup, or dropoff friction is part of the nearby disruption story.
- `severity.dust` reflects demolition, excavation, or similarly physical site activity likely to create dust or vibration nuisance.

### Approved demo example (product-012)

The following response is the approved canonical example for demo walkthroughs and stakeholder reviews. It represents a High disruption-band address with a dominant traffic signal. Use this example verbatim when demoing the API output.

```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "livability_score": 48,
  "disruption_score": 62,
  "confidence": "MEDIUM",
  "evidence_quality": "moderate",
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

**Why this example was chosen**: 1600 W Chicago Ave is a recognizable West Town arterial with documented active closure history, making it credible for a disruption-risk walkthrough. The disruption subscore of 62 sits clearly in the High band without overstating a Severe outcome, while the livability score of 48 shows how disruption and neighborhood context combine in the current headline score. Confidence is MEDIUM because the closure timing is specific but the data is not address-level GPS-precise.

### Approved buyer-facing demo responses per score band (product-016)

Use these four responses when walking a buyer or investor through the full range of disruption subscore outputs. Each example is approved for use in demos, pitch decks, and stakeholder presentations.

#### Low disruption band (0–24) — 11900 S Morgan St, Chicago, IL (West Pullman)
```json
{
  "address": "11900 S Morgan St, Chicago, IL",
  "livability_score": 84,
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

#### Moderate disruption band (25–49) — 3150 N Southport Ave, Chicago, IL (Lakeview)
```json
{
  "address": "3150 N Southport Ave, Chicago, IL",
  "livability_score": 64,
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

#### High disruption band (50–74) — 1600 W Chicago Ave, Chicago, IL (West Town)
*(See approved demo example above.)*

#### Severe disruption band (75–100) — 1200 W Fulton Market, Chicago, IL (Fulton Market)
```json
{
  "address": "1200 W Fulton Market, Chicago, IL",
  "livability_score": 29,
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
- `livability_score` is the public headline field when present.
- `disruption_score` remains in the response for API compatibility and disruption-specific workflows.
- The score should be interpretable by a non-technical reviewer without exposing raw model internals.
- `top_risks` should be implementation-ready display strings; the frontend should not need to reconstruct them from lower-level project data.
- `explanation` should be deterministic and consistent with the rules in `docs/03_scoring_model.md`.
- `explanation` should be led by the single dominant signal; only mention a secondary driver when it materially changes how a reviewer should interpret the address.
- When `severity.traffic` is driven mainly by curb occupancy or pickup/loading friction, the wording should say so explicitly instead of implying only broad roadway congestion.
