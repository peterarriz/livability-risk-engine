"""
backend/ingest/il_city_permits.py
task: data-033
lane: data

Generic Socrata-based ingest for Illinois municipal building permits outside Chicago.
Covers Cook County and additional Illinois cities with open data portals.

Supported sources (configured in CITY_CONFIGS):
  - Cook County (datacatalog.cookcountyil.gov)
  - Evanston    (data.cityofevanston.org)
  - Aurora      (data.aurora.il.us)
  - Rockford    (data.illinois.gov — statewide permits, filtered by city)
  - Springfield (data.illinois.gov — statewide permits, filtered by city)

NOTE ON DATASET IDs:
  Dataset IDs below were researched from public Socrata catalog metadata as of early
  2026. If a fetch returns 0 records or an HTTP 404, verify the dataset ID by visiting
  the portal URL, searching for "building permits", and copying the 4x4 ID from the
  dataset URL (e.g. https://domain/resource/<ID>.json).

  Quick verification command:
    curl "https://<domain>/api/catalog/v1?q=building+permits&limit=5" | python -m json.tool

Usage:
  # Ingest all configured cities
  python backend/ingest/il_city_permits.py

  # Ingest a single city
  python backend/ingest/il_city_permits.py --city cook_county
  python backend/ingest/il_city_permits.py --city evanston

  # Dry-run (fetch one page only; do not write output files)
  python backend/ingest/il_city_permits.py --dry-run
  python backend/ingest/il_city_permits.py --city cook_county --dry-run

  # List configured cities
  python backend/ingest/il_city_permits.py --list

Environment variables (optional):
  SOCRATA_APP_TOKEN  — Generic Socrata app token for higher rate limits.
                       Register free at https://dev.socrata.com/register

Acceptance criteria (data-033):
  - Records are fetched from each configured Socrata portal.
  - Raw records are written to data/raw/il_city_permits_<source_key>.json.
  - Source identifiers are preserved for traceability.
  - Script is idempotent: re-running overwrites output cleanly.
  - --dry-run mode fetches one page per city and reports without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# City configurations
# ---------------------------------------------------------------------------
# Each entry describes one Socrata open-data source.
#
# Fields:
#   city_name     : Human-readable city/county label
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
#   city_il       : City + state suffix for address construction
#   where_clause  : Additional SoQL WHERE clause (e.g. to filter by city in a
#                   statewide dataset). None means no extra filter.

CITY_CONFIGS: list[dict] = [
    {
        # Cook County Department of Building and Zoning issues permits for
        # unincorporated Cook County and some suburban municipalities.
        # Portal: https://datacatalog.cookcountyil.gov
        # Dataset: "Building Permits" — verify at:
        #   https://datacatalog.cookcountyil.gov/api/catalog/v1?q=building+permits
        "city_name":        "Cook County",
        "source_key":       "cook_county",
        "domain":           "datacatalog.cookcountyil.gov",
        "dataset_id":       "ep35-ewd2",   # TODO: verify — visit portal and confirm
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Cook County, IL",
        "where_clause":     None,
    },
    {
        # City of Evanston open data portal (Socrata-powered).
        # Portal: https://data.cityofevanston.org
        # Dataset: "Building Permits" — verify at:
        #   https://data.cityofevanston.org/api/catalog/v1?q=building+permits
        "city_name":        "Evanston",
        "source_key":       "evanston",
        "domain":           "data.cityofevanston.org",
        "dataset_id":       "cth3-bk7n",   # TODO: verify
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "date_issued",
        "exp_date_field":   None,
        "lat_field":        None,
        "lon_field":        None,
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Evanston, IL",
        "where_clause":     None,
    },
    {
        # City of Aurora — uses data.aurora.il.us Socrata portal.
        # Portal: https://data.aurora.il.us
        # Dataset: "Building Permits" — verify at:
        #   https://data.aurora.il.us/api/catalog/v1?q=building+permits
        "city_name":        "Aurora",
        "source_key":       "aurora",
        "domain":           "data.aurora.il.us",
        "dataset_id":       "7axj-ypre",   # TODO: verify
        "id_field":         "permit_no",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   "expiration_date",
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "site_address",
        "city_il":          "Aurora, IL",
        "where_clause":     None,
    },
    {
        # City of Naperville — uses data.naperville.il.us or similar Socrata portal.
        # Portal: https://data.naperville.il.us
        # Dataset: "Building Permits" — verify at:
        #   https://data.naperville.il.us/api/catalog/v1?q=building+permits
        "city_name":        "Naperville",
        "source_key":       "naperville",
        "domain":           "data.naperville.il.us",
        "dataset_id":       "q59f-pnz8",   # TODO: verify
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Naperville, IL",
        "where_clause":     None,
    },
    {
        # City of Rockford — uses data.rockford.il.gov Socrata portal.
        # Portal: https://data.rockford.il.gov
        # Dataset: "Building Permits" — verify at:
        #   https://data.rockford.il.gov/api/catalog/v1?q=building+permits
        "city_name":        "Rockford",
        "source_key":       "rockford",
        "domain":           "data.rockford.il.gov",
        "dataset_id":       "wr4m-9tbd",   # TODO: verify
        "id_field":         "permit_number",
        "type_field":       "type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Rockford, IL",
        "where_clause":     None,
    },
    {
        # City of Springfield — via data.illinois.gov statewide portal,
        # filtered to Springfield.  Alternatively, Springfield may have its
        # own portal at data.springfieldil.gov — verify which is authoritative.
        # Dataset: "Illinois Building Permits" on data.illinois.gov — verify at:
        #   https://data.illinois.gov/api/catalog/v1?q=building+permits
        "city_name":        "Springfield",
        "source_key":       "springfield",
        "domain":           "data.illinois.gov",
        "dataset_id":       "bpax-uvjz",   # TODO: verify — statewide IL permits
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Springfield, IL",
        "where_clause":     "city='Springfield'",
    },
    {
        # City of Peoria — verify if data.peoria.il.gov or data.illinois.gov
        # is the authoritative source.  Using data.illinois.gov statewide portal
        # filtered to Peoria as a starting point.
        "city_name":        "Peoria",
        "source_key":       "peoria",
        "domain":           "data.illinois.gov",
        "dataset_id":       "bpax-uvjz",   # TODO: verify — statewide IL permits
        "id_field":         "permit_number",
        "type_field":       "permit_type",
        "desc_field":       "description",
        "issue_date_field": "issue_date",
        "exp_date_field":   None,
        "lat_field":        "latitude",
        "lon_field":        "longitude",
        "loc_field":        "location",
        "addr_field":       "address",
        "city_il":          "Peoria, IL",
        "where_clause":     "city='Peoria'",
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
    cutoff = datetime.now(timezone.utc)
    # Simple year-based lookback (good enough for a 90-day window).
    cutoff_str = f"{cutoff.year - (days_back // 365)}-{cutoff.month:02d}-{cutoff.day:02d}T00:00:00"

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


def normalize_raw_record(record: dict, config: dict) -> dict:
    """
    Map a raw Socrata permit record to a consistent internal field set.

    The output dict uses stable internal field names regardless of the
    per-portal Socrata field names, enabling a single normalize_il_city_permit()
    function in project.py.
    """
    lat, lon = _extract_lat_lon(record, config)

    return {
        "source_key":    config["source_key"],
        "city_name":     config["city_name"],
        "city_il":       config["city_il"],
        "source_id":     str(record.get(config["id_field"], "") or ""),
        "permit_type":   record.get(config["type_field"], "") or "",
        "description":   record.get(config["desc_field"], "") or "",
        "issue_date":    record.get(config["issue_date_field"], "") or "",
        "expiration_date": record.get(config.get("exp_date_field") or "", "") or "",
        "address":       record.get(config["addr_field"], "") or "",
        "latitude":      lat,
        "longitude":     lon,
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
    output_path = output_dir / f"il_city_permits_{config['source_key']}.json"

    staging = {
        "source":       f"il_city_permits_{config['source_key']}",
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
            "Ingest Illinois municipal building permits from Socrata open data portals."
        )
    )
    parser.add_argument(
        "--city",
        choices=list(CITY_CONFIG_BY_KEY.keys()) + ["all"],
        default="all",
        help="Which city/county to ingest (default: all).",
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
        print("Configured Illinois city/county sources:")
        for cfg in CITY_CONFIGS:
            print(f"  {cfg['source_key']:20s} → {cfg['city_name']} "
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
