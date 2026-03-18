# MVP Scope

## In-scope features
- Geocoded address input → Chicago lat/lon bounding box
- Ingestion pipeline for Chicago permit data + planned street closures
- Normalized project/permit schema stored in PostGIS
- Simple scoring engine (rule-based) producing a 0–100 disruption score
- FastAPI `/score` endpoint returning `disruption_score`, `confidence`, `severity`, `top_risks`, and `explanation`
- Minimal Next.js frontend that calls `/score` and displays the disruption score, severity, top risks, and explanation

## Out-of-scope features
- Machine learning score tuning based on historical disruption outcomes
- Real-time GPS traffic/vehicle feed integration
- Multi-city support
- Complex scenario simulation (e.g. cumulative citywide traffic modeling)
- User accounts / authentication / billing

## MVP success criteria (testable)
1. Given a Chicago address, the API returns a JSON response in <500ms containing `disruption_score` (0–100), `confidence`, `severity`, `top_risks`, and `explanation`.
2. Ingestion pipeline can be run end-to-end from raw source (CSV/API) to normalized DB within 1 hour and ingest at least 30 days of data.
3. Frontend displays the disruption score, severity, top risks, and explanation for the input address and matches the API response.
4. Documentation is present in `/docs` and `/ops` for onboarding an additional engineer.

## Data sources included in MVP
- Chicago OPA permit dataset (commercial/residential construction permits)
- Chicago Department of Transportation planned street closures (permit/roadwork closures)

## Intentionally deferred
- Incorporating utility company outage/repair feeds
- Adding transit disruption schedules (CTA/Uber/Lyft data)
- Tracking project status changes in real time (daily refresh is sufficient)
- Calculating macro-level neighborhood scores (focus is address-level)
