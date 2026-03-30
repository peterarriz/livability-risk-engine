"""
backend/ingest/us_city_permits_ckan.py
task: data-039, data-043, data-045
lane: data

CKAN-based building permit ingest for US cities that do NOT use Socrata.

Supported cities (verified to use CKAN open data portals):
  - Houston       (data.houstontx.gov)
  - Philadelphia  (data.phila.gov)
  - San Antonio   (data.sanantonio.gov)
  - San Diego     (data.sandiego.gov)
  - Boston        (data.boston.gov)     [resource_id verified 2026-03-22]
  - Milwaukee     (data.milwaukee.gov)  [resource_id verified 2026-03-22]

NOT YET IMPLEMENTED — ArcGIS Hub / custom portals (data-045):
  - Minneapolis  (opendata.minneapolismn.gov) — ArcGIS Hub
  - Charlotte    (data.charlottenc.gov)       — ArcGIS/custom
  - Jacksonville (coj.net)                    — ArcGIS/custom
  These require an ArcGIS REST ingest approach; see notes in TASKS.yaml data-046.

CKAN API pattern:
  Paginated fetch:
    GET https://<domain>/api/3/action/datastore_search
        ?resource_id=<UUID>&limit=<N>&offset=<N>
  Date-filtered fetch (SQL):
    GET https://<domain>/api/3/action/datastore_search_sql
        ?sql=SELECT * FROM "<resource_id>"
             WHERE "<date_field>" >= '2025-12-21'
             ORDER BY "<date_field>" DESC
             LIMIT 5000 OFFSET 0

NOTE ON RESOURCE IDs:
  Each CKAN resource_id is a UUID for the specific datastore resource within
  a package (dataset). These were researched from public CKAN catalog metadata
  as of early 2026. If a fetch returns 0 records or HTTP 404/403, verify with:

    # List packages matching "building permit":
    curl "https://<domain>/api/3/action/package_search?q=building+permit&rows=5"

    # Show resources within a specific package:
    curl "https://<domain>/api/3/action/package_show?id=<package_name>"

    # Sample first record of a resource to inspect field names:
    curl "https://<domain>/api/3/action/datastore_search?resource_id=<UUID>&limit=1"

  Or run this script's --discover flag to call package_search automatically:
    python backend/ingest/us_city_permits_ckan.py --city houston --discover

  NOTE: Some CKAN portals disable the datastore_search_sql endpoint
  (returns 403). When that happens, date filtering falls back to fetching
  the most recent N records via plain datastore_search and filtering client-side.

Usage:
  # Ingest all configured cities
  python backend/ingest/us_city_permits_ckan.py

  # Ingest a single city
  python backend/ingest/us_city_permits_ckan.py --city houston
  python backend/ingest/us_city_permits_ckan.py --city philadelphia

  # Dry-run (fetch one page only; do not write output files)
  python backend/ingest/us_city_permits_ckan.py --dry-run
  python backend/ingest/us_city_permits_ckan.py --city san_diego --dry-run

  # Discover resource IDs for a city (calls package_search)
  python backend/ingest/us_city_permits_ckan.py --city houston --discover

  # List configured cities
  python backend/ingest/us_city_permits_ckan.py --list

Acceptance criteria (data-039):
  - Records are fetched from each CKAN portal.
  - Raw records are written to data/raw/us_city_permits_<source_key>.json.
  - Source identifiers are preserved for traceability.
  - Script is idempotent: re-running overwrites output cleanly.
  - Individual city failures are non-fatal; other cities continue.
  - --dry-run mode fetches one page per city and reports without writing.
  - --discover mode prints available building-permit packages from CKAN catalog.
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
# Each entry describes one CKAN open-data source.
#
# Fields:
#   city_name       : Human-readable city label
#   source_key      : Snake-case identifier used in output filename
#   domain          : CKAN portal domain (no https://)
#   resource_id     : CKAN datastore resource UUID (verify via --discover)
#   id_field        : Field name for unique record ID
#   type_field      : Field name for permit type / category
#   desc_field      : Field name for work description / notes
#   issue_date_field: Field name for permit issue date (used for lookback filter)
#   exp_date_field  : Field name for expiration date (None if unavailable)
#   lat_field       : Field name for latitude  (None if not available directly)
#   lon_field       : Field name for longitude (None if not available directly)
#   addr_field      : Field name for full address string
#   city_state      : City + state for address construction
#   discover_query  : Query string for package_search when using --discover

CITY_CONFIGS: list[dict] = [
    # -----------------------------------------------------------------
    # REMOVED — Houston (verified 2026-03-27):
    #   data.houstontx.gov CKAN has only monthly aggregate counts
    #   (residential-building-permits, resource c9cef716): Year, Month,
    #   Single Family, Multi-Family totals. No individual permit records.
    #   Original resource_id a67a8bcd was fabricated (404).
    # REMOVED — Philadelphia (verified 2026-03-27):
    #   data.phila.gov CKAN API returns 403. Philadelphia permits are
    #   available on ArcGIS: services.arcgis.com/fLeGjb7u4uXqeF9q
    #   ActivePermitOverview/FeatureServer/1 (ACTIVE_BUILDING, 15,294 records).
    #   Moved to us_city_permits_arcgis.py.
    # -----------------------------------------------------------------
    {
        # San Antonio — Building Permits (verified 2026-03-27).
        # Portal: https://data.sanantonio.gov
        # Package: building-permits, resource: PERMITS ISSUED (101,274 records).
        # where_extra excludes permit types that are ungeocodeable:
        #   - Plumbing Irrigation Permit (8,260 — new subdivision streets not in geocoder)
        #   - Tree Affidavit Permit (2,221 — often no address or informal lot refs)
        #   - Tree Permit (493 — same issue)
        #   - On Premise Sign (2,409 — sign permits, low scoring value)
        "city_name":        "San Antonio",
        "source_key":       "san_antonio",
        "domain":           "data.sanantonio.gov",
        "resource_id":      "c21106f9-3ef5-4f3a-8604-f992b4db7512",
        "id_field":         "PERMIT #",
        "type_field":       "PERMIT TYPE",
        "desc_field":       "WORK TYPE",
        "issue_date_field": "DATE ISSUED",
        "exp_date_field":   None,
        "lat_field":        "Y_COORD",
        "lon_field":        "X_COORD",
        "addr_field":       "ADDRESS",
        "city_state":       "San Antonio, TX",
        "discover_query":   "building permit",
        "where_extra":      "\"PERMIT TYPE\" NOT IN ('Plumbing Irrigation Permit','Tree Affidavit Permit','Tree Permit','On Premise Sign')",
    },
    # -----------------------------------------------------------------
    # REMOVED — San Diego (verified 2026-03-27):
    #   data.sandiego.gov is NOT CKAN — it's a custom static HTML portal.
    #   CKAN datastore_search returns no JSON. Not on Socrata either.
    #   Original resource_id 7e82b527 was fabricated (no response).
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — Denver (verified 2026-03-22):
    #   data.denvergov.org is NOT CKAN — it redirects (301) to ArcGIS Hub
    #   (opendata-geospatialdenver.hub.arcgis.com). Denver publishes permits
    #   via ArcGIS FeatureServer:
    #     ODC_DEV_RESIDENTIALCONSTPERMIT_P (residential)
    #     ODC_DEV_COMMERCIALCONSTPERMIT_P  (commercial)
    #   A future task can add an ArcGIS REST ingest for Denver permits.
    # -----------------------------------------------------------------
    {
        # Boston — Approved Building Permits.
        # Portal: https://data.boston.gov (CKAN)
        # Package: "approved-building-permits"
        # Resource verified 2026-03-22 via datastore_search.
        # Note: use y_latitude / x_longitude (NOT gpsx/gpsy which are state plane coords).
        "city_name":        "Boston",
        "source_key":       "boston",
        "domain":           "data.boston.gov",
        "resource_id":      "6ddcd912-32a0-43df-9908-63574f8c7e77",
        "id_field":         "permitnumber",
        "type_field":       "permittypedescr",
        "desc_field":       "description",
        "issue_date_field": "issued_date",
        "exp_date_field":   None,
        "lat_field":        "y_latitude",
        "lon_field":        "x_longitude",
        "addr_field":       "address",
        "city_state":       "Boston, MA",
        "discover_query":   "building permits",
    },
    {
        # Milwaukee — Residential and Commercial Permit Work Data.
        # Portal: https://data.milwaukee.gov (CKAN)
        # Package: "buildingpermits"
        # Resource verified 2026-03-22 via datastore_search.
        # Note: no lat/lon columns — address must be geocoded downstream.
        # No free-text description; "Use of Building" is closest metadata.
        "city_name":        "Milwaukee",
        "source_key":       "milwaukee",
        "domain":           "data.milwaukee.gov",
        "resource_id":      "828e9630-d7cb-42e4-960e-964eae916397",
        "id_field":         "Record ID",
        "type_field":       "Permit Type",
        "desc_field":       "Use of Building",
        "issue_date_field": "Date Issued",
        "exp_date_field":   None,
        "lat_field":        None,
        "lon_field":        None,
        "addr_field":       "Address",
        "city_state":       "Milwaukee, WI",
        "discover_query":   "building permits",
    },
]

# Index by source_key for fast lookup.
CITY_CONFIG_BY_KEY: dict[str, dict] = {c["source_key"]: c for c in CITY_CONFIGS}

# How many records to fetch per API page (CKAN default max is 32000; use 5000 for safety).
PAGE_SIZE = 5000

# How many days back to filter permits.
DAYS_BACK = 90

# Base output directory for staging files.
DEFAULT_OUTPUT_DIR = Path("data/raw")


# ---------------------------------------------------------------------------
# CKAN API helpers
# ---------------------------------------------------------------------------

def _ckan_url(domain: str, action: str) -> str:
    """Build a CKAN action API URL."""
    return f"https://{domain}/api/3/action/{action}"


def fetch_page_sql(
    session: requests.Session,
    config: dict,
    offset: int,
    limit: int,
    cutoff_str: str,
) -> list[dict]:
    """
    Fetch one page of permits using CKAN datastore_search_sql.

    Uses a SQL WHERE clause for date filtering.  Some portals disable this
    endpoint (returns 403 or 501); callers should catch HTTPError and fall
    back to fetch_page_plain().
    """
    resource_id = config["resource_id"]
    date_field  = config["issue_date_field"]

    where_extra = config.get("where_extra", "")
    extra_clause = f" AND {where_extra}" if where_extra else ""
    sql = (
        f'SELECT * FROM "{resource_id}" '
        f'WHERE "{date_field}" >= \'{cutoff_str}\'{extra_clause} '
        f'ORDER BY "{date_field}" DESC '
        f'LIMIT {limit} OFFSET {offset}'
    )

    url = _ckan_url(config["domain"], "datastore_search_sql")
    response = session.get(url, params={"sql": sql}, timeout=30)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        error = data.get("error", {})
        raise RuntimeError(f"CKAN API error: {error}")

    return data["result"].get("records", [])


def fetch_page_plain(
    session: requests.Session,
    config: dict,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    """
    Fetch one page of permits using plain CKAN datastore_search.

    Returns (records, total_count).  No server-side date filter is applied —
    we rely on client-side filtering in the caller when a date field is known.
    """
    resource_id = config["resource_id"]

    url = _ckan_url(config["domain"], "datastore_search")
    params: dict[str, Any] = {
        "resource_id": resource_id,
        "limit":       limit,
        "offset":      offset,
    }

    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        error = data.get("error", {})
        raise RuntimeError(f"CKAN API error: {error}")

    result = data["result"]
    return result.get("records", []), result.get("total", 0)


def fetch_city_permits(
    config: dict,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Fetch all permits for one city within the lookback window.

    Strategy:
      1. Try datastore_search_sql (supports server-side date filter).
      2. If SQL endpoint is unavailable (403/501), fall back to plain
         datastore_search and apply a client-side date cutoff.

    Returns an empty list (and logs a warning) if the dataset is inaccessible
    so the rest of the pipeline can continue.
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    date_field = config["issue_date_field"]

    all_records: list[dict] = []
    offset = 0
    use_sql = True   # start with SQL approach; flip to False on failure

    print(
        f"\nFetching {config['city_name']} permits "
        f"(domain={config['domain']}, resource_id={config['resource_id']})..."
    )

    try:
        # ── SQL mode ────────────────────────────────────────────────────────
        if use_sql:
            try:
                print("  Attempting datastore_search_sql...", end=" ", flush=True)
                records = fetch_page_sql(session, config, 0, PAGE_SIZE, cutoff_str)
                print(f"{len(records)} records.")
                all_records.extend(records)
                offset = len(records)

                if not dry_run:
                    while len(records) == PAGE_SIZE:
                        print(f"  SQL page at offset {offset}...", end=" ", flush=True)
                        records = fetch_page_sql(
                            session, config, offset, PAGE_SIZE, cutoff_str
                        )
                        print(f"{len(records)} records.")
                        all_records.extend(records)
                        offset += len(records)
                        if len(records) < PAGE_SIZE:
                            break
                else:
                    print("  Dry-run: stopping after first SQL page.")

                return all_records

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                print(
                    f"\n  SQL endpoint returned HTTP {status} — "
                    "falling back to plain datastore_search.",
                    file=sys.stderr,
                )
                use_sql = False
                offset = 0

        # ── Plain mode ───────────────────────────────────────────────────
        while True:
            print(f"  datastore_search at offset {offset}...", end=" ", flush=True)
            records, total = fetch_page_plain(session, config, offset, PAGE_SIZE)
            print(f"{len(records)} records (total={total}).")

            if not records:
                break

            # Apply client-side date filter when we have a date field.
            if date_field:
                records = [
                    r for r in records
                    if _record_after_cutoff(r, date_field, cutoff_str)
                ]

            # Apply client-side type exclusion (mirrors where_extra for plain mode).
            where_extra = config.get("where_extra", "")
            if where_extra and "NOT IN" in where_extra:
                # Parse excluded types from where_extra string
                import re
                excluded = set(re.findall(r"'([^']+)'", where_extra))
                type_field = config.get("type_field")
                if excluded and type_field:
                    records = [r for r in records if r.get(type_field) not in excluded]

            all_records.extend(records)
            offset += PAGE_SIZE  # CKAN offset is always step-by-page-size

            if dry_run:
                print("  Dry-run: stopping after first page.")
                break

            if offset >= total:
                break

    except requests.exceptions.Timeout:
        print(
            f"\n  ERROR [{config['city_name']}]: Request timed out. Skipping.",
            file=sys.stderr,
        )
        return []
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(
            f"\n  ERROR [{config['city_name']}]: HTTP {status}. Skipping. "
            f"Verify resource_id={config['resource_id']} at "
            f"https://{config['domain']}/api/3/action/package_search"
            f"?q={config.get('discover_query', 'building permit').replace(' ', '+')}",
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


def _record_after_cutoff(record: dict, date_field: str, cutoff_str: str) -> bool:
    """
    Return True if the record's date field is on or after the cutoff.

    Handles ISO 8601 timestamps and plain YYYY-MM-DD strings.
    Unknown formats are kept (returns True) so we don't silently discard data.
    """
    raw = record.get(date_field)
    if not raw:
        return True  # keep records with no date rather than silently drop them
    try:
        # Normalize to YYYY-MM-DD prefix for comparison.
        date_prefix = str(raw)[:10]
        return date_prefix >= cutoff_str
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_lat_lon(record: dict, config: dict) -> tuple[str | None, str | None]:
    """Extract latitude and longitude from a raw CKAN permit record."""
    lat_field = config.get("lat_field")
    lon_field = config.get("lon_field")

    lat = str(record[lat_field]).strip() if lat_field and record.get(lat_field) else None
    lon = str(record[lon_field]).strip() if lon_field and record.get(lon_field) else None

    return lat, lon


def _extract_source_id(record: dict, config: dict) -> str:
    """
    Extract a stable source ID from a raw CKAN record.

    Falls back to a hash of key fields when the configured id_field is absent.
    """
    id_field = config["id_field"]
    raw_id = str(record.get(id_field) or "").strip()
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
    Map a raw CKAN permit record to a consistent internal field set.

    Output schema matches the Socrata normalization in us_city_permits.py
    so downstream loaders can treat both identically.
    """
    lat, lon = _extract_lat_lon(record, config)

    exp_date = ""
    if config.get("exp_date_field"):
        exp_date = record.get(config["exp_date_field"], "") or ""

    return {
        "source_key":      config["source_key"],
        "city_name":       config["city_name"],
        "city_state":      config.get("city_state", config["city_name"]),
        "source_id":       _extract_source_id(record, config),
        "permit_type":     record.get(config["type_field"], "") or "",
        "description":     record.get(config["desc_field"], "") or "",
        "issue_date":      record.get(config["issue_date_field"], "") or "",
        "expiration_date": str(exp_date),
        "address":         record.get(config["addr_field"], "") or "",
        "latitude":        lat,
        "longitude":       lon,
    }


