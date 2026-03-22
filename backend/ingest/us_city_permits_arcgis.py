"""
backend/ingest/us_city_permits_arcgis.py
task: data-046
lane: data

ArcGIS REST FeatureServer ingest for building permits in cities that publish
open data via ArcGIS Hub or ArcGIS Server (not Socrata or CKAN).

Supported cities:
  - Phoenix     (maps.phoenix.gov — ArcGIS MapServer)
  - Columbus    (opendata.columbus.gov — ArcGIS Hub)
  - Minneapolis (opendata.minneapolismn.gov — ArcGIS Hub)
  - Charlotte   (meckgis.mecklenburgcountync.gov — ArcGIS FeatureServer)

ArcGIS REST FeatureServer query pattern:
  GET {service_url}/query
      ?where=<SQL_WHERE>&outFields=*&f=json
      &resultOffset=<N>&resultRecordCount=<page_size>

  Response format (f=json):
    {
      "features": [
        {
          "attributes": { "permit_number": "...", "issue_date": ... },
          "geometry": { "x": <lon>, "y": <lat> }
        }
      ],
      "exceededTransferLimit": true|false
    }

  Geometry uses the service's spatial reference; most ArcGIS Hub services
  support outSR=4326 to request WGS-84 (lat/lon) directly.

NOTE ON SERVICE URLS:
  Service URLs below are researched estimates as of 2026-03-22.
  ArcGIS Hub service URLs can be verified by:
  1. Visit the city's open data portal (listed in CITY_CONFIGS).
  2. Search "building permits" and open the dataset page.
  3. Click "API" or "View API" to get the FeatureServer URL.
  4. Or run: python backend/ingest/us_city_permits_arcgis.py --city <city> --discover
     (queries ArcGIS Hub REST API for datasets matching "building permits")

  If a service_url returns HTTP 400 or 404:
  1. Visit the city's open data portal
  2. Search for "building permits" or "construction permits"
  3. Open the dataset and click "I want to use this" → "API Explorer"
  4. Copy the FeatureServer endpoint and update service_url below.

  If the service returns 0 records but no error, verify:
  - The where clause date field name matches the service's actual field name.
  - Run --dry-run to see the raw response and field names.

Usage:
  # Ingest all configured cities
  python backend/ingest/us_city_permits_arcgis.py

  # Ingest a single city
  python backend/ingest/us_city_permits_arcgis.py --city phoenix
  python backend/ingest/us_city_permits_arcgis.py --city columbus

  # Dry-run (fetch one page only; do not write output files)
  python backend/ingest/us_city_permits_arcgis.py --dry-run
  python backend/ingest/us_city_permits_arcgis.py --city phoenix --dry-run

  # Discover ArcGIS Hub datasets for a city (queries ArcGIS Hub REST API)
  python backend/ingest/us_city_permits_arcgis.py --city phoenix --discover

  # List configured cities
  python backend/ingest/us_city_permits_arcgis.py --list

Acceptance criteria (data-046):
  - Records are fetched from each ArcGIS FeatureServer.
  - Raw records are written to data/raw/us_city_permits_<source_key>.json.
  - Output schema matches Socrata/CKAN scripts for downstream compatibility.
  - Individual city failures are non-fatal; other cities continue.
  - --dry-run mode fetches one page per city and reports without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# City configurations
# ---------------------------------------------------------------------------
# Each entry describes one ArcGIS FeatureServer source.
#
# Fields:
#   city_name       : Human-readable city label
#   source_key      : Snake-case identifier used in output filename
#   service_url     : ArcGIS FeatureServer layer URL (ending in /FeatureServer/0)
#   portal_url      : Open data portal homepage (for humans verifying endpoints)
#   id_field        : Field name for unique permit ID in the attributes dict
#   type_field      : Field name for permit type / work class
#   desc_field      : Field name for work description
#   issue_date_field: Field name for permit issue date (used for date filter)
#   exp_date_field  : Field name for expiration date (None if unavailable)
#   addr_field      : Field name for address string
#   city_state      : City + state for context
#   date_filter_sql : SQL WHERE snippet for date filtering (None = use default)
#                     Set to None to use the default epoch-ms filter on issue_date_field.
#   skip_date_filter: If True, no date WHERE clause is applied (use max_records cap).
#   max_records     : Cap on records fetched (used when skip_date_filter=True).

CITY_CONFIGS: list[dict] = [
    {
        # Phoenix, AZ — Planning Permits.
        # Server: maps.phoenix.gov (MapServer — supports same query API as FeatureServer)
        # Verified 2026-03-22 via direct query.
        # Note: phoenixopendata.com redirects to ArcGIS Hub but the actual
        # permit layer is on maps.phoenix.gov, NOT gismaps.phoenix.gov.
        "city_name":        "Phoenix",
        "source_key":       "phoenix",
        "service_url":      (
            "https://maps.phoenix.gov/pub/rest/services"
            "/Public/Planning_Permit/MapServer/1"
        ),
        "portal_url":       "https://www.phoenixopendata.com",
        "id_field":         "PER_NUM",
        "type_field":       "PER_TYPE_DESC",
        "desc_field":       "SCOPE_DESC",
        "issue_date_field": "PER_ISSUE_DATE",
        "exp_date_field":   "PER_EXPIRE_DATE",
        "addr_field":       "STREET_FULL_NAME",
        "city_state":       "Phoenix, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Columbus, OH — Building Permits.
        # Portal: https://opendata.columbus.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Columbus",
        "source_key":       "columbus",
        "service_url":      (
            "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.columbus.gov",
        "id_field":         "B1_ALT_ID",
        "type_field":       "B1_PER_TYPE",
        "desc_field":       "B1_PER_SUB_TYPE",
        "issue_date_field": "ISSUED_DT",
        "exp_date_field":   None,
        "addr_field":       "SITE_ADDRESS",
        "city_state":       "Columbus, OH",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Minneapolis, MN — CCS Permits.
        # Portal: https://opendata.minneapolismn.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Minneapolis",
        "source_key":       "minneapolis",
        "service_url":      (
            "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services"
            "/CCS_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.minneapolismn.gov",
        "id_field":         "permitNumber",
        "type_field":       "permitType",
        "desc_field":       "comments",
        "issue_date_field": "issueDate",
        "exp_date_field":   None,
        "addr_field":       "Display",
        "city_state":       "Minneapolis, MN",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Charlotte, NC (Mecklenburg County) — Building Permits.
        # Server: meckgis.mecklenburgcountync.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Charlotte",
        "source_key":       "charlotte",
        "service_url":      (
            "https://meckgis.mecklenburgcountync.gov/server/rest/services"
            "/BuildingPermits/FeatureServer/0"
        ),
        "portal_url":       "https://data.charlottenc.gov",
        "id_field":         "permitnum",
        "type_field":       "permittype",
        "desc_field":       "workdesc",
        "issue_date_field": "issuedate",
        "exp_date_field":   None,
        "addr_field":       "projadd",
        "city_state":       "Charlotte, NC",
        "skip_date_filter": False,
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # REMOVED — Jacksonville (verified 2026-03-22):
    #   maps.coj.net and gis.coj.net both return 404. No building permit
    #   FeatureServer found on ArcGIS Online either.
    # -----------------------------------------------------------------
]

# Index by source_key for fast lookup.
CITY_CONFIG_BY_KEY: dict[str, dict] = {c["source_key"]: c for c in CITY_CONFIGS}

# Records per page (ArcGIS default max varies by server; 1000 is safe).
PAGE_SIZE = 1000

# How many days back to filter permits.
DAYS_BACK = 90

# Base output directory for staging files.
DEFAULT_OUTPUT_DIR = Path("data/raw")


# ---------------------------------------------------------------------------
# ArcGIS REST API helpers
# ---------------------------------------------------------------------------

def _build_date_where(config: dict, cutoff_epoch_ms: int) -> str | None:
    """
    Build a SQL WHERE clause for date filtering.

    Uses TIMESTAMP literal format which is widely supported across ArcGIS
    Server and ArcGIS Online hosted FeatureServer/MapServer endpoints.
    Raw epoch ms comparison (field >= 123456789) is NOT supported by most
    servers despite being accepted in some documentation.
    """
    if config.get("skip_date_filter"):
        return None
    date_field = config["issue_date_field"]
    # Convert epoch ms to TIMESTAMP literal
    cutoff_dt = datetime.fromtimestamp(cutoff_epoch_ms / 1000, tz=timezone.utc)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"{date_field} >= TIMESTAMP '{cutoff_str}'"


def fetch_page(
    session: requests.Session,
    config: dict,
    offset: int,
    limit: int,
    where_clause: str,
) -> tuple[list[dict], bool]:
    """
    Fetch one page of ArcGIS FeatureServer records.

    Returns (records, exceeded_transfer_limit).
    Each record is the raw attributes dict from the ArcGIS JSON response,
    augmented with _geometry_x and _geometry_y from the feature geometry.
    """
    url = f"{config['service_url']}/query"
    params: dict[str, Any] = {
        "where":             where_clause,
        "outFields":         "*",
        "returnGeometry":    "true",
        "outSR":             "4326",   # request WGS-84 lat/lon
        "resultOffset":      offset,
        "resultRecordCount": limit,
        "f":                 "json",
    }

    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    # ArcGIS returns {"error": {...}} on query failure.
    if "error" in data:
        err = data["error"]
        raise RuntimeError(
            f"ArcGIS error {err.get('code', '?')}: {err.get('message', data)}"
        )

    features = data.get("features", [])
    exceeded = data.get("exceededTransferLimit", False)

    records = []
    for feat in features:
        attrs = dict(feat.get("attributes") or {})
        geom = feat.get("geometry") or {}

        # Inject geometry as private fields for lat/lon extraction.
        attrs["_geometry_x"] = geom.get("x")
        attrs["_geometry_y"] = geom.get("y")

        records.append(attrs)

    return records, exceeded


def fetch_city_permits(
    config: dict,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through an ArcGIS FeatureServer and return all permit records
    within the lookback window.

    Pagination strategy:
      - Use resultOffset / resultRecordCount for page-based pagination.
      - Stop when a page returns fewer records than the page size OR
        when exceededTransferLimit is False.

    Date filter strategy:
      - Try epoch-ms date filter first.
      - If the response has 0 records and no error, retry without a date filter
        (may indicate the date field name is wrong).
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_epoch_ms = int(cutoff.timestamp() * 1000)

    where_clause = _build_date_where(config, cutoff_epoch_ms) or "1=1"

    all_records: list[dict] = []
    offset = 0

    print(
        f"\nFetching {config['city_name']} permits "
        f"(url={config['service_url']})..."
    )
    print(f"  WHERE: {where_clause}")

    tried_date_filter = (where_clause != "1=1")

    try:
        while True:
            print(f"  Fetching at offset {offset}...", end=" ", flush=True)
            records, exceeded = fetch_page(
                session, config, offset, PAGE_SIZE, where_clause
            )
            print(f"{len(records)} records (exceededTransferLimit={exceeded}).")

            if not records:
                # If we got 0 records with a date filter, try without.
                if tried_date_filter and offset == 0:
                    print(
                        "  WARN: 0 records with date filter — retrying without "
                        "date filter to verify connectivity.",
                        file=sys.stderr,
                    )
                    print(
                        f"  NOTE: Verify '{config['issue_date_field']}' is the "
                        f"correct date field name for {config['city_name']}.",
                        file=sys.stderr,
                    )
                    where_clause = "1=1"
                    tried_date_filter = False

                    records, exceeded = fetch_page(
                        session, config, 0, PAGE_SIZE, where_clause
                    )
                    print(
                        f"  Retry without date filter: {len(records)} records "
                        f"(exceededTransferLimit={exceeded})."
                    )
                    if records:
                        all_records.extend(records)
                        offset = PAGE_SIZE
                        if dry_run or not exceeded:
                            break
                        continue

                break  # genuinely 0 records

            all_records.extend(records)
            offset += len(records)

            if dry_run:
                print("  Dry-run: stopping after first page.")
                break

            if not exceeded and len(records) < PAGE_SIZE:
                break  # last page

            # Some servers don't set exceededTransferLimit. Keep paginating.

            max_records = config.get("max_records")
            if max_records and len(all_records) >= max_records:
                print(f"  Reached max_records cap ({max_records}). Stopping.")
                break

    except requests.exceptions.Timeout:
        print(
            f"\n  ERROR [{config['city_name']}]: Request timed out.",
            file=sys.stderr,
        )
        print(
            f"  Verify service_url: {config['service_url']}\n"
            f"  Or run: python backend/ingest/us_city_permits_arcgis.py "
            f"--city {config['source_key']} --discover",
            file=sys.stderr,
        )
        return []
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(
            f"\n  ERROR [{config['city_name']}]: HTTP {status}. Skipping.",
            file=sys.stderr,
        )
        print(
            f"  Verify service_url: {config['service_url']}\n"
            f"  Portal: {config['portal_url']}\n"
            f"  Or run: python backend/ingest/us_city_permits_arcgis.py "
            f"--city {config['source_key']} --discover",
            file=sys.stderr,
        )
        return []
    except RuntimeError as exc:
        print(
            f"\n  ERROR [{config['city_name']}]: {exc}. Skipping.",
            file=sys.stderr,
        )
        return []

    return all_records


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_lat_lon(
    record: dict,
    config: dict,
) -> tuple[str | None, str | None]:
    """
    Extract lat/lon from an ArcGIS record.

    Checks _geometry_y/_geometry_x (injected from feature.geometry) first,
    then falls back to explicit lat/lon attribute fields if configured.
    """
    lat: str | None = None
    lon: str | None = None

    # Primary: geometry fields injected by fetch_page()
    raw_y = record.get("_geometry_y")
    raw_x = record.get("_geometry_x")

    if raw_y is not None:
        try:
            lat = str(float(raw_y))
        except (TypeError, ValueError):
            pass

    if raw_x is not None:
        try:
            lon = str(float(raw_x))
        except (TypeError, ValueError):
            pass

    return lat, lon


def _extract_source_id(record: dict, config: dict) -> str:
    """
    Extract a stable source ID from a raw ArcGIS record.

    Falls back to SHA-1 hash of key fields when the configured id_field
    is absent.
    """
    id_field = config["id_field"]
    raw_id = str(record.get(id_field) or "").strip()
    if raw_id and raw_id.lower() not in ("none", "null"):
        return raw_id

    parts = [
        str(record.get(config["issue_date_field"], "") or ""),
        str(record.get(config["addr_field"], "") or ""),
        str(record.get(config.get("desc_field", ""), "") or ""),
    ]
    key = "|".join(parts)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _ms_epoch_to_iso(value: Any) -> str:
    """
    Convert an ArcGIS epoch-millisecond timestamp to an ISO 8601 string.
    Returns the original string representation if conversion fails.
    """
    if value is None:
        return ""
    try:
        ms = int(value)
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(value)


def normalize_raw_record(record: dict, config: dict) -> dict:
    """
    Map a raw ArcGIS permit attributes dict to the standard internal field set.

    Output schema matches Socrata and CKAN scripts so downstream loaders
    can treat all permit sources identically.
    """
    lat, lon = _extract_lat_lon(record, config)

    # ArcGIS timestamps are epoch-ms integers; convert to ISO dates.
    raw_issue = record.get(config["issue_date_field"])
    issue_date = _ms_epoch_to_iso(raw_issue) if isinstance(raw_issue, (int, float)) else str(raw_issue or "")

    raw_exp = record.get(config.get("exp_date_field") or "") if config.get("exp_date_field") else None
    exp_date = _ms_epoch_to_iso(raw_exp) if isinstance(raw_exp, (int, float)) else str(raw_exp or "")

    return {
        "source_key":      config["source_key"],
        "city_name":       config["city_name"],
        "city_state":      config["city_state"],
        "source_id":       _extract_source_id(record, config),
        "permit_type":     str(record.get(config["type_field"], "") or ""),
        "description":     str(record.get(config["desc_field"], "") or ""),
        "issue_date":      issue_date,
        "expiration_date": exp_date,
        "address":         str(record.get(config["addr_field"], "") or ""),
        "latitude":        lat,
        "longitude":       lon,
    }


# ---------------------------------------------------------------------------
# Discovery mode
# ---------------------------------------------------------------------------

def discover_service(config: dict) -> None:
    """
    Query the ArcGIS Hub REST API to find building permit datasets for a city.

    Prints dataset titles, IDs, and FeatureServer URLs to help the user
    identify and verify the correct service_url to configure above.
    """
    city_name = config["city_name"]
    print(f"\nDiscovering ArcGIS Hub datasets for {city_name}...")

    # ArcGIS Hub REST API: search for datasets by keyword + bounding box.
    # Docs: https://hub.arcgis.com/api/v3/
    hub_url = "https://hub.arcgis.com/api/v3/datasets"
    params = {
        "q":           f"building permits {city_name}",
        "fields[datasets]": "title,url,access,layer,extent,searchDescription",
        "page[size]":  10,
    }

    try:
        resp = requests.get(hub_url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  ERROR querying ArcGIS Hub: {exc}", file=sys.stderr)
        print(
            f"\n  Manual search:\n"
            f"  1. Visit {config['portal_url']}\n"
            f"  2. Search 'building permits'\n"
            f"  3. Open the dataset and click 'API' to get the FeatureServer URL\n"
            f"  4. Update service_url in CITY_CONFIGS for {config['source_key']}"
        )
        return

    datasets = data.get("data", [])
    if not datasets:
        print(f"  No datasets found for '{city_name}' on ArcGIS Hub.")
        print(
            f"\n  Try manually:\n"
            f"  1. Visit {config['portal_url']}\n"
            f"  2. Search 'building permits'\n"
            f"  3. Open the dataset and copy the FeatureServer/0 URL."
        )
        return

    print(f"  Found {len(datasets)} dataset(s):\n")
    for ds in datasets:
        attrs = ds.get("attributes", {})
        title = attrs.get("title", "?")
        url = attrs.get("url", "")
        print(f"  Title: {title}")
        print(f"  URL:   {url}")
        if url and "FeatureServer" in url:
            service_layer = url.rstrip("/") + "/0" if not url.endswith("/0") else url
            print(f"  → Set service_url = '{service_layer}/query' base: '{url}/0'")
        print()

    print(
        f"  Hint: update service_url in CITY_CONFIGS['{config['source_key']}'] "
        f"to the FeatureServer/0 URL above."
    )

    # Also print a direct sample query to test the current service_url.
    print(
        f"\n  Test current service_url with:\n"
        f"  curl '{config['service_url']}/query"
        f"?where=1%3D1&outFields=*&resultRecordCount=1&f=json'"
    )


# ---------------------------------------------------------------------------
# Staging file writer
# ---------------------------------------------------------------------------

def write_staging_file(
    records: list[dict],
    config: dict,
    output_dir: Path,
) -> Path:
    """Write normalized permit records to a JSON staging file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"us_city_permits_{config['source_key']}.json"

    staging = {
        "source":       f"us_city_permits_{config['source_key']}",
        "city_name":    config["city_name"],
        "source_url":   config["service_url"],
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
    days_back: int,
    dry_run: bool,
    output_dir: Path,
    discover: bool,
) -> int:
    """
    Fetch and stage permits for one city.

    Returns the number of records written (0 on failure or dry-run).
    """
    if discover:
        discover_service(config)
        return 0

    raw_records = fetch_city_permits(config, days_back, dry_run)

    if not raw_records:
        print(f"  No records returned for {config['city_name']}.")
        return 0

    # Strip internal geometry fields before normalization.
    normalized = [normalize_raw_record(r, config) for r in raw_records]
    print(f"  Normalized {len(normalized)} records.")

    if dry_run:
        print("  Dry-run: skipping file write.")
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
            "Ingest US city building permits from ArcGIS REST FeatureServer.\n\n"
            "Cities: Phoenix, Columbus, Minneapolis, Charlotte, Jacksonville.\n\n"
            "NOTE: Service URLs require verification before production use.\n"
            "Run --discover or visit each city's open data portal to confirm."
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
        help=f"Number of days back to filter permits (default: {DAYS_BACK}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page per city only; do not write output files.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help=(
            "Query ArcGIS Hub REST API to find building permit datasets — "
            "useful for verifying or finding the correct service_url."
        ),
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
        print("Configured ArcGIS city sources:")
        for cfg in CITY_CONFIGS:
            print(
                f"  {cfg['source_key']:20s} → {cfg['city_name']} "
                f"({cfg['service_url'][:60]}...)"
            )
        return

    configs = (
        CITY_CONFIGS
        if args.city == "all"
        else [CITY_CONFIG_BY_KEY[args.city]]
    )

    total = 0
    failed: list[str] = []

    for config in configs:
        try:
            count = ingest_city(
                config,
                args.days_back,
                args.dry_run,
                args.output_dir,
                args.discover,
            )
            total += count
        except Exception as exc:
            print(f"  ERROR [{config['city_name']}]: {exc}", file=sys.stderr)
            failed.append(config["city_name"])

    if not args.discover:
        print(f"\n── Summary ──────────────────────────────────────")
        print(f"  Cities attempted: {len(configs)}")
        print(
            f"  Cities failed:    {len(failed)}"
            + (f" ({', '.join(failed)})" if failed else "")
        )
        print(f"  Total records:    {total}")

        if args.dry_run:
            print("  Dry-run mode: no files written.")

        if failed and len(failed) == len(configs):
            sys.exit(1)


if __name__ == "__main__":
    main()
