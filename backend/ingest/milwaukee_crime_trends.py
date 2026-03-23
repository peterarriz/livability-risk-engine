"""
backend/ingest/milwaukee_crime_trends.py
task: data-045
lane: data

Ingests Milwaukee Police Department crime data and calculates 12-month crime trends
by district.

Source:
  https://data.milwaukee.gov (CKAN portal)
  Dataset: "Wibr" or "Police Incidents" (MPS)
  Resource ID: 87843297-a6fa-46d4-ba5d-cb342fb2d3bb

  Verify resource_id:
    python backend/ingest/milwaukee_crime_trends.py --discover
    # or:
    curl "https://data.milwaukee.gov/api/3/action/package_search?q=crime&rows=5"
  Sample first record to confirm field names:
    curl "https://data.milwaukee.gov/api/3/action/datastore_search?resource_id=<UUID>&limit=1"

Method:
  1. Use CKAN datastore_search_sql to aggregate crime counts by district.
  2. Fall back to plain datastore_search with client-side filtering.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/milwaukee_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/milwaukee_crime_trends.py
  python backend/ingest/milwaukee_crime_trends.py --dry-run
  python backend/ingest/milwaukee_crime_trends.py --discover
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CKAN_DOMAIN = "data.milwaukee.gov"

# Verify this resource_id:
#   python backend/ingest/milwaukee_crime_trends.py --discover
# Common Milwaukee crime datasets: "wibr" (Wibr crime data), "police-incidents"
RESOURCE_ID = "87843297-a6fa-46d4-ba5d-cb342fb2d3bb"

DEFAULT_OUTPUT_PATH = Path("data/raw/milwaukee_crime_trends.json")

# Date field and district field in the MPS crime dataset.
# Verify by sampling: curl "https://data.milwaukee.gov/api/3/action/datastore_search?resource_id=<UUID>&limit=1"
DATE_FIELD = "ReportedDateTime"
DISTRICT_FIELD = "POLICE"

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0

PAGE_SIZE = 5000


# ---------------------------------------------------------------------------
# CKAN helpers
# ---------------------------------------------------------------------------

def _ckan_url(action: str) -> str:
    return f"https://{CKAN_DOMAIN}/api/3/action/{action}"


def fetch_crime_counts_sql(
    start_date: datetime,
    end_date: datetime,
    limit: int = 50000,
) -> dict[str, int]:
    """
    Aggregate crime counts per district via CKAN datastore_search_sql.
    Returns dict: district → count.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    sql = (
        f'SELECT "{DISTRICT_FIELD}", count(*) as crime_count '
        f'FROM "{RESOURCE_ID}" '
        f'WHERE "{DATE_FIELD}" >= \'{start_str}\' '
        f'AND "{DATE_FIELD}" < \'{end_str}\' '
        f'AND "{DISTRICT_FIELD}" IS NOT NULL '
        f'GROUP BY "{DISTRICT_FIELD}" '
        f'LIMIT {limit}'
    )

    url = _ckan_url("datastore_search_sql")
    response = requests.get(url, params={"sql": sql}, timeout=60)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"CKAN SQL error: {data.get('error', {})}")

    counts: dict[str, int] = {}
    for row in data["result"].get("records", []):
        district = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not district:
            continue
        try:
            counts[district] = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            counts[district] = 0
    return counts


def fetch_crime_counts_plain(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    """
    Aggregate crime counts by fetching plain datastore_search pages and
    filtering client-side. Used as fallback when SQL endpoint is unavailable.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    counts: defaultdict[str, int] = defaultdict(int)
    offset = 0

    url = _ckan_url("datastore_search")
    while True:
        params = {
            "resource_id": RESOURCE_ID,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            raise RuntimeError(f"CKAN error: {data.get('error', {})}")

        result = data["result"]
        records = result.get("records", [])
        total = result.get("total", 0)

        if not records:
            break

        for record in records:
            raw_date = str(record.get(DATE_FIELD, "") or "")[:10]
            if raw_date < start_str or raw_date >= end_str:
                continue
            district = str(record.get(DISTRICT_FIELD, "") or "").strip().upper()
            if district:
                counts[district] += 1

        offset += PAGE_SIZE

        if dry_run:
            print("  Dry-run: stopping after first page.")
            break

        if offset >= total:
            break

    return dict(counts)


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    """
    Fetch crime counts per district, trying SQL endpoint first then falling back.
    """
    print(f"  Attempting CKAN SQL aggregation...", end=" ", flush=True)
    try:
        counts = fetch_crime_counts_sql(start_date, end_date)
        print(f"{len(counts)} districts.")
        return counts
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(
            f"\n  SQL endpoint returned HTTP {status} — "
            "falling back to plain datastore_search.",
            file=sys.stderr,
        )

    print("  Fetching via plain datastore_search (slower)...")
    return fetch_crime_counts_plain(start_date, end_date, dry_run)


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def _classify_trend(current: int, prior: int) -> tuple[str, float]:
    if prior == 0:
        if current > 0:
            return "INCREASING", 100.0
        return "STABLE", 0.0

    pct = (current - prior) / prior * 100.0
    if pct >= STABLE_THRESHOLD_PCT:
        return "INCREASING", round(pct, 1)
    if pct <= -STABLE_THRESHOLD_PCT:
        return "DECREASING", round(pct, 1)
    return "STABLE", round(pct, 1)


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_trend_records(
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    """
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "district",
            "region_id": f"milwaukee_district_{district}",
            "district_id": district,
            "district_name": f"Milwaukee District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": None,
            "longitude": None,
        })
    return records


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_resource() -> None:
    """Query CKAN package_search to find the crime resource UUID."""
    url = _ckan_url("package_search")
    params = {"q": "crime incidents", "rows": 10}

    print(f"Discovering crime datasets on {CKAN_DOMAIN}...")
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
            print(
                f"    resource_id={res['id']}  name={res.get('name', '?')!r}  "
                f"format={res.get('format', '?')}"
            )

    print(
        f"\n  Hint: update RESOURCE_ID in this script to the correct UUID, then sample:\n"
        f"    curl 'https://{CKAN_DOMAIN}/api/3/action/datastore_search"
        f"?resource_id=<UUID>&limit=1'"
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "milwaukee_crime_trends",
        "source_url": f"https://{CKAN_DOMAIN}/api/3/action/datastore_search?resource_id={RESOURCE_ID}",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Milwaukee MPS crime trends by district from CKAN."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write output file.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Query CKAN package_search to find crime dataset resource UUIDs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover_resource()
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month crime counts ({current_start.date()} → {now.date()})...")
    try:
        current_data = fetch_crime_counts(current_start, now, args.dry_run)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        print(
            f"  Run --discover to find the correct resource_id:\n"
            f"  python backend/ingest/milwaukee_crime_trends.py --discover",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"  {len(current_data)} districts with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({prior_start.date()} → {prior_end.date()})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end, args.dry_run)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} districts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
