# Data Sources (Multi-City)

## City coverage registry expansion (data-086)

The canonical city registry is `city_coverage` in `db/schema.sql`, seeded by
`db/migrations/add_city_coverage_registry.sql` and mirrored for review in
`data/city_coverage_seed.json`.

The 50 cities below were selected from repo-backed generated evidence in
`data/generated/data_flow_simulation.json` and existing context loaders in
`backend/ingest/load_neighborhood_quality.py`. They intentionally exclude
Chicago and cities already represented by the current permit/closure adapter
configs. These rows do **not** seed synthetic construction projects; they mark
known contextual coverage until city-specific permit or closure feeds are
connected and validated.

| City | State | Coverage | Source key | Staging file | Sim records | Latest score |
| --- | --- | --- | --- | --- | ---: | ---: |
| Cape Coral | FL | contextual_only | crime_cape_coral | `data/raw/cape_coral_crime_trends.json` | 14 | 29 |
| Chandler | AZ | contextual_only | crime_chandler | `data/raw/chandler_crime_trends.json` | 14 | 25 |
| Durham | NC | contextual_only | crime_durham | `data/raw/durham_crime_trends.json` | 14 | 25 |
| Indianapolis | IN | contextual_only | crime_indianapolis | `data/raw/indianapolis_crime_trends.json` | 14 | 31 |
| Providence | RI | contextual_only | crime_providence | `data/raw/providence_crime_trends.json` | 14 | 23 |
| Sacramento | CA | contextual_only | crime_sacramento | `data/raw/sacramento_crime_trends.json` | 14 | 23 |
| St. Paul | MN | contextual_only | crime_st_paul | `data/raw/st_paul_crime_trends.json` | 14 | 24 |
| Virginia Beach | VA | contextual_only | crime_virginia_beach | `data/raw/virginia_beach_crime_trends.json` | 14 | 29 |
| Akron | OH | contextual_only | crime_akron | `data/raw/akron_crime_trends.json` | 13 | 29 |
| Atlanta | GA | contextual_only | crime_atlanta | `data/raw/atlanta_crime_trends.json` | 13 | 27 |
| Birmingham | AL | contextual_only | crime_birmingham | `data/raw/birmingham_crime_trends.json` | 13 | 20 |
| Chattanooga | TN | contextual_only | crime_chattanooga | `data/raw/chattanooga_crime_trends.json` | 13 | 25 |
| Colorado Springs | CO | contextual_only | crime_colorado_springs | `data/raw/colorado_springs_crime_trends.json` | 13 | 24 |
| Gilbert | AZ | contextual_only | crime_gilbert | `data/raw/gilbert_crime_trends.json` | 13 | 25 |
| Jersey City | NJ | contextual_only | crime_jersey_city | `data/raw/jersey_city_crime_trends.json` | 13 | 26 |
| Memphis | TN | contextual_only | crime_memphis | `data/raw/memphis_crime_trends.json` | 13 | 29 |
| Miami | FL | contextual_only | crime_miami | `data/raw/miami_crime_trends.json` | 13 | 25 |
| Oakland | CA | contextual_only | crime_oakland | `data/raw/oakland_crime_trends.json` | 13 | 22 |
| Omaha | NE | contextual_only | crime_omaha | `data/raw/omaha_crime_trends.json` | 13 | 24 |
| Orlando | FL | contextual_only | crime_orlando | `data/raw/orlando_crime_trends.json` | 13 | 27 |
| Pittsburgh | PA | contextual_only | crime_pittsburgh | `data/raw/pittsburgh_crime_trends.json` | 13 | 28 |
| Albuquerque | NM | contextual_only | crime_albuquerque | `data/raw/albuquerque_crime_trends.json` | 12 | 30 |
| Arlington | TX | contextual_only | crime_arlington_tx | `data/raw/arlington_tx_crime_trends.json` | 12 | 29 |
| Aurora | CO | contextual_only | crime_aurora | `data/raw/aurora_crime_trends.json` | 12 | 28 |
| Boise | ID | contextual_only | crime_boise | `data/raw/boise_crime_trends.json` | 12 | 29 |
| Cary | NC | contextual_only | crime_cary | `data/raw/cary_crime_trends.json` | 12 | 24 |
| Cedar Park | TX | contextual_only | crime_cedar_park_tx | `data/raw/cedar_park_tx_crime_trends.json` | 12 | 27 |
| Cleveland | OH | contextual_only | crime_cleveland | `data/raw/cleveland_crime_trends.json` | 12 | 29 |
| Dallas | TX | contextual_only | crime_dallas | `data/raw/dallas_crime_trends.json` | 12 | 29 |
| El Paso | TX | contextual_only | crime_el_paso | `data/raw/el_paso_crime_trends.json` | 12 | 28 |
| Eugene | OR | contextual_only | crime_eugene | `data/raw/eugene_crime_trends.json` | 12 | 21 |
| Fayetteville | NC | contextual_only | crime_fayetteville_nc | `data/raw/fayetteville_nc_crime_trends.json` | 12 | 20 |
| Fort Wayne | IN | contextual_only | crime_fort_wayne | `data/raw/fort_wayne_crime_trends.json` | 12 | 23 |
| Fresno | CA | contextual_only | crime_fresno | `data/raw/fresno_crime_trends.json` | 12 | 27 |
| Frisco | TX | contextual_only | crime_frisco_tx | `data/raw/frisco_tx_crime_trends.json` | 12 | 26 |
| Garland | TX | contextual_only | crime_garland_tx | `data/raw/garland_tx_crime_trends.json` | 12 | 30 |
| Glendale | AZ | contextual_only | crime_glendale_az | `data/raw/glendale_az_crime_trends.json` | 12 | 21 |
| Goodyear | AZ | contextual_only | crime_goodyear_az | `data/raw/goodyear_az_crime_trends.json` | 12 | 26 |
| Grand Rapids | MI | contextual_only | crime_grand_rapids | `data/raw/grand_rapids_crime_trends.json` | 12 | 30 |
| Henderson | NV | contextual_only | crime_henderson | `data/raw/henderson_crime_trends.json` | 12 | 20 |
| Honolulu | HI | contextual_only | crime_honolulu | `data/raw/honolulu_crime_trends.json` | 12 | 22 |
| Houston | TX | contextual_only | crime_houston | `data/raw/houston_crime_trends.json` | 12 | 22 |
| Huntsville | AL | contextual_only | crime_huntsville | `data/raw/huntsville_crime_trends.json` | 12 | 30 |
| Jacksonville | FL | contextual_only | crime_jacksonville | `data/raw/jacksonville_crime_trends.json` | 12 | 31 |
| Knoxville | TN | contextual_only | crime_knoxville | `data/raw/knoxville_crime_trends.json` | 12 | 26 |
| Laredo | TX | contextual_only | crime_laredo_tx | `data/raw/laredo_tx_crime_trends.json` | 12 | 29 |
| Lexington | KY | contextual_only | crime_lexington | `data/raw/lexington_crime_trends.json` | 12 | 20 |
| Lincoln | NE | contextual_only | crime_lincoln | `data/raw/lincoln_crime_trends.json` | 12 | 22 |
| Long Beach | CA | contextual_only | crime_long_beach | `data/raw/long_beach_crime_trends.json` | 12 | 26 |
| Lubbock | TX | contextual_only | crime_lubbock_tx | `data/raw/lubbock_tx_crime_trends.json` | 12 | 25 |

Common caveat for all 50 rows: context signals can inform evidence quality,
livability context, and buyer-facing coverage copy, but address-level
construction disruption confidence remains sparse until a city-specific permit,
closure, or infrastructure project feed is connected.

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
