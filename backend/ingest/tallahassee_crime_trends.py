"""
backend/ingest/tallahassee_crime_trends.py
task: data-068
lane: data

Ingests Tallahassee Police Department crime data and calculates
12-month crime trends by zone.

Source:
  Socrata — data.talgov.com (City of Tallahassee Open Data)
  Dataset: TPD Police Calls for Service (or Incidents)

  MUST VERIFY dataset ID:
    Visit https://data.talgov.com and search "police incidents" or
    "calls for service" to find the correct dataset.
    curl "https://data.talgov.com/api/catalog/v1?q=crime+incidents&limit=10"
    curl "https://data.talgov.com/api/catalog/v1?q=police+calls&limit=10"

  Current estimate (MUST VERIFY):
    Dataset ID:  f476-psrc
    Date field:  incident_date
    Group field: zone

Output:
  data/raw/tallahassee_crime_trends.json

Usage:
  python backend/ingest/tallahassee_crime_trends.py
  python backend/ingest/tallahassee_crime_trends.py --dry-run
  python backend/ingest/tallahassee_crime_trends.py --discover

Environment variables (optional):
  SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_DOMAIN = "data.talgov.com"

# MUST VERIFY: visit https://data.talgov.com and search for crime/police incidents.
# Run: python backend/ingest/tallahassee_crime_trends.py --discover
DATASET_ID = "f476-psrc"

CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/tallahassee_crime_trends.json")

# MUST VERIFY: actual field names in the dataset.
# Common Socrata field names for date and district/zone.
DATE_FIELD = "incident_date"
DISTRICT_FIELD = "zone"

STABLE_THRESHOLD_PCT = 5.0

# City center fallback coordinates
TALLAHASSEE_LAT = 30.4518
TALLAHASSEE_LON = -84.2807


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Aggregate crime counts per zone via SoQL GROUP BY."""
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": f"{DISTRICT_FIELD}, count(*) as crime_count",
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 500,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"Socrata error: {rows}")

    results: dict[str, int] = {}
    for row in rows:
        zone = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not zone:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        results[zone] = count

    return results


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
    all_zones = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zone in sorted(all_zones):
        current_count = current_data.get(zone, 0)
        prior_count = prior_data.get(zone, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = zone.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "district",
            "region_id": f"tallahassee_zone_{slug}",
            "district_id": zone,
            "district_name": f"Tallahassee Zone {zone}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": TALLAHASSEE_LAT,
            "longitude": TALLAHASSEE_LON,
        })
    return records


def discover_datasets(app_token: str | None) -> None:
    """Show available datasets on data.talgov.com matching crime/police keywords."""
    print(f"Discovering datasets on {SOCRATA_DOMAIN}...")
    url = f"https://{SOCRATA_DOMAIN}/api/catalog/v1"
    for q in ["police incidents", "police calls", "crime", "police"]:
        params: dict = {"q": q, "limit": 5}
        if app_token:
            params["$$app_token"] = app_token
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                print(f"\nResults for '{q}':")
                for r in results[:3]:
                    m = r.get("resource", {})
                    print(f"  ID: {m.get('id', '?')}  Name: {m.get('name', '?')[:60]}")
        except Exception as exc:
            print(f"  Error for '{q}': {exc}", file=sys.stderr)


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "tallahassee_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Tallahassee TPD crime trends by zone from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="Show available datasets on data.talgov.com.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if args.discover:
        discover_datasets(app_token)
        return

    print(f"Tallahassee crime trends ingest — source: {CRIMES_URL}")
    print("NOTE: Dataset ID and field names are MUST VERIFY estimates.")
    print("      Run --discover to find the correct dataset ID.")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} zones, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} zones, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} zone trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} zones")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
