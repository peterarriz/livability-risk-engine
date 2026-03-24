"""
backend/ingest/chandler_crime_trends.py
task: data-058
lane: data

Ingests Chandler Police Department crime data (CSV) and calculates
12-month crime trends by district.

Source:
  Chandler PD Open Data — General Offense Reports (CSV download)
  Portal: https://data.chandlerpd.com/
  CSV:    https://data.chandlerpd.com/catalog/general-offenses/download/csv/

  Key fields:
    report_event_date — date of incident  (YYYY-MM-DD)
    report_district   — police district   (1-5)

Output:
  data/raw/chandler_crime_trends.json

Usage:
  python backend/ingest/chandler_crime_trends.py
  python backend/ingest/chandler_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

CSV_URL = "https://data.chandlerpd.com/catalog/general-offenses/download/csv/"

DEFAULT_OUTPUT_PATH = Path("data/raw/chandler_crime_trends.json")

DATE_FIELD = "report_event_date"
GROUP_FIELD = "report_district"

CHANDLER_LAT = 33.3062
CHANDLER_LON = -111.8413

STABLE_THRESHOLD_PCT = 5.0


def fetch_and_count(
    start_date: datetime,
    end_date: datetime,
    rows: list[dict],
) -> dict[str, int]:
    """Filter rows by date range and count by district."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    results: dict[str, int] = {}
    for row in rows:
        event_date = row.get(DATE_FIELD, "").strip()
        if not event_date:
            continue
        if event_date < start_str or event_date >= end_str:
            continue
        district = row.get(GROUP_FIELD, "").strip()
        if not district:
            continue
        results[district] = results.get(district, 0) + 1
    return results


def download_csv() -> list[dict]:
    """Download the full CSV and return rows as list of dicts."""
    print(f"  Downloading CSV from {CSV_URL}...")
    resp = requests.get(CSV_URL, timeout=120)
    resp.raise_for_status()

    text = resp.text
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"  Downloaded {len(rows):,} rows.")
    return rows


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
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = district.lower().replace(" ", "_")
        records.append({
            "region_type": "district",
            "region_id": f"chandler_district_{slug}",
            "district_id": district,
            "district_name": f"Chandler District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": CHANDLER_LAT,
            "longitude": CHANDLER_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "chandler_crime_trends",
        "source_url": CSV_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Chandler PD crime trends by district from open data CSV."
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

    print("Downloading Chandler PD General Offense CSV...")
    try:
        rows = download_csv()
    except Exception as exc:
        print(f"ERROR: failed to download CSV — {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nCounting current 12-month crimes ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data = fetch_and_count(current_start, now, rows)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nCounting prior 12-month crimes ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data = fetch_and_count(prior_start, prior_end, rows)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} districts, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
