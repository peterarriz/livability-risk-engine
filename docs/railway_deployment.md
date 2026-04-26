# Railway Postgres+PostGIS Deployment Guide

**Task**: data-015  
**Lane**: data

This document outlines the steps to deploy a Postgres+PostGIS database on Railway and configure the backend to connect to it.

## Overview

Railway provides managed PostgreSQL databases with the ability to install extensions like PostGIS. This guide covers:

1. Setting up the Railway Postgres database
2. Configuring PostGIS extension
3. Running the schema initialization
4. Configuring the backend connection
5. Validating the setup

## Prerequisites

- Railway account (sign up at [railway.app](https://railway.app))
- Railway CLI installed locally (optional but recommended)
- Access to this repository's backend code

## Step 1: Create Railway Postgres Database

### Via Railway Dashboard

1. Go to [railway.app](https://railway.app) and sign in
2. Click "New Project"
3. Select "Add database" → "PostgreSQL"
4. Choose a project name (e.g., "livability-engine-db")
5. The database will be provisioned automatically

### Via Railway CLI (Alternative)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Create new project
railway new

# Add Postgres database
railway add --database postgresql
```

## Step 2: Enable PostGIS Extension

Once your database is provisioned:

1. Go to your Railway project dashboard
2. Click on the PostgreSQL database service
3. Click "Connect" to open the database console
4. Run the following SQL command to enable PostGIS:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Alternatively, connect via any PostgreSQL client using the connection details from Railway and run the same command.

## Step 3: Get Database Connection Details

From your Railway Postgres service dashboard:

1. Go to the "Variables" tab
2. Copy the `DATABASE_URL` value (it will look like: `postgresql://postgres:password@host:port/railway`)
3. You can also find individual connection components:
   - `POSTGRES_HOST`
   - `POSTGRES_PORT` 
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`

## Step 4: Initialize Database Schema

### Method 1: Direct SQL Execution

Connect to your Railway database and run the schema file:

```bash
# Using psql (replace with your actual DATABASE_URL from Railway)
psql "postgresql://postgres:password@host:port/railway" -f db/schema.sql
```

### Method 2: Via Backend Script

The backend includes scripts that can initialize the database:

```bash
# Set environment variables
export DATABASE_URL="postgresql://postgres:password@host:port/railway"
# OR set individual variables:
export POSTGRES_HOST="your-railway-host"
export POSTGRES_PORT="5432"
export POSTGRES_DB="railway"
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="your-password"

# Run schema creation (if you have a script for it)
cd backend
python3 -c "
import os
import psycopg2
from scoring.query import get_db_connection

# Read and execute schema
with open('../db/schema.sql', 'r') as f:
    schema_sql = f.read()

conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute(schema_sql)
conn.commit()
conn.close()
print('Schema created successfully!')
"
```

## Step 5: Configure Backend Environment

### For Development/Local Testing

Create a `.env` file in the `backend/` directory:

```bash
# Railway database connection
DATABASE_URL=postgresql://postgres:password@host:port/railway

# Alternative: Individual variables (if preferred)
POSTGRES_HOST=your-railway-host.railway.app
POSTGRES_PORT=5432
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
```

### For Production Deployment

Set environment variables in your production environment:

- Vercel: Add to project environment variables
- Railway: Add to service environment variables
- Other platforms: Follow platform-specific environment variable setup

## Step 6: Update Backend Configuration

The backend currently expects individual `POSTGRES_*` environment variables. We need to add support for Railway's `DATABASE_URL` format.

### Updated Connection Logic

The `get_db_connection()` function in `backend/scoring/query.py` should be updated to support both formats:

1. `DATABASE_URL` (Railway standard)
2. Individual `POSTGRES_*` variables (existing)

This allows flexibility for different deployment scenarios.

## Step 7: Validate Connection

### Test Backend Connection

```bash
cd backend

# Test database connection
python3 -c "
from scoring.query import get_db_connection
try:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('SELECT version(), postgis_version();')
        result = cur.fetchone()
        print(f'PostgreSQL: {result[0]}')
        print(f'PostGIS: {result[1]}')
    conn.close()
    print('✅ Database connection successful!')
except Exception as e:
    print(f'❌ Connection failed: {e}')
"
```

### Test API Health Check

Start the FastAPI server and check the health endpoint:

```bash
# Start server
cd backend
uvicorn app.main:app --reload

# In another terminal, test health
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "ok",
#   "mode": "live",
#   "db_configured": true
# }
```

`/health` is public liveness only. To check DB readiness, use the
admin-protected `/health/db` endpoint with `X-Admin-Secret`, or run the demo
smoke check with `ADMIN_SECRET` set:

```bash
# From the repository root:
python3 scripts/demo_smoke_check.py --backend-url http://localhost:8000 --require-live
```

## Step 8: Load Initial Data

Once the database is connected and validated:

1. Run the data ingestion pipeline to populate the database
2. Test the `/score` endpoint with real data
3. Verify `scripts/demo_smoke_check.py --require-live` passes. Use
   `/debug/score` only for operator troubleshooting with `X-Admin-Secret`.

## Connection String Format

Railway provides connection strings in this format:
```
postgresql://username:password@hostname:port/database_name
```

This can be parsed to extract individual components if needed for legacy code compatibility.

## Security Considerations

1. **Never commit connection strings**: Keep database credentials in environment variables only
2. **Use Railway's internal networking**: When possible, deploy the backend on Railway for internal network access
3. **Enable SSL**: Railway databases support SSL by default
4. **Rotate passwords**: Regularly rotate database passwords through Railway dashboard

## Troubleshooting

### Common Issues

1. **PostGIS extension not found**: Ensure you've run `CREATE EXTENSION IF NOT EXISTS postgis;`
2. **Connection timeout**: Check if Railway database is in the same region as your backend deployment
3. **SSL errors**: Railway databases require SSL connections by default
4. **Schema errors**: Ensure the database is empty before running schema.sql

### Helpful Commands

```bash
# Test connection with psql
psql "$DATABASE_URL" -c "SELECT 1;"

# Check PostGIS installation
psql "$DATABASE_URL" -c "SELECT postgis_version();"

# List all tables
psql "$DATABASE_URL" -c "\dt"

# Check table row counts
psql "$DATABASE_URL" -c "
SELECT 
    schemaname,
    tablename,
    n_tup_ins as row_count
FROM pg_stat_user_tables 
WHERE schemaname = 'public';
"
```

## Next Steps

After successful deployment:

1. Update `TASKS.yaml` to mark data-015 as completed
2. Proceed with data ingestion (run building permits and street closures loaders)
3. Remove demo fallbacks from `backend/app/main.py` once live data is available
4. Update frontend to remove demo mode handling in `frontend/src/lib/api.ts`

## Environment Variable Reference

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | Railway standard connection string | `postgresql://postgres:pass@host:5432/railway` | Yes (Railway) |
| `POSTGRES_HOST` | Database hostname | `mydb.railway.app` | Yes (individual) |
| `POSTGRES_PORT` | Database port | `5432` | No (default: 5432) |
| `POSTGRES_DB` | Database name | `railway` | No (default: livability) |
| `POSTGRES_USER` | Username | `postgres` | No (default: postgres) |
| `POSTGRES_PASSWORD` | Password | `secretpassword` | Yes |
