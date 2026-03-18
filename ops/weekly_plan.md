# Weekly Plan

## Week 1 goal
Establish a runnable baseline: ingest Chicago permits/closures into Postgres, expose a mocked `/score` endpoint, and validate end-to-end flow to the frontend.

## Deliverables by lane

### Product
- Confirm MVP scope and success criteria with the team.
- Validate that selected data sources (permits + closures) are accessible and contain expected fields.
- Provide 3–5 example addresses for score validation.

### Data
- Implement ingestion pipelines for Chicago permits and street closures.
- Normalize data into the canonical project schema and load into PostGIS.
- Create a basic query that returns projects near a lat/lon.

### App
- Scaffold FastAPI backend with `/score` endpoint returning mocked JSON.
- Scaffold Next.js frontend to call `/score` and render score + projects.
- Add local run instructions to README.

## Risks
- **Data access risk**: Public APIs may change, be rate-limited, or require API keys.
- **Geometry risk**: Source feeds may lack reliable location data, impacting spatial scoring.
- **Time risk**: Team of 3 could be blocked if the ingestion pipeline requires extensive data cleanup.
