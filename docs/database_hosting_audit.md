# Database Hosting Audit - data-014

## Executive Summary

The Livability Risk Engine has a complete data pipeline but is currently using a mocked demo mode because no live Postgres+PostGIS database is hosted. This audit evaluates hosting options to deploy the database and enable live scoring.

## Current Database Requirements

### Database Stack
- **PostgreSQL** with **PostGIS extension** (spatial queries)
- Database name: `livability`
- Default port: 5432
- Required extensions: `postgis`

### Schema Overview
- **Raw tables**: `raw_building_permits`, `raw_street_closures` (source data staging)
- **Canonical table**: `projects` (normalized, used by scoring engine)
- **Audit table**: `ingest_runs` (ingestion tracking)
- **Key indexes**: Spatial GIST index on `projects.geom`, date indexes
- **Schema size**: Small to medium for MVP (estimated < 100MB for Chicago data)

### Application Connection Pattern
- **Environment variables**: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- **Driver**: `psycopg2-binary` (already in requirements.txt)
- **Connection method**: Direct connection from FastAPI backend
- **Query pattern**: Spatial radius queries using `ST_DWithin` for scoring

### Data Ingestion Requirements
- **Daily ingestion** from Chicago Socrata APIs (building permits, street closures)
- **Incremental updates** using source_id for upserts
- **Ingest scripts**: `backend/ingest/building_permits.py`, `backend/ingest/street_closures.py`
- **Volume**: Low (estimated hundreds of new records per day)

## Hosting Platform Analysis

### 1. Railway
**Type**: Application-focused PaaS with database add-ons

**Pros:**
- **PostGIS support**: ✅ Explicit PostGIS support in Postgres service
- **Cost**: $5/month starter plan, reasonable for MVP
- **Setup**: Simple env var injection, git-based deploys
- **Backend hosting**: Can host FastAPI backend on same platform
- **Developer experience**: Excellent, minimal configuration

**Cons:**
- **Newer platform**: Less enterprise track record than established providers
- **Scaling**: Limited control over database tuning

**Best fit for**: 
- MVP with co-located backend/database
- Teams wanting minimal DevOps overhead

### 2. Supabase
**Type**: Database-as-a-Service (Postgres-native)

**Pros:**
- **Native PostGIS**: ✅ PostGIS enabled by default, excellent spatial support
- **Cost**: Free tier available, $25/month pro plan
- **Performance**: Optimized Postgres with connection pooling
- **Tooling**: Built-in database dashboard, migration tools
- **Extensions**: Full extension support including PostGIS

**Cons:**
- **Backend hosting**: Database-only, need separate hosting for FastAPI
- **Vendor lock-in**: Some proprietary features beyond standard Postgres

**Best fit for**:
- Database-first approach with separate backend hosting
- Teams wanting Postgres-native tooling

### 3. Render
**Type**: General-purpose PaaS with managed databases

**Pros:**
- **PostGIS support**: ✅ Full Postgres with extensions
- **Cost**: $7/month starter database plan
- **Backend hosting**: Can host FastAPI backend on same platform
- **Reliability**: Strong uptime reputation
- **Configuration**: Standard Postgres, minimal vendor-specific features

**Cons:**
- **Setup complexity**: Requires more manual PostGIS extension setup
- **Pricing**: Slightly higher than competitors for equivalent resources

**Best fit for**:
- Teams wanting standard Postgres without vendor-specific features
- Full-stack hosting on single platform

### 4. DigitalOcean Managed Databases
**Type**: Traditional cloud managed database service

**Pros:**
- **PostGIS support**: ✅ Available as extension
- **Cost**: $15/month starter plan
- **Performance**: Dedicated resources, predictable performance
- **Control**: Standard Postgres, full admin access

**Cons:**
- **Setup effort**: More manual configuration required
- **Backend hosting**: Need separate droplet or external service
- **Cost**: Higher than newer PaaS options

**Best fit for**:
- Production deployments with dedicated resources
- Teams comfortable with traditional cloud infrastructure

### 5. Heroku Postgres
**Type**: Established PaaS database add-on

**Pros:**
- **PostGIS support**: ✅ Available via extension
- **Maturity**: Battle-tested platform
- **Integration**: Seamless with Heroku app hosting

**Cons:**
- **Cost**: $5/month essential plan, but limited storage
- **Platform dependency**: Tied to Heroku ecosystem
- **Performance**: Shared resources on lower tiers

**Best fit for**:
- Teams already on Heroku
- Traditional PaaS preference

## Platform Comparison Matrix

| Platform | Monthly Cost | PostGIS | Backend Hosting | Setup Effort | MVP Ready |
|----------|-------------|---------|----------------|-------------|-----------|
| **Railway** | $5 | ✅ Native | ✅ Same platform | Low | ✅ |
| **Supabase** | $25 (Free available) | ✅ Native | ❌ External needed | Low | ✅ |
| **Render** | $7 | ✅ Extension | ✅ Same platform | Medium | ✅ |
| **DigitalOcean** | $15 | ✅ Extension | ❌ External needed | Medium | ✅ |
| **Heroku** | $5 | ✅ Extension | ✅ Same platform | Low | ⚠️ Limited |

## Recommendations

### Primary Recommendation: Railway
**Why Railway is the best fit for MVP:**

1. **Lowest total friction**: Database + backend hosting on single platform
2. **Cost effective**: $5/month database + $5/month backend = $10/month total
3. **PostGIS ready**: Native support without manual extension setup
4. **MVP-focused**: Perfect for getting to live demo quickly
5. **Migration path**: Easy to migrate to other platforms later if needed

**Implementation approach:**
- Deploy database service on Railway
- Deploy FastAPI backend as Railway service
- Connect via Railway's internal network
- Environment variables auto-injected

### Secondary Recommendation: Supabase
**If database-only hosting preferred:**

1. **Best-in-class Postgres**: Superior database features and performance
2. **Free tier**: Can start with free tier for initial testing
3. **Spatial-first**: Excellent PostGIS support and spatial tooling
4. **Growth path**: Scales well for production usage

**Implementation approach:**
- Create Supabase project with PostGIS enabled
- Deploy FastAPI to Vercel or Railway
- Connect via environment variables
- Use Supabase dashboard for database management

### Not Recommended for MVP: DigitalOcean, Heroku
- **DigitalOcean**: Good for production but overkill for MVP
- **Heroku**: Storage limitations and platform constraints

## Next Steps

### Immediate Actions (data-015)
1. **Create Railway account** and test PostGIS setup
2. **Run schema migration**: `psql < db/schema.sql`
3. **Test ingest pipeline**: Run building permits and street closures scripts
4. **Validate scoring**: Test /score endpoint with real data
5. **Update environment variables**: Set POSTGRES_HOST to enable live mode

### Success Criteria
- [ ] Database schema deployed successfully
- [ ] PostGIS extension working (spatial queries)
- [ ] Raw data ingested (building permits + street closures)
- [ ] Canonical projects table populated
- [ ] /score endpoint returning real scores (not demo fallback)
- [ ] Frontend connected to live backend

### Risk Mitigation
- **Demo fallback**: Keep demo mode as backup during transition
- **Data validation**: Verify ingest data quality before switching modes
- **Monitoring**: Track ingest_runs table for data freshness
- **Cost monitoring**: Set billing alerts on hosting platform

## Budget Impact
- **Railway (recommended)**: ~$10/month for database + backend
- **Alternative**: ~$25-40/month for Supabase + separate backend hosting
- **ROI**: Enables real customer demos and design partner engagement

---

*This audit satisfies data-014. Next task should be data-015 (implement recommended hosting solution).*