# ---------------------------------------------------------------------------
# Discovery mode
# ---------------------------------------------------------------------------

def discover_packages(config: dict) -> None:
    """
    Query the CKAN package_search endpoint and print matching datasets
    with their resource UUIDs.  Helps verify or find the correct resource_id.
    """
    domain = config["domain"]
    query  = config.get("discover_query", "building permit")

    url = _ckan_url(domain, "package_search")
    params = {"q": query, "rows": 10}

    print(f"\nDiscovering packages on {domain} (q={query!r})...")
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return

    packages = data.get("result", {}).get("results", [])
    if not packages:
        print("  No packages found.")
        return

    for pkg in packages:
        print(f"\n  Package: {pkg.get('name')} — {pkg.get('title')}")
        for res in pkg.get("resources", []):
            fmt = res.get("format", "?")
            print(
                f"    resource_id={res['id']}  name={res.get('name', '?')!r}  "
                f"format={fmt}"
            )

    print(
        f"\n  Hint: set resource_id in CITY_CONFIGS to one of the UUIDs above, "
        f"then sample it with:\n"
        f"    curl 'https://{domain}/api/3/action/datastore_search"
        f"?resource_id=<UUID>&limit=1'"
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
        "source_url":   (
            f"https://{config['domain']}/api/3/action/datastore_search"
            f"?resource_id={config['resource_id']}"
        ),
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
        discover_packages(config)
        return 0

    raw_records = fetch_city_permits(config, days_back, dry_run)

    if not raw_records:
        print(f"  No records returned for {config['city_name']}.")
        return 0

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
            "Ingest US city building permits from CKAN open data portals.\n\n"
            "Cities: Houston, Philadelphia, San Antonio, San Diego, Boston, Milwaukee."
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
        "--discover",
        action="store_true",
        help=(
            "Query CKAN package_search and print resource UUIDs — "
            "useful for verifying or finding the correct resource_id."
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
        print("Configured CKAN city sources:")
        for cfg in CITY_CONFIGS:
            print(
                f"  {cfg['source_key']:20s} → {cfg['city_name']} "
                f"({cfg['domain']}, resource_id={cfg['resource_id']})"
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
