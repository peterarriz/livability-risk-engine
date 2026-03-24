"""
backend/ingest/new_orleans_crime_trends.py
task: data-056
lane: data

Ingests New Orleans Police Department crime data and calculates 12-month
crime trends by district.

Source:
  Socrata — data.nola.gov
  Per-year datasets (Electronic Police Reports):
    2026: TBD
    2025: agqi-9adb
    2024: c5iy-ew8n
    2023: j3gz-62a2

  Key fields: occurred_date_time, district, signal_description

Output:
  data/raw/new_orleans_crime_trends.json

Usage:
  python backend/ingest/new_orleans_crime_trends.py
  python backend/ingest/new_orleans_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SOCRATA_DOMAIN = "data.nola.gov"

YEAR_DATASETS: dict[int, str] = {
    2025: "agqi-9adb",
    2024: "c5iy-ew8n",
    2023: "j3gz-62a2",
}

DEFAULT_OUTPUT_PATH = Path("data/raw/new_orleans_crime_trends.json")

DATE_FIELD = "occurred_date_time"
GROUP_FIELD = "district"

NEW_ORLEANS_LAT = 29.9511
NEW_ORLEANS_LON = -90.0715

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def _years_in_range(start: datetime, end: datetime) -> list[int]:
    years = []
    for y in range(start.year, end.year + 1):
        if y in YEAR_DATASETS:
            years.append(y)
    return years


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    years = _years_in_range(start_date, end_date)
    if not years:
        return {}

    totals: dict[str, int] = {}
    for year in years:
        dataset_id = YEAR_DATASETS[year]
        url = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"

        where_clause = (
            f"{DATE_FIELD} >= '{_date_str(start_date)}' "
            f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
        )

        params: dict = {
            "$select": f"{GROUP_FIELD}, count(*) as crime_count",
            "$where": where_clause,
            "$group": GROUP_FIELD,
            "$limit": 100,
        }
        if app_token:
            params["$$app_token"] = app_token

        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:
            print(f"  WARN: {year} dataset {dataset_id} failed: {exc}", file=sys.stderr)
            continue

        for row in rows:
            district = str(row.get(GROUP_FIELD) or "").strip()
            if not district:
                continue
            try:
                count = int(row.get("crime_count", 0))
            except (TypeError, ValueError):
                count = 0
            totals[district] = totals.get(district, 0) + count

    return totals


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
            "region_id": f"new_orleans_district_{slug}",
            "district_id": district,
            "district_name": f"New Orleans District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": NEW_ORLEANS_LAT,
            "longitude": NEW_ORLEANS_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "new_orleans_crime_trends",
        "source_url": f"https://{SOCRATA_DOMAIN}",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest New Orleans crime trends by district from Socrata (per-year datasets)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month New Orleans crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month New Orleans crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
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
