"""
backend/ingest/houston_crime_trends.py
task: data-049
lane: data

Ingests Houston Police Department NIBRS crime data (CSV) and calculates
12-month crime trends by beat.

Source:
  Static CSV files on city website:
  https://www.houstontx.gov/police/cs/xls/NIBRSPublicView{year}.csv

  Key fields: Occurrence Date, Beat, NIBRS Class, NIBRS Description,
              Map Longitude, Map Latitude

Output:
  data/raw/houston_crime_trends.json

Usage:
  python backend/ingest/houston_crime_trends.py
  python backend/ingest/houston_crime_trends.py --dry-run
  python backend/ingest/houston_crime_trends.py --discover
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

CSV_URL_TEMPLATE = (
    "https://www.houstontx.gov/police/cs/xls/NIBRSPublicView{year}.csv"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/houston_crime_trends.json")

STABLE_THRESHOLD_PCT = 5.0
HOUSTON_LAT = 29.7604
HOUSTON_LON = -95.3698


def _years_in_range(start: datetime, end: datetime) -> list[int]:
    years = set()
    d = start
    while d <= end:
        years.add(d.year)
        d += timedelta(days=365)
    years.add(end.year)
    return sorted(years)


def _fetch_and_count(
    year: int,
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    """Download CSV for one year, filter by date range, count by beat."""
    url = CSV_URL_TEMPLATE.format(year=year)
    print(f"    Downloading {url}...", end=" ", flush=True)

    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()

    start_str = start_date.strftime("%m/%d/%Y")
    end_str = end_date.strftime("%m/%d/%Y")
    start_iso = start_date.strftime("%Y-%m-%d")
    end_iso = end_date.strftime("%Y-%m-%d")

    counts: dict[str, int] = {}
    lines_read = 0

    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        raw_date = (row.get("Occurrence Date") or "").strip()
        # Houston CSV dates are MM/DD/YYYY
        try:
            if "/" in raw_date:
                parts = raw_date.split("/")
                dt_str = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
            else:
                dt_str = raw_date[:10]
        except (IndexError, ValueError):
            continue

        if dt_str < start_iso or dt_str >= end_iso:
            continue

        beat = (row.get("Beat") or "").strip().upper()
        if beat:
            counts[beat] = counts.get(beat, 0) + 1
        lines_read += 1
        if dry_run and lines_read >= 5000:
            break

    total = sum(counts.values())
    print(f"{total:,} matching crimes in {len(counts)} beats")
    return counts


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    combined: dict[str, int] = {}
    for year in _years_in_range(start_date, end_date):
        try:
            year_counts = _fetch_and_count(year, start_date, end_date, dry_run)
            for beat, count in year_counts.items():
                combined[beat] = combined.get(beat, 0) + count
        except Exception as exc:
            print(f"WARN: year {year} — {exc}")
    return combined


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
    all_beats = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for beat in sorted(all_beats):
        current_count = current_data.get(beat, 0)
        prior_count = prior_data.get(beat, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "beat",
            "region_id": f"houston_beat_{beat}",
            "district_id": beat,
            "district_name": f"Houston Beat {beat}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": HOUSTON_LAT,
            "longitude": HOUSTON_LON,
        })
    return records


def discover_resource() -> None:
    """List available HPD NIBRS CSV files."""
    print("Discovering Houston PD NIBRS CSV files...")
    for year in range(2019, datetime.now().year + 1):
        url = CSV_URL_TEMPLATE.format(year=year)
        try:
            resp = requests.head(url, timeout=10)
            size = resp.headers.get("Content-Length", "?")
            print(f"  {year}: HTTP {resp.status_code} — {url} (size={size})")
        except Exception as exc:
            print(f"  {year}: ERROR — {exc}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "houston_crime_trends",
        "source_url": CSV_URL_TEMPLATE.format(year="YYYY"),
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Houston HPD crime trends by beat from CSV downloads."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="List available HPD NIBRS CSV files by year.")
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

    print(f"Fetching current 12-month Houston crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data = fetch_crime_counts(current_start, now, args.dry_run)
    print(f"  {len(current_data)} beats with current data.")

    print(f"\nFetching prior 12-month Houston crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(prior_start, prior_end, args.dry_run)
    print(f"  {len(prior_data)} beats with prior data.")

    if not current_data and not prior_data:
        print("ERROR: no data returned from any year.", file=sys.stderr)
        sys.exit(1)

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} beat trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} beats")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
