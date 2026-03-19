# Data Sources (Chicago)

## Priority 1 sources

### 1) Chicago Building Permits (City of Chicago Data Portal)
- **What it provides**: Active and historic building permit records (commercial/residential), including scope of work, permit type, address, issue/expiration dates.
- **Why it matters**: Most construction disruption originates from permitted building work; permits are a stable, public source.
- **Expected difficulty**: Medium (CSV/JSON API with pagination; inconsistent address formatting).
- **Access method**: Socrata API at `data.cityofchicago.org` (dataset `ydr8-5enu`); no API key required for read-only access; supports JSON and CSV output.
- **Ingestion approach**: Scheduled pull from Socrata API + incremental delta using `updated_date`.
- **Refresh cadence**: Daily. Pull records updated in the last 24 hours using `$where=updated_date>'<yesterday>'`; full re-pull weekly to catch any backdated edits.
- **Freshness expectation**: Staging file `data/raw/building_permits.json` must be no older than **26 hours** before scoring is considered trustworthy. The 26-hour threshold allows a 2-hour grace window over a 24-hour cron cadence.
- **Freshness check**: `python backend/ingest/check_freshness.py`

### 2) Chicago Street Closure Permits (CDOT Street Closures)
- **What it provides**: Planned street/lanes/sidewalk closures, including location, closure start/end, stage details.
- **Why it matters**: Street closures directly map to traffic + pedestrian impact footprints.
- **Expected difficulty**: Medium (spreadsheet-style data; geometry sometimes absent; needs manual normalization).
- **Access method**: Socrata API at `data.cityofchicago.org` (dataset `Ansr-8mav` for right-of-way permits / `u44e-s9pk` for CDOT closures); also available as CSV download from city portal.
- **Ingestion approach**: Pull via Socrata API; normalize closure dates and location into canonical fields; geometry filled via geocoding when absent.
- **Refresh cadence**: Daily. Closures change frequently; pull all records with `close_date >= today - 7 days` to catch recent additions and updates.
- **Freshness expectation**: Staging file `data/raw/street_closures.json` must be no older than **26 hours**. Closures have a shorter relevance horizon than permits; a missed refresh is more likely to leave the scoring engine with stale traffic signal.
- **Freshness check**: `python backend/ingest/check_freshness.py`

## Priority 2 sources

### 3) Chicago DOT Construction Projects (CDOT construction permit data)
- **What it provides**: Larger city-managed projects (pavement, sewer, water main) with planned schedules and impacts.
- **Why it matters**: Captures major infrastructure works not always in typical permit feeds.
- **Expected difficulty**: Medium (data may be in PDF or Excel; may require scraping).
- **Access method**: CDOT project pages and any available Socrata export; check `data.cityofchicago.org` for CDOT-tagged datasets before resorting to scraping.
- **Ingestion approach**: Scrape from CDOT project planner pages or use any available API.
- **Refresh cadence**: Weekly. Major infrastructure projects change slowly; weekly refresh is sufficient for MVP confidence.

### 4) Chicago 311 Service Requests (subset for construction complaints)
- **What it provides**: User-reported complaints about construction noise, blocked sidewalks, etc.
- **Why it matters**: Provides signal on actual disruption impact beyond permit intent.
- **Expected difficulty**: Medium/Hard (large volume, needs filtering, may not align with location precision).
- **Access method**: Socrata API at `data.cityofchicago.org` (dataset `v6vf-nfxy`); filter by `sr_type` for construction and noise complaint categories.
- **Ingestion approach**: Socrata API with filters on request type; store as separate table for later modeling.
- **Refresh cadence**: Daily. High complaint volume for recently opened requests; pull records created or updated in the last 48 hours.

## Priority 3 sources

### 5) Utility outage/repair feeds (ComEd, Peoples Gas, etc.)
- **What it provides**: Scheduled outages or pipeline repairs affecting streets and sidewalks.
- **Why it matters**: Utilities are a common cause of disruption, but feeds are inconsistent.
- **Expected difficulty**: Hard (requires scraping disparate vendor sites or partnering for access).
- **Access method**: No stable public API; ComEd and Peoples Gas publish outage maps via web interface only. Manual CSV exports or screen scraping required.
- **Ingestion approach**: Manual ingestion / one-off CSV exports until a more stable API is found.
- **Refresh cadence**: Ad hoc / manual for MVP. Not suitable for automated daily refresh without a stable feed.

### 6) CTA construction schedules (train/bus stop closures)
- **What it provides**: Planned transit disruptions (station closures, bus route detours).
- **Why it matters**: Transit outages are part of livability disruption but are separate from street permits.
- **Expected difficulty**: Medium/Hard (data often presented as PDF schedules or web pages).
- **Access method**: CTA publishes alerts via `transitchicago.com` and the CTA Alerts API (`lapi.transitchicago.com/api/1.0/alerts.aspx`); structured alert data available in XML/JSON.
- **Ingestion approach**: Manual extraction or targeted scraping; store as separate dataset.
- **Refresh cadence**: Weekly for planned schedules; daily alert pull if the CTA Alerts API is used.
