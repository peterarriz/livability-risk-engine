"""
backend/ingest/phoenix_crime_trends.py
task: data-050
lane: data

Ingests Phoenix Police Department crime data and calculates 12-month
crime trends by ZIP code.

Source:
  CKAN Datastore — phoenixopendata.com
  Dataset: Crime Data
  Resource ID: 0ce3411a-2fc6-4302-a33f-167f68608a20

  Key fields:
    "OCCURRED ON"        — text date (MM/DD/YYYY  HH:MM)
    "ZIP"                — ZIP code
    "UCR CRIME CATEGORY" — crime type
    "GRID"               — police grid (too granular; ZIP preferred)

  Note: Phoenix does NOT have an ArcGIS FeatureServer for crime incidents.
  The portal runs CKAN 2.9 with a PostgreSQL-backed Datastore SQL API.

Method:
  1. Aggregate crime counts by ZIP for the last 12 months.
  2. Aggregate crime counts by ZIP for the prior 12 months.
  3. Calculate percent change -> crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/phoenix_crime_trends.json — ZIP crime trend records

Usage:
  python backend/ingest/phoenix_crime_trends.py
  python backend/ingest/phoenix_crime_trends.py --dry-run
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

CKAN_SQL_URL = "https://www.phoenixopendata.com/api/3/action/datastore_search_sql"
RESOURCE_ID = "0ce3411a-2fc6-4302-a33f-167f68608a20"

DEFAULT_OUTPUT_PATH = Path("data/raw/phoenix_crime_trends.json")

# Field names (quoted in SQL because they contain spaces)
DATE_FIELD = "OCCURRED ON"
GROUP_FIELD = "ZIP"

PHOENIX_LAT = 33.4484
PHOENIX_LON = -112.0740

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """
    Fetch crime counts grouped by ZIP code via CKAN Datastore SQL.
    """
    start_str = start_date.strftime("%m/%d/%Y")
    end_str = end_date.strftime("%m/%d/%Y")

    sql = (
        f'SELECT "{GROUP_FIELD}", COUNT(*) as crime_count '
        f'FROM "{RESOURCE_ID}" '
        f'WHERE TO_DATE(LEFT("{DATE_FIELD}", 10), \'MM/DD/YYYY\') >= \'{start_date:%Y-%m-%d}\'::date '
        f'AND TO_DATE(LEFT("{DATE_FIELD}", 10), \'MM/DD/YYYY\') < \'{end_date:%Y-%m-%d}\'::date '
        f'AND "{GROUP_FIELD}" IS NOT NULL AND "{GROUP_FIELD}" != \'\' '
        f'GROUP BY "{GROUP_FIELD}"'
    )

    resp = requests.get(CKAN_SQL_URL, params={"sql": sql}, timeout=120)
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("success"):
        error = payload.get("error", {})
        raise RuntimeError(f"CKAN SQL error: {error}")

    results: dict[str, int] = {}
    for record in payload.get("result", {}).get("records", []):
        zip_code = str(record.get(GROUP_FIELD) or "").strip()
        if not zip_code:
            continue
        results[zip_code] = results.get(zip_code, 0) + int(record.get("crime_count", 0))
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
    all_zips = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zip_code in sorted(all_zips):
        current_count = current_data.get(zip_code, 0)
        prior_count = prior_data.get(zip_code, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "zip",
            "region_id": f"phoenix_zip_{zip_code}",
            "district_id": zip_code,
            "district_name": f"Phoenix ZIP {zip_code}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": PHOENIX_LAT,
            "longitude": PHOENIX_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "phoenix_crime_trends",
        "source_url": CKAN_SQL_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Phoenix PD crime trends by ZIP from CKAN Datastore."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Phoenix crime counts "
          f"({current_start:%Y-%m-%d} \u2192 {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} ZIP codes, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Phoenix crime counts "
          f"({prior_start:%Y-%m-%d} \u2192 {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} ZIP codes, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} ZIP trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} ZIP codes")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
