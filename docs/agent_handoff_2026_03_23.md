# Agent Handoff — 2026-03-23

**Project:** Livability Risk Engine — Chicago MVP
**Period covered:** ~2026-03-17 through 2026-03-23
**Branch:** `claude/website-expansion-planning-zaoQR`
**Prepared by:** Claude (data lane agent)

---

## TL;DR for the next agent

The database is live, the ingest pipeline is running daily, and the demo fallback has been removed. The app is now in "live-or-error" mode — no more silent demo data. The one remaining manual step is confirming that the Railway backend URL is wired into Vercel as `NEXT_PUBLIC_API_URL` so the frontend actually calls the live backend.

**Immediate priority:** data-039 — validate `/score` returns real DB data end-to-end.

---

## What was the state at the start of this period

- Backend: FastAPI on Railway (code deployed, service running)
- Database: Railway Postgres provisioned, but `DATABASE_URL` GitHub secret had the **private** Railway hostname (`postgres.railway.internal`), which is unreachable from GitHub Actions runners
- Schema: Not yet applied to the live DB
- Ingest: Never run against the live DB — all scoring was returning the approved demo scenario
- Frontend: Live on Vercel, but always showing demo mode because the DB was never populated
- Demo fallback: Active in both backend `/score` and frontend `fetchScore()`

---

## What was accomplished this period

### Infrastructure fixes

| Fix | Detail |
|-----|--------|
| `DATABASE_URL` secret corrected | Was set to Railway's private internal hostname. Updated to the public proxy URL (`roundhouse.proxy.rlwy.net:PORT`), which is reachable from GitHub Actions. |
| Railway OOM kill fixed | Removed `--workers 2` from uvicorn start command — single worker prevents hobby-tier memory exhaustion. |
| Health check hang fixed | Added `connect_timeout=5` to psycopg2 connections; moved DB ping to `/health/db` so `/health` responds instantly even when DB is slow. |
| Backend startup crash fixed | Added missing FastAPI imports (`Header`, `Depends`, `Response`) that caused Railway to fail on boot. |
| python-dotenv added | Added to root `requirements.txt` so Railway build doesn't fail on `from dotenv import load_dotenv`. |

### Data pipeline work

**data-034 — Fixed IDOT normalizer field names**
The IDOT (Illinois Department of Transportation) road project normalizer was using wrong field names. Fixed to use the correct ArcGIS REST API field names so IDOT construction data ingests cleanly.

**data-035 — Fixed film permits and special events dataset IDs**
Chicago Data Portal dataset IDs for film permits (`ivkd-2m2v`) and special events (`r5kz-chrr`) were incorrect. Fixed field name mappings for both.

**data-036 — Added three new Chicago data sources**
Three new ingest scripts and normalizers added:
- `backend/ingest/chicago_311_requests.py` — pothole/water main/cave-in/tree emergency calls from Socrata `v6vf-nfxy` (last 90 days)
- `backend/ingest/chicago_film_permits.py` — film permit street holds from Socrata `ivkd-2m2v` (last 90 days + next 30 days)
- `backend/ingest/chicago_special_events.py` — festivals, parades, marathons from Socrata `r5kz-chrr` (last 60 days + next 90 days)

New normalizers in `backend/models/project.py`:
- `normalize_311_request()`, `normalize_film_permit()`, `normalize_special_event()`

`run_pipeline.py` updated with skip flags: `--skip-311`, `--skip-film`, `--skip-events`.

**data-038 — Removed PostGIS dependency**
Railway standard Postgres does not include PostGIS. All spatial queries migrated from `ST_DWithin`/`ST_Distance` to pure haversine math in plain SQL.

Changes:
- `db/schema.sql` — removed `CREATE EXTENSION postgis` and `geom` column from `projects` table; added `projects_location_idx (latitude, longitude)` as bounding-box pre-filter
- `backend/ingest/load_projects.py` — removed `geom` from upsert SQL
- `backend/scoring/query.py` — radius query now uses haversine bounding box + exact haversine distance

