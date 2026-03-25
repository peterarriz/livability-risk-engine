"""
backend/ingest/honolulu_crime_trends.py
task: data-071
lane: data

Ingests Honolulu Police Department crime data and calculates 12-month
crime trends by crime type.

Source:
  Socrata — data.honolulu.gov (City and County of Honolulu Open Data)
  Dataset: HPD Crime Incidents
  Dataset ID: vg88-5rn5 (verified 2026-03-25)
  Permalink: https://data.honolulu.gov/d/vg88-5rn5

  Key fields (verified 2026-03-25):
    date  — date of incident (calendar date)
    type  — crime type (e.g. ASSAULT, BURGLARY, THEFT/LARCENY)

  Note: No district/area field exists in this dataset. Trends are
  grouped by crime type instead. Dataset holds ~6 months of rolling
  data, so prior-year window may return zero.

Output:
  data/raw/honolulu_crime_trends.json

Usage:
  python backend/ingest/honolulu_crime_trends.py
  python backend/ingest/honolulu_crime_trends.py --dry-run
  python backend/ingest/honolulu_crime_trends.py --discover
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

SOCRATA_DOMAIN = "data.honolulu.gov"

# Verified 2026-03-25: HPD Crime Incidents dataset.
DATASET_ID = "vg88-5rn5"

DEFAULT_OUTPUT_PATH = Path("data/raw/honolulu_crime_trends.json")

# Verified 2026-03-25: "date" is calendar date, "type" is crime category.
DATE_FIELD = "date"
GROUP_FIELD = "type"

HONOLULU_LAT = 21.3069
HONOLULU_LON = -157.8583

STABLE_THRESHOLD_PCT = 5.0

PAGE_SIZE = 5000


def discover_datasets(domain: str) -> None:
    """Print matching datasets for manual verification."""
    url = f"https://{domain}/api/catalog/v1"
    resp = requests.get(url, params={"q": "crime incident", "limit": 10}, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    print(f"Found {len(results)} datasets matching 'crime incident' on {domain}:")
    for r in results:
        meta = r.get("resource", {})
        print(f"  {meta.get('id')} — {meta.get('name')}")


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    domain: str = SOCRATA_DOMAIN,
    dataset_id: str = DATASET_ID,
) -> dict[str, int]:
    url = f"https://{domain}/resource/{dataset_id}.json"

    start_str = start_date.strftime("%Y-%m-%dT00:00:00")
    end_str = end_date.strftime("%Y-%m-%dT00:00:00")
    where_clause = f"{DATE_FIELD} >= '{start_str}' AND {DATE_FIELD} < '{end_str}'"

    params = {
        "$select": f"{GROUP_FIELD}, count(*) as crime_count",
        "$where": where_clause,
        "$group": GROUP_FIELD,
        "$limit": PAGE_SIZE,
    }

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    records = resp.json()

    results: dict[str, int] = {}
    for row in records:
        district = str(row.get(GROUP_FIELD) or "").strip()
        if not district:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        results[district] = results.get(district, 0) + count
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
    for crime_type in sorted(all_types):
        current_count = current_data.get(crime_type, 0)
        prior_count = prior_data.get(crime_type, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = crime_type.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        records.append({
            "region_type": "category",
            "region_id": f"honolulu_category_{slug}",
            "district_id": crime_type,
            "district_name": f"Honolulu {crime_type}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": HONOLULU_LAT,
            "longitude": HONOLULU_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "honolulu_crime_trends",
        "source_url": f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Honolulu HPD crime trends by district from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="List available datasets on the portal and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover_datasets(SOCRATA_DOMAIN)
        return

    print(f"Honolulu crime trends ingest — {SOCRATA_DOMAIN} / {DATASET_ID}")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} categories, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} categories, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} categories")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
