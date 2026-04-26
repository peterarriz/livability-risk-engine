# Database Connection Validation Guide

**Task**: data-015  
**Lane**: data

This document outlines the validation steps to ensure the Railway Postgres+PostGIS database is properly deployed and connected.

## Validation Checklist

### 1. Database Instance Verification

After provisioning the Railway database:

```bash
# Test basic connection
psql "$DATABASE_URL" -c "SELECT version();"

# Verify PostGIS extension
psql "$DATABASE_URL" -c "SELECT postgis_version();"
```

Expected output:
- PostgreSQL version string
- PostGIS version string (e.g., "3.x.x")

### 2. Schema Validation

After running `python3 scripts/init_database.py`:

```bash
# Check all tables exist
psql "$DATABASE_URL" -c "\dt"
```

Expected tables:
- `ingest_runs`
- `projects` 
- `raw_building_permits`
- `raw_street_closures`

```bash
# Verify PostGIS geometry columns
psql "$DATABASE_URL" -c "SELECT f_table_name, f_geometry_column, type FROM geometry_columns;"
```

Expected output:
- `projects.geom` with type `POINT`

### 3. Backend Connection Validation

Test all connection methods:

```bash
# Test with DATABASE_URL
export DATABASE_URL="your_railway_connection_string"
cd backend
python3 -c "from scoring.query import get_db_connection; conn = get_db_connection(); print('✅ Connected'); conn.close()"

# Test with individual variables
export POSTGRES_HOST="your-railway-host"
export POSTGRES_PORT="5432"
export POSTGRES_DB="railway"
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="your-password"
unset DATABASE_URL
python3 -c "from scoring.query import get_db_connection; conn = get_db_connection(); print('✅ Connected'); conn.close()"
```

### 4. API Health Check Validation

Start the FastAPI server and test endpoints:

```bash
# Start server
cd backend
uvicorn app.main:app --reload

# In another terminal, test the public liveness endpoint
curl http://localhost:8000/health | jq
```

Expected public `/health` response when database is configured:
```json
{
  "status": "ok",
  "mode": "live",
  "db_configured": true
}
```

`/health` is liveness only. To validate DB readiness and ingest metadata, use
the admin-protected `/health/db` endpoint with `X-Admin-Secret`:

```bash
curl -s \
  -H "X-Admin-Secret: ${ADMIN_SECRET:?set ADMIN_SECRET}" \
  http://localhost:8000/health/db \
  | jq
```

### 5. Score Endpoint Validation

```bash
# Test score endpoint (should return live mode if DB is empty)
curl "http://localhost:8000/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" | jq
```

Expected response shape:
```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "disruption_score": 0,
  "confidence": "LOW",
  "severity": {"noise": "LOW", "traffic": "LOW", "dust": "LOW"},
  "top_risks": ["No significant construction or closure activity found nearby."],
  "explanation": "No significant construction or closure activity was found near this address within the near-term window.",
  "mode": "live",
  "fallback_reason": null
}
```

### 6. Demo Smoke Validation

```bash
# Non-destructive score contract and readiness check
# From the repository root:
python3 scripts/demo_smoke_check.py --backend-url http://localhost:8000 --require-live
```

Set `ADMIN_SECRET` or pass `--admin-secret` to include the protected
`/health/db` readiness probe. Set `LRE_API_KEY` or pass `--api-key` if the
backend requires API keys.

### 7. Optional Debug Endpoint Validation

`/debug/score` is internal and requires `X-Admin-Secret`. Use it only when
an operator needs lower-level geocoding/project-count detail:

```bash
curl -s \
  -H "X-Admin-Secret: ${ADMIN_SECRET:?set ADMIN_SECRET}" \
  "http://localhost:8000/debug/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" \
  | jq
```

## Common Issues and Troubleshooting

### Connection Issues

**Error**: `psycopg2.OperationalError: could not connect to server`

**Solutions**:
1. Check DATABASE_URL format: `postgresql://user:pass@host:port/database`
2. Verify Railway database is not sleeping (free tier limitation)
3. Check firewall/network connectivity

**Error**: `ERROR: extension "postgis" does not exist`

**Solution**:
```sql
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

### Schema Issues

**Error**: `relation "projects" does not exist`

**Solution**:
Run the database initialization script:
```bash
python3 scripts/init_database.py
```

### Backend Issues

**Error**: Backend shows `mode: "demo"` instead of `mode: "live"`

**Diagnosis**:
1. Check environment variables are set
2. Verify public liveness with `/health` and DB readiness with protected `/health/db`
3. Check backend logs for connection errors

**Error**: `geocode_failed` fallback reason

**Diagnosis**:
- Geocoding service may be unavailable
- Try a different Chicago address
- Check backend logs for geocoding errors

## Environment Setup Examples

### Development (.env.local)

```bash
# Railway connection
DATABASE_URL=postgresql://postgres:password@railway-host:5432/railway

# Alternative format
POSTGRES_HOST=railway-host.railway.app
POSTGRES_PORT=5432
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
```

### Production (Vercel)

Set environment variables in Vercel dashboard:
- `DATABASE_URL`: `postgresql://...`
- `FRONTEND_ORIGIN`: `https://your-frontend.vercel.app`

## Performance Validation

After data is ingested, validate performance:

```bash
# Check index usage on spatial queries
psql "$DATABASE_URL" -c "EXPLAIN ANALYZE SELECT COUNT(*) FROM projects WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(-87.6704, 41.8960), 4326)::geography, 500);"
```

Expected:
- Query should use `projects_geom_idx` index
- Execution time should be under 50ms for typical datasets

## Success Criteria

✅ All validation checks pass
✅ Public `/health` returns `status: "ok"`
✅ Protected `/health/db` returns `db_connection: true`
✅ Score endpoint returns `mode: "live"`
✅ `scripts/demo_smoke_check.py --require-live` passes
✅ No connection errors in backend logs
✅ Schema tables exist with proper indexes
✅ PostGIS extension is available

## Next Steps

Once validation is complete:

1. **Load Initial Data**: Run building permits and street closures ingestion
   ```bash
   python3 backend/ingest/building_permits.py --days 180
   python3 backend/ingest/street_closures.py --days 180
   python3 backend/ingest/load_projects.py
   ```

2. **Test with Real Data**: Verify score endpoint returns realistic results
   ```bash
   # From the repository root:
   python3 scripts/demo_smoke_check.py --backend-url http://localhost:8000 --require-live
   ```

3. **Remove Demo Fallbacks**: Update frontend and backend to remove demo mode handling

4. **Deploy to Production**: Set up production environment variables and deploy

## Documentation References

- [Railway Deployment Guide](railway_deployment.md)
- [API Health Check Documentation](handoffs/app.md)
- [Database Schema](../db/schema.sql)
- [Backend Connection Logic](../backend/scoring/query.py)
