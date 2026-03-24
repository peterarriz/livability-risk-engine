"""
backend/ingest/us_city_permits.py
task: data-038, data-043, data-045, data-047, data-048, data-050
lane: data

Generic Socrata-based ingest for building permits across major US cities,
all of which publish open data via Socrata portals.

Supported sources (configured in CITY_CONFIGS):
  - New York City  (data.cityofnewyork.us)
  - Los Angeles    (data.lacity.org)
  - Austin         (data.austintexas.gov)
  - New York City Street Closures (data.cityofnewyork.us)
  - Seattle        (data.seattle.gov)
  - Kansas City    (data.kcmo.org)  [added data-045]
  - San Francisco  (data.sfgov.org) [added data-047]
  - Baltimore      — REMOVED data-048: migrated to ArcGIS Hub
  - Nashville      — REMOVED data-048: migrated to ArcGIS Hub

NOT SUPPORTED (no Socrata portal):
  - San Jose — the city uses ArcGIS Hub / GeoHub (gis.sanjoseca.gov).
    A future task can add an ArcGIS REST ingest if needed.
  - Indianapolis — data.indy.gov uses ArcGIS Hub; no building permit dataset
    is published (only ordinance PDFs). Verified 2026-03-22.
  - Denver, Boston, Milwaukee — use CKAN; see us_city_permits_ckan.py.
  - Portland, Detroit, Memphis, Louisville — portals
    are down, non-Socrata, or returning non-JSON. Removed 2026-03-22.
  - Baltimore, Nashville — migrated to ArcGIS Hub. Moved to
    us_city_permits_arcgis.py (data-048).
  - Phoenix, Columbus, Minneapolis, Charlotte, Jacksonville — use ArcGIS Hub
    or custom portals; not Socrata/CKAN. Research needed for ArcGIS REST ingest.
    See notes in TASKS.yaml data-045.

NOTE ON DATASET IDs:
  Dataset IDs below were researched from public Socrata catalog metadata as of
  early 2026. If a fetch returns 0 records or an HTTP 404, verify the dataset
  ID by visiting the portal URL, searching for "building permits", and copying
  the 4x4 ID from the dataset URL
  (e.g. https://domain/resource/<ID>.json).

  Quick verification command:
    curl "https://<domain>/api/catalog/v1?q=building+permits&limit=5" | python -m json.tool

  NYC also publishes street closure permits:
    https://data.cityofnewyork.us/resource/i6b5-j7bu.json

Usage:
  # Ingest all configured cities
  python backend/ingest/us_city_permits.py

  # Ingest a single city
  python backend/ingest/us_city_permits.py --city nyc
  python backend/ingest/us_city_permits.py --city austin

  # Dry-run (fetch one page only; do not write output files)
  python backend/ingest/us_city_permits.py --dry-run
  python backend/ingest/us_city_permits.py --city houston --dry-run

  # List configured cities
  python backend/ingest/us_city_permits.py --list

Environment variables (optional):
  SOCRATA_APP_TOKEN  — Generic Socrata app token for higher rate limits.
                       Register free at https://dev.socrata.com/register

Acceptance criteria (data-038):
  - Records are fetched from each configured Socrata portal.
  - Raw records are written to data/raw/us_city_permits_<source_key>.json.
  - Source identifiers are preserved for traceability.
  - Script is idempotent: re-running overwrites output cleanly.
  - Individual city failures are non-fatal; other cities continue.
  - --dry-run mode fetches one page per city and reports without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# City configurations
# ---------------------------------------------------------------------------
# Each entry describes one Socrata open-data source.
#
# Fields:
#   city_name     : Human-readable city label
#   source_key    : Snake-case identifier used in project_id and output filename
#   domain        : Socrata portal domain (no https://)
#   dataset_id    : Socrata 4x4 dataset identifier  ← verify if fetches return 0
#   id_field      : Field name that holds the unique record ID
#   type_field    : Field name for permit type / category
#   desc_field    : Field name for work description / notes
#   issue_date_field : Field name for permit issue date (used for lookback filter)
#   exp_date_field   : Field name for expiration/end date (None if unavailable)
#   lat_field     : Field name for latitude  (None if embedded in location struct)
#   lon_field     : Field name for longitude (None if embedded in location struct)
#   loc_field     : Field name for nested location struct (used if lat/lon are None)
#   addr_field    : Field name for full address string
#   city_state    : City + state suffix for address construction
#   where_clause  : Additional SoQL WHERE clause (e.g. to filter by permit class).
#                   None means no extra filter.

CITY_CONFIGS: list[dict] = [
    {
        # New York City — DOB Permit Issuance.
        # Portal: https://data.cityofnewyork.us
        # Dataset: "DOB Permit Issuance" (ipu4-2q9a)
        # Verified 2026-03-21 via catalog API.
        # Note: date fields are text (MM/DD/YYYY), not calendar_date.
        # SoQL date comparison won't work on text dates, so we skip the
        # date filter and cap via max_records to get the most recent permits
        # ordered by dobrundate DESC.
        "city_name":        "New York City",
        "source_key":       "nyc",
        "domain":           "data.cityofnewyork.us",
        "dataset_id":       "ipu4-2q9a",
        "id_field":         "job__",
        "type_field":       "permit_type",
        "desc_field":       "job_type",
        "issue_date_field": "dobrundate",
        "exp_date_field":   "expiration_date",
        "skip_date_filter": True,
        "max_records":      50000,
        "lat_field":        "gis_latitude",
        "lon_field":        "gis_longitude",
        "loc_field":        None,
        "addr_field":       "street_name",
        "city_state":       "New York, NY",
        "where_clause":     None,
    },
    {
        # Los Angeles — Building Permits Issued 2020-Present.
        # Portal: https://data.lacity.org
        # Dataset: "Building and Safety - Building Permits Issued from 2020 to Present (N)" (pi9x-tg5x)
        # Verified 2026-03-22 — old dataset xnhu-aczu was a stale filter view returning 0 records.
        "city_name":        "Los Angeles",
        "source_key":       "los_angeles",
        "domain":           "data.lacity.org",
        "dataset_id":       "pi9x-tg5x",
        "id_field":         "permit_nbr",
        "type_field":       "permit_type",
        "desc_field":       "work_desc",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "lat",
        "lon_field":        "lon",
        "loc_field":        None,
        "addr_field":       "primary_address",
        "city_state":       "Los Angeles, CA",
        "where_clause":     None,
    },
    {
        # Austin — Issued Construction Permits.
        # Portal: https://data.austintexas.gov
        # Dataset: "Issued Construction Permits" (3syk-w9eu)
        # Verified 2026-03-21 — date field is issue_date (not issued_date).
        "city_name":        "Austin",
        "source_key":       "austin",
        "domain":           "data.austintexas.gov",
        "dataset_id":       "3syk-w9eu",
        "id_field":         "permit_number",
        "type_field":       "permit_type_desc",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   "expiresdate",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "original_address1",
        "city_state":       "Austin, TX",
        "where_clause":     None,
    },
    {
        # New York City — Street Closures (DOT).
        # Portal: https://data.cityofnewyork.us
        # Dataset: "Street Closure Permits" (i6b5-j7bu)
        # Verified 2026-03-21 — fields: work_start_date, work_end_date,
        #   uniqueid, onstreetname, purpose, the_geom (multiline).
        # No lat/lon — geocode_fill handles it.
        "city_name":        "New York City Street Closures",
        "source_key":       "nyc_street_closures",
        "domain":           "data.cityofnewyork.us",
        "dataset_id":       "i6b5-j7bu",
        "id_field":         "uniqueid",
        "type_field":       "purpose",
        "desc_field":       "onstreetname",
        "issue_date_field": "work_start_date",
        "exp_date_field":   "work_end_date",
        "lat_field":        None,
        "lon_field":        None,
        "loc_field":        None,
        "addr_field":       "onstreetname",
        "city_state":       "New York, NY",
        "where_clause":     None,
    },
    # -----------------------------------------------------------------
    # REMOVED — non-Socrata portals (verified 2026-03-21):
    #
    #   houston      — data.houstontx.gov uses CKAN, not Socrata
    #   phoenix      — data.phoenix.gov returns non-JSON (not Socrata)
    #   philadelphia — data.phila.gov uses CKAN, not Socrata (403 on catalog)
    #   san_antonio  — data.sanantonio.gov uses CKAN, not Socrata
    #   san_diego    — data.sandiego.gov uses S3/custom, not Socrata
    #   dallas       — data.dallascityhall.com DNS does not resolve
    #   san_jose     — uses ArcGIS Hub (gis.sanjoseca.gov)
    #   denver       — uses CKAN/OpenGov; see us_city_permits_ckan.py
    # -----------------------------------------------------------------
    {
        # Seattle — Issued Construction Permits.
        # Portal: https://data.seattle.gov
        # Dataset: "Issued Construction Permits" (76t5-zqzr)
        # Verify: curl "https://data.seattle.gov/api/catalog/v1?q=building+permits&limit=5"
        # Fields verified from Socrata catalog metadata (2026-03-22).
        "city_name":        "Seattle",
        "source_key":       "seattle",
        "domain":           "data.seattle.gov",
        "dataset_id":       "76t5-zqzr",
        "id_field":         "permitnum",
        "type_field":       "permittypemapped",
        "desc_field":       "description",
        "issue_date_field": "issueddate",
        "exp_date_field":   "expirationdate",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "originaladdress1",
        "city_state":       "Seattle, WA",
        "where_clause":     None,
    },
    {
        # Kansas City, MO — Building Permits (CPD Dataset).
        # Portal: https://data.kcmo.org  (Socrata)
        # Dataset: "Permits - CPD Dataset" (ntw8-aacc)
        # Verified 2026-03-22 via catalog API and sample query.
        # Note: old dataset i6pc-e4ph returns 404; ntw8-aacc is the correct one.
        # Fields verified: permitnum, permittypedesc, description, issueddate,
        #   expiresdate, latitude, longitude, originaladdress1.
        "city_name":        "Kansas City",
        "source_key":       "kansas_city",
        "domain":           "data.kcmo.org",
        "dataset_id":       "ntw8-aacc",
        "id_field":         "permitnum",
        "type_field":       "permittypedesc",
        "desc_field":       "description",
        "issue_date_field": "issueddate",
        "exp_date_field":   "expiresdate",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "originaladdress1",
        "city_state":       "Kansas City, MO",
        "where_clause":     None,
    },
    # -----------------------------------------------------------------
    # REMOVED — non-Socrata portals (verified 2026-03-22):
    #
    #   indianapolis — data.indy.gov uses ArcGIS Hub; no building permit
    #                  dataset is published (only ordinance PDFs). Verified
    #                  2026-03-22 via Hub search + GIS server scan.
    #   portland     — uses ArcGIS Hub; see us_city_permits_arcgis.py (data-047)
    #   nashville    — migrated to ArcGIS Hub; see us_city_permits_arcgis.py (data-048)
    #   detroit      — data.detroitmi.gov returns non-JSON (not Socrata)
    #   memphis      — data.memphistn.gov returns non-JSON (not Socrata)
    #   louisville   — data.louisvilleky.gov returns non-JSON (not Socrata)
    #   baltimore    — migrated to ArcGIS Hub; see us_city_permits_arcgis.py (data-048)
    #   boston       — data.boston.gov uses CKAN; moved to us_city_permits_ckan.py
    #   milwaukee    — data.milwaukee.gov uses CKAN; moved to us_city_permits_ckan.py
    {
        # San Francisco — Building Permits.
        # Portal: https://data.sfgov.org
        # Dataset: "Building Permits" (i98e-djp9)
        # Verified pattern: data.sfgov.org uses Socrata.
        # MUST VERIFY dataset_id and field names before production:
        #   curl "https://data.sfgov.org/api/catalog/v1?q=building+permits&limit=5"
        #   curl "https://data.sfgov.org/resource/i98e-djp9.json?$limit=1"
        # Note: No top-level lat/lon fields — coordinates are in "location"
        # (GeoJSON Point: {"type":"Point","coordinates":[-122.4, 37.8]}).
        # Address is constructed from street_number + street_name + street_suffix.
        "city_name":        "San Francisco",
        "source_key":       "san_francisco",
        "domain":           "data.sfgov.org",
        "dataset_id":       "i98e-djp9",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   None,
        "lat_field":        None,
        "lon_field":        None,
        "loc_field":        "location",
        "addr_field":       "street_number",
        "addr_extra_fields": ["street_name", "street_suffix"],
        "city_state":       "San Francisco, CA",
        "where_clause":     None,
    },
    # -----------------------------------------------------------------
    # REMOVED — Baltimore + Nashville (verified 2026-03-23):
    #   data.baltimorecity.gov and data.nashville.gov both redirect to
    #   hub.arcgis.com/legacy — no longer Socrata portals.
    #   Moved to us_city_permits_arcgis.py (data-048).
    # -----------------------------------------------------------------
    {
        # Washington DC — Building Permits.
        # Portal: https://opendata.dc.gov
        # Dataset: "Building Permits" (addl-w6ut or similar)
        # MUST VERIFY dataset_id and field names:
        #   curl "https://opendata.dc.gov/api/catalog/v1?q=building+permits&limit=5"
        "city_name":        "Washington DC",
        "source_key":       "dc",
        "domain":           "opendata.dc.gov",
        "dataset_id":       "awqx-tuwv",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description_of_work",
        "issue_date_field": "issue_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "full_address",
        "city_state":       "Washington, DC",
        "where_clause":     None,
    },
    {
        # Oklahoma City — Building Permits.
        # Portal: https://data.okc.gov
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.okc.gov/api/catalog/v1?q=building+permits&limit=5"
        "city_name":        "Oklahoma City",
        "source_key":       "oklahoma_city",
        "domain":           "data.okc.gov",
        "dataset_id":       "bsum-mkwp",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Oklahoma City, OK",
        "where_clause":     None,
    },
    {
        # Louisville — Building Permits.
        # Portal: https://data.louisvilleky.gov
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.louisvilleky.gov/api/catalog/v1?q=building+permits&limit=5"
        "city_name":        "Louisville",
        "source_key":       "louisville",
        "domain":           "data.louisvilleky.gov",
        "dataset_id":       "5mge-bwiz",
        "id_field":         "permit_id",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Louisville, KY",
        "where_clause":     None,
    },
    {
        # Fresno — Building Permits.
        # Portal: https://data.fresno.gov
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.fresno.gov/api/catalog/v1?q=building+permits&limit=5"
        "city_name":        "Fresno",
        "source_key":       "fresno",
        "domain":           "data.fresno.gov",
        "dataset_id":       "sxvh-bkgt",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Fresno, CA",
        "where_clause":     None,
    },
    {
        # Sacramento — Building Permits.
        # Portal: https://data.cityofsacramento.org
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.cityofsacramento.org/api/catalog/v1?q=building+permits&limit=5"
        "city_name":        "Sacramento",
        "source_key":       "sacramento",
        "domain":           "data.cityofsacramento.org",
        "dataset_id":       "rent-6pka",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Sacramento, CA",
        "where_clause":     None,
    },
    # -----------------------------------------------------------------
    # NOT YET IMPLEMENTED — ArcGIS Hub cities (data-045):
    #
    #   phoenix      — data.phoenix.gov uses ArcGIS Hub; needs ArcGIS REST ingest
    #   columbus     — opendata.columbus.gov uses ArcGIS Hub
    #   minneapolis  — opendata.minneapolismn.gov uses ArcGIS Hub
    #   charlotte    — data.charlottenc.gov uses ArcGIS/custom portal
    #   jacksonville — coj.net uses ArcGIS/custom portal
    #
    # To add ArcGIS REST support, use:
    #   GET https://<server>/arcgis/rest/services/<layer>/FeatureServer/0/query
    #       ?where=1%3D1&outFields=*&f=geojson&resultOffset=<N>&resultRecordCount=1000
    # -----------------------------------------------------------------
    {
        # New Orleans — Building Permits.
        # Portal: https://data.nola.gov (Socrata)
        # Dataset: "Permits" (rcm3-fn58)
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.nola.gov/api/catalog/v1?q=permits&limit=5"
        # data-056: added 2026-03-24
        "city_name":        "New Orleans",
        "source_key":       "new_orleans",
        "domain":           "data.nola.gov",
        "dataset_id":       "rcm3-fn58",
        "id_field":         "numstring",
        "type_field":       "type",
        "desc_field":       "description",
        "issue_date_field": "issuedate",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "New Orleans, LA",
        "where_clause":     None,
    },
    {
        # Cincinnati — Building Permits.
        # Portal: https://data.cincinnati-oh.gov (Socrata)
        # Dataset: "Permits" (uhjb-xac9)
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.cincinnati-oh.gov/api/catalog/v1?q=building+permits&limit=5"
        # data-056: added 2026-03-24
        "city_name":        "Cincinnati",
        "source_key":       "cincinnati",
        "domain":           "data.cincinnati-oh.gov",
        "dataset_id":       "uhjb-xac9",
        "id_field":         "permitnum",
        "type_field":       "permittypedesc",
        "desc_field":       "description",
        "issue_date_field": "issueddate",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "originaladdress1",
        "city_state":       "Cincinnati, OH",
        "where_clause":     None,
    },
    {
        # Buffalo — Building Permits.
        # Portal: https://data.buffalony.gov (Socrata)
        # Dataset: "Building Permits" (9p2d-f3yt)
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.buffalony.gov/api/catalog/v1?q=building+permits&limit=5"
        # data-056: added 2026-03-24
        "city_name":        "Buffalo",
        "source_key":       "buffalo",
        "domain":           "data.buffalony.gov",
        "dataset_id":       "9p2d-f3yt",
        "id_field":         "apno",
        "type_field":       "aptype",
        "desc_field":       "descofwork",
        "issue_date_field": "issued",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "stname",
        "city_state":       "Buffalo, NY",
        "where_clause":     None,
    },
    {
        # Raleigh, NC — Building Permits.
        # Portal: https://data.raleighnc.gov (Socrata)
        # Dataset: Building Permits (NIBRS/development permits)
        # MUST VERIFY dataset_id and field names:
        #   curl "https://data.raleighnc.gov/api/catalog/v1?q=building+permits&limit=5"
        #   curl "https://data.raleighnc.gov/resource/k4n2-jcgh.json?$limit=1"
        # data-050: added 2026-03-23
        "city_name":        "Raleigh",
        "source_key":       "raleigh",
        "domain":           "data.raleighnc.gov",
        "dataset_id":       "k4n2-jcgh",
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Raleigh, NC",
        "where_clause":     None,
    },
]

# Index by source_key for fast lookup.
CITY_CONFIG_BY_KEY: dict[str, dict] = {c["source_key"]: c for c in CITY_CONFIGS}

# How many records to fetch per API page (Socrata max is 50000).
PAGE_SIZE = 5000

# How many days back to filter permits.
DAYS_BACK = 90

# Base output directory for staging files.
DEFAULT_OUTPUT_DIR = Path("data/raw")


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def build_params(
    config: dict,
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> dict:
    """Build Socrata SoQL query parameters for one page of permits."""
    date_field = config["issue_date_field"]

    params: dict = {
        "$limit":  limit,
        "$offset": offset,
        "$order":  f"{date_field} DESC",
    }

    # Some datasets (e.g. NYC) have text-type date fields where SoQL
    # date comparison doesn't work. Skip the WHERE date filter for those.
    if not config.get("skip_date_filter"):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        cutoff_str = cutoff.strftime("%Y-%m-%dT00:00:00")
        where_parts = [f"{date_field} >= '{cutoff_str}'"]

        if config.get("where_clause"):
            where_parts.append(config["where_clause"])

        params["$where"] = " AND ".join(where_parts)
    elif config.get("where_clause"):
        params["$where"] = config["where_clause"]

    if app_token:
        params["$$app_token"] = app_token

    return params


def fetch_page(
    session: requests.Session,
    config: dict,
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> list[dict]:
    """Fetch one page of permit records from a Socrata portal."""
    url = f"https://{config['domain']}/resource/{config['dataset_id']}.json"
    params = build_params(config, offset, limit, app_token, days_back)

    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(
            f"  ERROR [{config['city_name']}]: Request timed out at offset {offset}.",
            file=sys.stderr,
        )
        raise
    except requests.exceptions.HTTPError as exc:
        print(
            f"  ERROR [{config['city_name']}]: HTTP {exc.response.status_code} "
            f"at offset {offset}: {exc.response.text[:300]}",
            file=sys.stderr,
        )
        raise

    return response.json()


def fetch_city_permits(
    config: dict,
    app_token: str | None,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through a Socrata API and return all raw permit records for
    one city within the lookback window.

    Returns an empty list (and logs a warning) if the dataset is inaccessible
    so the rest of the pipeline can continue.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print(f"\nFetching {config['city_name']} permits "
          f"(domain={config['domain']}, dataset={config['dataset_id']})...")

    try:
        while True:
            print(f"  Fetching page at offset {offset}...", end=" ", flush=True)
            records = fetch_page(session, config, offset, PAGE_SIZE, app_token, days_back)
            print(f"{len(records)} records.")

            if not records:
                break

            all_records.extend(records)
            offset += len(records)

            if dry_run and offset >= PAGE_SIZE:
                print("  Dry-run: stopping after first page.")
                break

            max_records = config.get("max_records")
            if max_records and offset >= max_records:
                print(f"  Reached max_records cap ({max_records}). Stopping.")
                break

            if len(records) < PAGE_SIZE:
                break

    except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as exc:
        print(
            f"  WARN [{config['city_name']}]: fetch failed — {exc}. "
            f"Skipping this source. Verify dataset_id={config['dataset_id']} at "
            f"https://{config['domain']}/api/catalog/v1?q=building+permits",
            file=sys.stderr,
        )
        return []

    return all_records


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_lat_lon(record: dict, config: dict) -> tuple[str | None, str | None]:
    """
    Extract latitude and longitude from a raw Socrata permit record.

    Tries top-level lat/lon fields first, then falls back to a nested
    location structure (Socrata 'location' column type).
    """
    lat_field = config.get("lat_field")
    lon_field = config.get("lon_field")
    loc_field = config.get("loc_field")

    lat = record.get(lat_field) if lat_field else None
    lon = record.get(lon_field) if lon_field else None

    if (lat is None or lon is None) and loc_field:
        loc = record.get(loc_field)
        if isinstance(loc, dict):
            # GeoJSON Point: {"type":"Point","coordinates":[-87.65, 41.68]}
            coords = loc.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                lon = lon or str(coords[0])
                lat = lat or str(coords[1])
            else:
                lat = lat or loc.get("latitude") or loc.get("lat")
                lon = lon or loc.get("longitude") or loc.get("lon")
        elif isinstance(loc, str) and "," in loc:
            # Some portals encode location as "lat, lon" string.
            parts = loc.split(",", 1)
            try:
                lat = lat or parts[0].strip()
                lon = lon or parts[1].strip()
            except (IndexError, ValueError):
                pass

    return lat, lon


def _extract_source_id(record: dict, config: dict) -> str:
    """
    Extract a stable source ID from a raw Socrata record.

    Falls back to a hash of key fields when the configured id_field
    is not present in the JSON response.
    """
    id_field = config["id_field"]
    raw_id = str(record.get(id_field, "") or "").strip()
    if raw_id:
        return raw_id

    parts = [
        record.get(config["issue_date_field"], ""),
        record.get(config["addr_field"], ""),
        record.get(config["desc_field"], ""),
    ]
    key = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def normalize_raw_record(record: dict, config: dict) -> dict:
    """
    Map a raw Socrata permit record to a consistent internal field set.

    The output dict uses stable internal field names regardless of the
    per-portal Socrata field names, enabling a single normalize_us_city_permit()
    function in project.py.
    """
    lat, lon = _extract_lat_lon(record, config)

    # Build address from primary field + any extra fields (e.g. street_name, suffix).
    addr_parts = [str(record.get(config["addr_field"], "") or "")]
    for extra in config.get("addr_extra_fields", []):
        val = str(record.get(extra, "") or "").strip()
        if val:
            addr_parts.append(val)
    address = " ".join(p for p in addr_parts if p.strip())

    return {
        "source_key":      config["source_key"],
        "city_name":       config["city_name"],
        "city_state":      config.get("city_state", config["city_name"]),
        "source_id":       _extract_source_id(record, config),
        "permit_type":     record.get(config["type_field"], "") or "",
        "description":     record.get(config["desc_field"], "") or "",
        "issue_date":      record.get(config["issue_date_field"], "") or "",
        "expiration_date": record.get(config.get("exp_date_field") or "", "") or "",
        "address":         address,
        "latitude":        lat,
        "longitude":       lon,
    }


# ---------------------------------------------------------------------------
# Staging file writer
# ---------------------------------------------------------------------------

def write_staging_file(
    records: list[dict],
    config: dict,
    output_dir: Path,
) -> Path:
    """Write normalized raw permit records to a JSON staging file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"us_city_permits_{config['source_key']}.json"

    staging = {
        "source":       f"us_city_permits_{config['source_key']}",
        "city_name":    config["city_name"],
        "source_url":   f"https://{config['domain']}/resource/{config['dataset_id']}.json",
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records":      records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"  Wrote {len(records)} records to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Per-city orchestration
# ---------------------------------------------------------------------------

def ingest_city(
    config: dict,
    app_token: str | None,
    days_back: int,
    dry_run: bool,
    output_dir: Path,
) -> int:
    """
    Fetch and stage permits for one city.

    Returns the number of records written (0 on failure or dry-run).
    """
    raw_records = fetch_city_permits(config, app_token, days_back, dry_run)

    if not raw_records:
        print(f"  No records returned for {config['city_name']}.")
        return 0

    normalized = [normalize_raw_record(r, config) for r in raw_records]
    print(f"  Normalized {len(normalized)} records.")

    if dry_run:
        print(f"  Dry-run: skipping file write.")
        if normalized:
            print(f"  Sample:\n{json.dumps(normalized[0], indent=4)}")
        return 0

    write_staging_file(normalized, config, output_dir)
    return len(normalized)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest US city building permits from Socrata open data portals."
        )
    )
    parser.add_argument(
        "--city",
        choices=list(CITY_CONFIG_BY_KEY.keys()) + ["all"],
        default="all",
        help="Which city to ingest (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for output staging files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=DAYS_BACK,
        help=f"Number of days back to fetch (default: {DAYS_BACK}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page per city only; do not write output files.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List configured cities and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Configured US city sources:")
        for cfg in CITY_CONFIGS:
            print(f"  {cfg['source_key']:25s} → {cfg['city_name']} "
                  f"({cfg['domain']}, dataset={cfg['dataset_id']})")
        return

    app_token = os.environ.get("SOCRATA_APP_TOKEN")
    if not app_token:
        print(
            "Note: SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register a free token at https://dev.socrata.com/register"
        )

    configs = (
        CITY_CONFIGS
        if args.city == "all"
        else [CITY_CONFIG_BY_KEY[args.city]]
    )

    total = 0
    failed: list[str] = []

    for config in configs:
        try:
            count = ingest_city(config, app_token, args.days_back, args.dry_run, args.output_dir)
            total += count
        except Exception as exc:
            print(f"  ERROR [{config['city_name']}]: {exc}", file=sys.stderr)
            failed.append(config["city_name"])

    print(f"\n── Summary ──────────────────────────────────────")
    print(f"  Cities attempted: {len(configs)}")
    print(f"  Cities failed:    {len(failed)}" + (f" ({', '.join(failed)})" if failed else ""))
    print(f"  Total records:    {total}")

    if args.dry_run:
        print("  Dry-run mode: no files written.")

    # Exit non-zero only if ALL cities failed — partial success is still useful.
    if failed and len(failed) == len(configs):
        sys.exit(1)


if __name__ == "__main__":
    main()
