# Architecture

## End-to-end system flow
1. **Ingestion**: Fetch raw permit & closure sources (CSV/API) -> raw storage (S3/`data/raw` folder) -> staging.
2. **Normalization**: Parse raw records -> normalize into canonical `project` schema -> upsert into Postgres/PostGIS.
3. **Scoring**: For a query address, find nearby active projects, apply rule-based score model, return score + factor breakdown.
4. **API**: FastAPI service exposes `/score` endpoint (JSON) and internal health/metrics endpoints.
5. **Frontend**: Next.js app calls `/score`, renders score and project list; optional map view.

## Tech stack
- **Backend API**: Python 3.11 + FastAPI
- **Database**: Postgres + PostGIS (spatial queries + distance calculations)
- **Frontend**: Next.js (React) with client-side fetch to API
- **Data pipeline**: Python scripts (cron/airflow optional), local files under `data/` or `db/`
- **Infra** (MVP): local dev containers / Docker Compose; deploy via simple VM/container

## Data flow between layers
- Raw ingestion writes to a raw staging area (CSV/JSON).
- Normalizer reads staging, writes canonical rows to Postgres; ensures idempotency via stable keys.
- API reads Postgres, performs spatial query around input coordinates, computes score.
- Frontend calls API and renders response (no direct DB access).

## Responsibilities by lane
- **Product**: define success criteria, gaps in source data, prioritize features, validate score output with stakeholders.
- **Data**: implement ingestion/normalization pipelines, maintain canonical schema, ensure data quality and coverage.
- **App**: build API scaffold, core `/score` endpoint, frontend demo, deploy pipeline (dev/staging).

## Where AI is used vs not used
- **Used**: AI agents can assist in writing ingestion/parsing code, generating docs, and suggesting scoring heuristics.
- **Not used**: Core scoring logic, production API, and backend data pipelines should be deterministic and reviewable by humans. No black-box ML model in MVP.
