# Scoring Model (MVP)

## Score structure
- Output: single integer `score` in range **0–100** (higher = higher disruption risk).
- Score is the **maximum** of per-project disruption contributions, then scaled/normalized.

## Key variables
- **Distance**: radial distance from input point to project footprint/closure geometry.
- **Scale**: physical footprint (length of closure, number of permits, estimated impacted lanes).
- **Probability**: inferred likelihood that the project is active during the forecast window (based on permit status, start/end dates).
- **Time**: temporal proximity (start date soon vs far future, active window overlap).

## Severity categories (MVP)
1. **Noise / Nuisance**: small residential permits, short-duration sidewalk work.
2. **Traffic Impact**: street/lane closures, major roadway work, long-duration closures.
3. **Pedestrian Impact**: sidewalk closures, alley closures, general access restrictions.

## Confidence model
- Base confidence levels derived from source metadata (e.g., permit status, update time).
- Score response includes `confidence` tier (HIGH / MEDIUM / LOW) based on data freshness and completeness.

## Important assumptions
- A permit/closure that lists a start/end date is considered active if today is between those dates (plus a small buffer).
- Projects with explicit geometry (closure endpoints) are more reliable; when geometry is missing, fall back to address centroid.
- The score is not a prediction of accidents or delays, but a relative measure of planned disruption potential.

## Open questions
- How to weight overlapping projects? (sum vs max vs spatial aggregation)
- How to handle multi-day rolling closures where permit dates are broad?
- What is the best public signal for “confidence” (e.g., last modified timestamp vs status code)?
