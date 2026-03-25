"""
backend/ingest/san_jose_crime_trends.py
task: data-050
lane: data

Ingests San Jose Police Department crime data and calculates 12-month
crime trends by call type (crime category).

Source:
  CKAN Open Data Portal — data.sanjoseca.gov
  Dataset: Police Calls for Service (updated daily)
  API: https://data.sanjoseca.gov/api/3/action/datastore_search_sql

  Verified resource ID (2026 data): dc0ec99c-0c6b-45fb-b1ec-faf072fe4833

  Key fields (verified):
    OFFENSE_DATE — date of incident (timestamp)
    CALL_TYPE    — crime/call type category
    ADDRESS      — 100-block level address (no lat/lon, no district)

  Note: No district/beat field in the data. Grouping by CALL_TYPE instead.

Output:
  data/raw/san_jose_crime_trends.json — call type crime trend records

Usage:
  python backend/ingest/san_jose_crime_trends.py
  python backend/ingest/san_jose_crime_trends.py --dry-run
  python backend/ingest/san_jose_crime_trends.py --discover
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# CKAN datastore SQL endpoint on data.sanjoseca.gov
CKAN_BASE_URL = "https://data.sanjoseca.gov/api/3/action/datastore_search_sql"
RESOURCE_ID = "dc0ec99c-0c6b-45fb-b1ec-faf072fe4833"

DEFAULT_OUTPUT_PATH = Path("data/raw/san_jose_crime_trends.json")

DATE_FIELD = "OFFENSE_DATE"
GROUP_FIELD = "CALL_TYPE"

SAN_JOSE_LAT = 37.3382
SAN_JOSE_LON = -121.8863

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    sql = (
        f'SELECT "{GROUP_FIELD}", COUNT(*) AS crime_count '
        f'FROM "{RESOURCE_ID}" '
        f'WHERE "{DATE_FIELD}" >= \'{start_str}\' '
        f'AND "{DATE_FIELD}" < \'{end_str}\' '
        f'AND "{GROUP_FIELD}" IS NOT NULL '
        f'AND "{GROUP_FIELD}" != \'\' '
        f'GROUP BY "{GROUP_FIELD}"'
    )

    resp = requests.get(CKAN_BASE_URL, params={"sql": sql}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("success"):
        error = payload.get("error", {})
        raise RuntimeError(f"CKAN query error: {error}")

    results: dict[str, int] = {}
    for record in payload.get("result", {}).get("records", []):
        call_type = str(record.get(GROUP_FIELD) or "").strip()
        if not call_type:
            continue
        count = int(record.get("crime_count", 0))
        results[call_type] = results.get(call_type, 0) + count
    return results


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


def build_trend_records(
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    all_types = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for call_type in sorted(all_types):
        current_count = current_data.get(call_type, 0)
        prior_count = prior_data.get(call_type, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = call_type.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "call_type",
            "region_id": f"san_jose_type_{slug}",
            "district_id": call_type,
            "district_name": f"San Jose — {call_type.title()}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": SAN_JOSE_LAT,
            "longitude": SAN_JOSE_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "san_jose_crime_trends",
        "source_url": f"https://data.sanjoseca.gov (resource {RESOURCE_ID})",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def discover() -> None:
    """List available CKAN datasets on data.sanjoseca.gov."""
    url = "https://data.sanjoseca.gov/api/3/action/package_search"
    params = {"q": "police crime", "rows": 10}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print("CKAN search results (police/crime):")
        for pkg in data.get("result", {}).get("results", []):
            print(f"  {pkg.get('title','?')}")
            for res in pkg.get("resources", []):
                print(f"    resource: {res.get('id','?')} — {res.get('name','?')}")
    except Exception as exc:
        print(f"Discover failed: {exc}")
    print(f"\nAlso try: https://data.sanjoseca.gov (search 'police' or 'crime')")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest San Jose SJPD crime trends by call type from CKAN."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Query CKAN for available crime datasets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover()
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month San Jose crime counts "
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} call types, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month San Jose crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} call types, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} call type trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} call types")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