**data-016 — Pipeline orchestrator and schema apply script**
- `run_pipeline.py` at repo root orchestrates all ingest steps in sequence
- `scripts/apply_schema.sh` applies `db/schema.sql` via `psql` (idempotent, uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`)

**data-020 — Daily ingest cron via GitHub Actions**
`.github/workflows/ingest.yml` runs daily at 06:00 UTC. Steps:
1. Install `postgresql-client`
2. Apply schema (idempotent)
3. Run `run_pipeline.py`
4. Smoke-check active project count

Manual dispatch supported with `dry_run` and `skip_geocode` inputs. Requires `DATABASE_URL` secret in GitHub repo settings.

**data-017 — First successful live ingest (completed today)**
Pipeline run #7 succeeded: schema applied (9s), ingest ran (13m 45s), smoke check passed.

**Demo fallback removed (today, as part of data-017 close)**
- `backend/app/main.py` `/score` endpoint: removed `if not _is_db_configured()` block. The endpoint now always attempts live scoring. Geocode failure → 422. Scoring error → 503. No more silent demo response.
- `frontend/src/lib/api.ts` `fetchScore()`: the `catch` block that returned fabricated demo data on network error now throws `ApiError` instead. The frontend will show an error to the user if the backend is unreachable, rather than silently showing stale sample data.

Note: `_build_demo_response()` and `_is_db_configured()` still exist in `main.py` and are still used by `/debug/score`, `/save-report`, and `/export` endpoints. Only the main `/score` path has been hardened.

### App lane work (app-009 through app-023)

14 UX and accessibility improvements landed, including:
- Accordion behavior for risk detail panels (only one open at a time)
- Confidence dot color fix (LOW = neutral grey, not misleading green)
- aria-live region on score results for screen readers
- Skip-to-main-content link (WCAG 2.1 AA)
- Escape key closes modals and history dropdown
- Clear button in address input
- Document title updates on result load
- Slash-key focuses address input
- Good-news empty state when no risks detected
- Mobile topnav cleanup in workspace mode
- Score timestamp in Quick Read card

### Frontend / Vercel

- Added Vercel Analytics (`@vercel/analytics`)
- Added `vercel.json` (pinned to `iad1` region)
- Expanded geocoding coverage from Chicago-only to all of Illinois
- Static Chicago street list for instant autocomplete (no geocoder round-trip for common queries)

---

## Current system state

| Component | Status |
|-----------|--------|
| Railway Postgres DB | Live, schema applied, data loaded |
| Daily ingest cron | Active — runs 06:00 UTC, last run succeeded |
| Backend (Railway) | Deployed and running |
| `/health` endpoint | Responds instantly; DB ping at `/health/db` |
| `/score` endpoint | Live-only mode — demo fallback removed |
| Frontend (Vercel) | Deployed |
| `NEXT_PUBLIC_API_URL` in Vercel | **UNCONFIRMED** — may still be unset or pointing to old URL |
| End-to-end live scoring | **UNVALIDATED** — see data-039 |

---

## What still needs to happen

### data-039 (immediate — high priority)
**Validate `/score` returns real DB data end-to-end.**

Steps:
1. Confirm Railway backend URL (e.g. `https://livability-risk-engine.up.railway.app`) is set as `NEXT_PUBLIC_API_URL` in Vercel → Settings → Environment Variables. Redeploy frontend if you change it.
2. Run smoke queries:
   ```bash
   curl -s "https://<railway-backend>/health" | python3 -m json.tool
   # expect: db_connection=true, status="ok"

   curl -s "https://<railway-backend>/score?address=100+W+Randolph+St+Chicago+IL" | python3 -m json.tool
   # expect: mode="live", disruption_score is a real number, top_risk_details non-empty
   ```
3. If `/score` still returns `mode: "demo"`, the Railway backend service itself may not have `DATABASE_URL` set in its own env vars (separate from the GitHub Actions secret). Set it in Railway → your backend service → Variables.
4. Once validated, mark data-019 done.

### data-019 (in-progress)
**Backend Railway deploy — operator validation.**

The code is deployed. What's unconfirmed:
- Railway backend service has `DATABASE_URL` env var set (not just GitHub Actions)
- `FRONTEND_ORIGIN` is set to the Vercel frontend URL (CORS)
- `NEXT_PUBLIC_API_URL` in Vercel points to the Railway backend public URL

### data-037 (backlog — medium)
**Illinois Tollway construction data.**
Not on the Chicago Data Portal. Options: IDOT District 1 ArcGIS (already covered by `idot_road_projects.py`), scraping `illinoistollway.com` (fragile), or GIS at `gis.idot.illinois.gov`. May be a won't-fix if IDOT District 1 already covers I-90/94 sufficiently.

---

## Key file locations

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app — all API endpoints |
| `backend/scoring/query.py` | Haversine radius query + score computation |
| `backend/models/project.py` | Project dataclass + all normalizers |
| `backend/ingest/` | All ingest scripts (permits, closures, 311, film, events, IDOT) |
| `backend/ingest/load_projects.py` | DB upsert — loads normalized rows into `projects` table |
| `run_pipeline.py` | Orchestrates all ingest steps |
| `scripts/apply_schema.sh` | Idempotent schema apply via psql |
| `db/schema.sql` | Full DB schema (no PostGIS — haversine only) |
| `frontend/src/lib/api.ts` | All frontend API calls |
| `.github/workflows/ingest.yml` | Daily ingest cron (06:00 UTC) |
| `TASKS.yaml` | Task registry — source of truth for what's done/pending |
| `docs/deploy_readiness_checklist.md` | Step-by-step checklist to confirm live mode |
| `docs/04_api_contracts.md` | Full API response shapes |

---

## Environment variables reference

| Variable | Where set | Purpose |
|----------|-----------|---------|
| `DATABASE_URL` | GitHub Actions secret + Railway backend service | Postgres connection string (public URL for Actions, internal OK for Railway service) |
| `NEXT_PUBLIC_API_URL` | Vercel env var | Railway backend public URL — **must be set for frontend to hit live backend** |
| `FRONTEND_ORIGIN` | Railway backend service env var | Allowed CORS origin (set to Vercel frontend URL) |
| `CHICAGO_SOCRATA_APP_TOKEN` | GitHub Actions secret (optional) | Higher Socrata rate limits during ingest |
| `REQUIRE_API_KEY` | Railway backend service env var (optional) | Set to `true` to enable API key auth |

---

## Scoring model summary (for context)

- **Radius:** 500 m haversine from geocoded address
- **Base weights by impact type:** `closure_full` (40) → `closure_multi_lane` (30) → `demolition` (20) → `closure_single_lane` (15) → `construction` (10) → `light_permit` (3)
- **Timing multiplier:** active projects with end_date within 7 days get 1.5×
- **Score cap:** 100
- **Confidence:** HIGH (≥3 projects), MEDIUM (1–2), LOW (0)
- **Data sources active:** Chicago building permits, CDOT street closures, Chicago 311 requests, film permits, special events, IDOT road construction

Full model: `docs/03_scoring_model.md`
