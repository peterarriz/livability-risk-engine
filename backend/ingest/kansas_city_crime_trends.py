"""
backend/ingest/kansas_city_crime_trends.py
task: data-045
lane: data

Ingests Kansas City KCPD crime data and calculates 12-month crime trends by area
(patrol division).

Source:
  KCPD publishes crime data as separate per-year Socrata datasets on data.kcmo.org:
    - 2025: dmnp-9ajg   (fields: report, report_date, area, beat)
    - 2024: isbe-v4d8   (fields: report_no, reported_date, area, beat)
    - 2023: bfyq-5nh6   (fields: report, report_date, area, beat)

  Verify dataset IDs:
    curl "https://data.kcmo.org/api/catalog/v1?q=crime+kansas&domains=data.kcmo.org&limit=10"

  Note: Field names differ between years. The 2024 dataset uses "report_no" and
  "reported_date", while 2023 and 2025 use "report" and "report_date".

Method:
  1. Fetch crime counts by area for the last 12 months across relevant year datasets.
  2. Fetch crime counts by area for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/kansas_city_crime_trends.json — area crime trend records

Usage:
  python backend/ingest/kansas_city_crime_trends.py
  python backend/ingest/kansas_city_crime_trends.py --dry-run

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
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

# KCPD crime datasets are published per-year on data.kcmo.org.
# Each entry: (dataset_id, date_field_name, year)
YEARLY_DATASETS = [
    ("dmnp-9ajg", "report_date", 2025),
    ("isbe-v4d8", "reported_date", 2024),
    ("bfyq-5nh6", "report_date", 2023),
]

SOCRATA_DOMAIN = "data.kcmo.org"
DISTRICT_FIELD = "area"

DEFAULT_OUTPUT_PATH = Path("data/raw/kansas_city_crime_trends.json")

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def _datasets_for_range(
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[str, str]]:
    """
    Return the (dataset_id, date_field) pairs whose year overlaps with
    [start_date, end_date).
    """
    start_year = start_date.year
    end_year = end_date.year
    result = []
    for dataset_id, date_field, year in YEARLY_DATASETS:
        if start_year <= year <= end_year:
            result.append((dataset_id, date_field))
    return result


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total crime counts per area for a date range, querying all
    relevant yearly datasets and merging the results.
    Returns dict: area → {count, lat (None), lon (None)}.
    """
    datasets = _datasets_for_range(start_date, end_date)
    if not datasets:
        print(f"  WARNING: no datasets cover range {start_date.year}–{end_date.year}",
              file=sys.stderr)
        return {}

    merged: dict[str, int] = {}

    for dataset_id, date_field in datasets:
        url = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
        where_clause = (
            f"{date_field} >= '{_date_str(start_date)}' "
            f"AND {date_field} < '{_date_str(end_date)}'"
        )
        params: dict = {
            "$select": f"{DISTRICT_FIELD}, count(*) as crime_count",
            "$where": where_clause,
            "$group": DISTRICT_FIELD,
            "$limit": 200,
        }
        if app_token:
            params["$$app_token"] = app_token

        print(f"    Querying {dataset_id} ({date_field})...", end=" ", flush=True)
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        rows = resp.json()
        print(f"{len(rows)} areas.")

        for row in rows:
            area = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
            if not area:
                continue
            try:
                count = int(row.get("crime_count", 0))
            except (TypeError, ValueError):
                count = 0
            merged[area] = merged.get(area, 0) + count

    return {area: {"count": count, "lat": None, "lon": None}
            for area, count in merged.items()}


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
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    All areas appearing in either window get a record.
    """
    all_areas = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for area in sorted(all_areas):
        curr = current_data.get(area, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(area, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "area",
            "region_id": f"kansas_city_area_{area}",
            "district_id": area,
            "district_name": f"Kansas City {area}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat,
            "longitude": lon,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "kansas_city_crime_trends",
        "source_url": f"https://{SOCRATA_DOMAIN} (KCPD yearly datasets)",
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
        description="Ingest Kansas City KCPD crime trends by area from yearly Socrata datasets."
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if not app_token:
        print(
            "Note: SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register free at https://dev.socrata.com/register"
        )

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month crime counts ({_date_str(current_start)} → {_date_str(now)})...")
    try:
        current_data = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} areas with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} areas with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} area trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} areas")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
