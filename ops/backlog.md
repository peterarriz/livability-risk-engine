# Backlog

## Near-term next tasks
- Refine scoring weights using a small set of example addresses and manual validation.
- Add a daily refresh job for permit + closure ingestion.
- Implement basic data quality checks (missing geometry, invalid dates).
- Add basic logging/metrics for API response times and score distribution.

## Medium-term features
- Add utility outage and utility repair sources to scoring model.
- Add a project timeline view in frontend (calendar / Gantt strip).
- Support batch scoring for a list of addresses (CSV input).
- Add confidence breakdown and contributor scoring details in API response.

## Long-term ideas
- Train a machine learning model using historical disruption complaints or traffic speed data.
- Expand to other cities with plug-n-play source adapters.
- Add user accounts, saved addresses, and alert subscriptions.
- Add a map-based UI with clustering and heatmaps.
