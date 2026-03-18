# Data Sources (Chicago)

## Priority 1 sources

### 1) Chicago Building Permits (City of Chicago Data Portal)
- **What it provides**: Active and historic building permit records (commercial/residential), including scope of work, permit type, address, issue/expiration dates.
- **Why it matters**: Most construction disruption originates from permitted building work; permits are a stable, public source.
- **Expected difficulty**: Medium (CSV/JSON API with pagination; inconsistent address formatting).
- **Ingestion approach**: Scheduled pull from Socrata API (`data.cityofchicago.org`) + incremental delta using `updated_date`.

### 2) Chicago Street Closure Permits (CDOT Street Closures)
- **What it provides**: Planned street/lanes/sidewalk closures, including location, closure start/end, stage details.
- **Why it matters**: Street closures directly map to traffic + pedestrian impact footprints.
- **Expected difficulty**: Medium (spreadsheet-style data; geometry sometimes absent; needs manual normalization).
- **Ingestion approach**: Download CSV/Excel from city portal or use their Socrata API; normalize into line/point geometries.

## Priority 2 sources

### 3) Chicago DOT Construction Projects (CDOT construction permit data)
- **What it provides**: Larger city-managed projects (pavement, sewer, water main) with planned schedules and impacts.
- **Why it matters**: Captures major infrastructure works not always in typical permit feeds.
- **Expected difficulty**: Medium (data may be in PDF or Excel; may require scraping).
- **Ingestion approach**: Scrape from CDOT project planner pages or use any available API.

### 4) Chicago 311 Service Requests (subset for construction complaints)
- **What it provides**: User-reported complaints about construction noise, blocked sidewalks, etc.
- **Why it matters**: Provides signal on actual disruption impact beyond permit intent.
- **Expected difficulty**: Medium/Hard (large volume, needs filtering, may not align with location precision).
- **Ingestion approach**: Socrata API with filters on request type; store as separate table for later modeling.

## Priority 3 sources

### 5) Utility outage/repair feeds (ComEd, Peoples Gas, etc.)
- **What it provides**: Scheduled outages or pipeline repairs affecting streets and sidewalks.
- **Why it matters**: Utilities are a common cause of disruption, but feeds are inconsistent.
- **Expected difficulty**: Hard (requires scraping disparate vendor sites or partnering for access).
- **Ingestion approach**: Manual ingestion / one-off CSV exports until a more stable API is found.

### 6) CTA construction schedules (train/bus stop closures)
- **What it provides**: Planned transit disruptions (station closures, bus route detours).
- **Why it matters**: Transit outages are part of livability disruption but are separate from street permits.
- **Expected difficulty**: Medium/Hard (data often presented as PDF schedules or web pages).
- **Ingestion approach**: Manual extraction or targeted scraping; store as separate dataset.
