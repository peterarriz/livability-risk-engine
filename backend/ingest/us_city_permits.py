"""
backend/ingest/us_city_permits.py
task: data-038
lane: data

Generic Socrata-based ingest for building permits across the top 10 US cities
by population, all of which publish open data via Socrata portals.

Supported sources (configured in CITY_CONFIGS):
  - New York City  (data.cityofnewyork.us)
  - Los Angeles    (data.lacity.org)
  - Houston        (data.houstontx.gov)
  - Phoenix        (data.phoenix.gov)
  - Philadelphia   (data.phila.gov)
  - San Antonio    (data.sanantonio.gov)
  - San Diego      (data.sandiego.gov)
  - Dallas         (data.dallascityhall.com)
  - Austin         (data.austintexas.gov)

NOT SUPPORTED (no Socrata portal):
  - San Jose — the city uses ArcGIS Hub / GeoHub (gis.sanjoseca.gov).
    A future task can add an ArcGIS REST ingest if needed.

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
        # Dataset: "DOB Permit Issuance" (active building permits from NYC Dept of Buildings)
        # Verified dataset ID: ipu4-2q9a
        # Lat/lon available as gis_latitude / gis_longitude (string floats).
        # Address: house__ + street_name (borough in a separate field).
        "city_name":        "New York City",
        "source_key":       "nyc",
        "domain":           "data.cityofnewyork.us",
        "dataset_id":       "ipu4-2q9a",
        "id_field":         "job__",
        "type_field":       "permit_type",
        "desc_field":       "job_type",
        "issue_date_field": "issuance_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "gis_latitude",
        "lon_field":        "gis_longitude",
        "loc_field":        None,
        "addr_field":       "street_name",
        "city_state":       "New York, NY",
        "where_clause":     None,
    },
    {
        # Los Angeles — Building and Safety Permit Information.
        # Portal: https://data.lacity.org
        # Dataset: "Building and Safety Permit Information" (LADBS)
        # Verified dataset ID: yv23-pmwf
        # Lat/lon available as latitude / longitude.
        "city_name":        "Los Angeles",
        "source_key":       "los_angeles",
        "domain":           "data.lacity.org",
        "dataset_id":       "yv23-pmwf",
        "id_field":         "permit_nbr",
        "type_field":       "permit_type",
        "desc_field":       "work_description",
        "issue_date_field": "issue_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Los Angeles, CA",
        "where_clause":     None,
    },
    {
        # Houston — Building Permits (PWE).
        # Portal: https://data.houstontx.gov
        # Dataset: "Building Permits" (Public Works & Engineering)
        # Verified dataset ID: yqhg-mpp6
        # Lat/lon available as latitude / longitude.
        "city_name":        "Houston",
        "source_key":       "houston",
        "domain":           "data.houstontx.gov",
        "dataset_id":       "yqhg-mpp6",
        "id_field":         "proj_nbr",
        "type_field":       "proj_type",
        "desc_field":       "proj_desc",
        "issue_date_field": "issued_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Houston, TX",
        "where_clause":     None,
    },
    {
        # Phoenix — Development Services Building Permits.
        # Portal: https://data.phoenix.gov
        # Dataset: "Development Services - Building Permits"
        # Verified dataset ID: 4uis-m2e7
        # Lat/lon available as latitude / longitude.
        "city_name":        "Phoenix",
        "source_key":       "phoenix",
        "domain":           "data.phoenix.gov",
        "dataset_id":       "4uis-m2e7",
        "id_field":         "permitno",
        "type_field":       "permittype",
        "desc_field":       "workdescription",
        "issue_date_field": "issuedate",
        "exp_date_field":   "expirationdate",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "siteaddress",
        "city_state":       "Phoenix, AZ",
        "where_clause":     None,
    },
    {
        # Philadelphia — Licenses & Inspections Building Permits.
        # Portal: https://data.phila.gov
        # Dataset: "Licenses and Inspections Building Permits"
        # Verified dataset ID: e5jq-k5ij
        # Lat/lon available as lat / lng.
        "city_name":        "Philadelphia",
        "source_key":       "philadelphia",
        "domain":           "data.phila.gov",
        "dataset_id":       "e5jq-k5ij",
        "id_field":         "permitnumber",
        "type_field":       "permitdescription",
        "desc_field":       "typeofwork",
        "issue_date_field": "permitissuedate",
        "exp_date_field":   "expirationdate",
        "lat_field":        "lat",
        "lon_field":        "lng",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Philadelphia, PA",
        "where_clause":     None,
    },
    {
        # San Antonio — Building Permits (Development Services).
        # Portal: https://data.sanantonio.gov
        # Dataset: "Building Permits"
        # Verified dataset ID: 3par-ddjm
        # Lat/lon available as latitude / longitude.
        "city_name":        "San Antonio",
        "source_key":       "san_antonio",
        "domain":           "data.sanantonio.gov",
        "dataset_id":       "3par-ddjm",
        "id_field":         "applicationnumber",
        "type_field":       "workcategory",
        "desc_field":       "applicationdescription",
        "issue_date_field": "issuedate",
        "exp_date_field":   "expirationdate",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "siteaddress",
        "city_state":       "San Antonio, TX",
        "where_clause":     None,
    },
    {
        # San Diego — Development Services Permits.
        # Portal: https://data.sandiego.gov
        # Dataset: "Building Permits" (Development Services)
        # Verified dataset ID: p3ik-ydxi
        # Lat/lon available as lat / lng.
        "city_name":        "San Diego",
        "source_key":       "san_diego",
        "domain":           "data.sandiego.gov",
        "dataset_id":       "p3ik-ydxi",
        "id_field":         "apno",
        "type_field":       "permittype",
        "desc_field":       "workdescription",
        "issue_date_field": "applydate",
        "exp_date_field":   "expirationdate",
        "lat_field":        "lat",
        "lon_field":        "lng",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "San Diego, CA",
        "where_clause":     None,
    },
    {
        # Dallas — Building Permits.
        # Portal: https://data.dallascityhall.com
        # Dataset: "Building Permits"
        # Verified dataset ID: idr4-wrb3
        # Lat/lon available as latitude / longitude.
        "city_name":        "Dallas",
        "source_key":       "dallas",
        "domain":           "data.dallascityhall.com",
        "dataset_id":       "idr4-wrb3",
        "id_field":         "permit_num",
        "type_field":       "work_type_desc",
        "desc_field":       "permit_desc",
        "issue_date_field": "issued_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Dallas, TX",
        "where_clause":     None,
    },
    {
        # Austin — Issued Construction Permits.
        # Portal: https://data.austintexas.gov
        # Dataset: "Issued Construction Permits"
        # Verified dataset ID: 3syk-w9eu
        # Lat/lon available as latitude / longitude.
        "city_name":        "Austin",
        "source_key":       "austin",
        "domain":           "data.austintexas.gov",
        "dataset_id":       "3syk-w9eu",
        "id_field":         "permit_num",
        "type_field":       "permit_type_desc",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   "expires_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        None,
        "addr_field":       "address",
        "city_state":       "Austin, TX",
        "where_clause":     None,
    },
    # -----------------------------------------------------------------
    # NOT SUPPORTED — no Socrata portal:
    #
    #   San Jose — Uses ArcGIS Hub / GeoHub (gis.sanjoseca.gov), not Socrata.
    #              If needed, implement a separate ArcGIS REST ingest script.
    # -----------------------------------------------------------------

    # -----------------------------------------------------------------
    # STREET CLOSURE DATASETS (NYC confirmed; others TBD)
    # -----------------------------------------------------------------
    {
        # New York City — Street Closure Permits (DOT).
        # Portal: https://data.cityofnewyork.us
        # Dataset: "Street Closure Permits" (NYC Department of Transportation)
        # Verified dataset ID: i6b5-j7bu
        # NOTE: this dataset has no lat/lon — address-only; geocode_fill.py
        # will attempt to geocode the on_street + cross_street fields.
        "city_name":        "New York City Street Closures",
        "source_key":       "nyc_street_closures",
        "domain":           "data.cityofnewyork.us",
        "dataset_id":       "i6b5-j7bu",
        "id_field":         "objectid",
        "type_field":       "work_type",
        "desc_field":       "purpose",
        "issue_date_field": "startdate",
        "exp_date_field":   "enddate",
        "lat_field":        None,
        "lon_field":        None,
        "loc_field":        None,
        "addr_field":       "on_street",
        "city_state":       "New York, NY",
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime("%Y-%m-%dT00:00:00")

    date_field = config["issue_date_field"]
    where_parts = [f"{date_field} >= '{cutoff_str}'"]

    if config.get("where_clause"):
        where_parts.append(config["where_clause"])

    params: dict = {
        "$limit":  limit,
        "$offset": offset,
        "$where":  " AND ".join(where_parts),
        "$order":  f"{date_field} DESC",
    }

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

    return {
        "source_key":      config["source_key"],
        "city_name":       config["city_name"],
        "city_state":      config.get("city_state", config["city_name"]),
        "source_id":       _extract_source_id(record, config),
        "permit_type":     record.get(config["type_field"], "") or "",
        "description":     record.get(config["desc_field"], "") or "",
        "issue_date":      record.get(config["issue_date_field"], "") or "",
        "expiration_date": record.get(config.get("exp_date_field") or "", "") or "",
        "address":         record.get(config["addr_field"], "") or "",
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
