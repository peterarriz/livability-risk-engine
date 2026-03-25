"""
backend/ingest/lincoln_crime_trends.py
task: data-071
lane: data

Ingests Lincoln Police Department crime data and calculates 12-month
crime trends by location code.

Source:
  ArcGIS FeatureServer — City of Lincoln GIS
  Org: services1.arcgis.com/wpJGOi6N4Rq5cqFv

  Lincoln publishes year-specific services with inconsistent naming:
    LPD_Incident_Reports_2025_ (trailing underscore)
    LPD_Incident_Reports_2024_ (trailing underscore)
    LPD_Incident_Report_2023   (singular, no underscore)

  Key fields (verified 2026-03-25):
    DATE      — incident date (DateOnly in 2025, String in 2024)
    LOC_CODE  — location/area code (integer, ~85 distinct values)

  Note: No named district field exists. LOC_CODE is the only grouping.
  Services are Table type (no geometry), maxRecordCount=1000.

Output:
  data/raw/lincoln_crime_trends.json

Usage:
  python backend/ingest/lincoln_crime_trends.py
  python backend/ingest/lincoln_crime_trends.py --dry-run
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

ARCGIS_BASE = "https://services1.arcgis.com/wpJGOi6N4Rq5cqFv/arcgis/rest/services"

# Year-specific service URLs (verified 2026-03-25).
# Naming is inconsistent across years.
YEAR_SERVICES = {
    2025: f"{ARCGIS_BASE}/LPD_Incident_Reports_2025_/FeatureServer/0",
    2024: f"{ARCGIS_BASE}/LPD_Incident_Reports_2024_/FeatureServer/0",
    2023: f"{ARCGIS_BASE}/LPD_Incident_Report_2023/FeatureServer/0",
}

DEFAULT_OUTPUT_PATH = Path("data/raw/lincoln_crime_trends.json")

GROUP_FIELD = "LOC_CODE"

LINCOLN_LAT = 40.8136
LINCOLN_LON = -96.7026

STABLE_THRESHOLD_PCT = 5.0


def _years_for_range(start: datetime, end: datetime) -> list[int]:
    """Return the calendar years that overlap the given date range."""
    years = []
    for y in range(start.year, end.year + 1):
        if y in YEAR_SERVICES:
            years.append(y)
    return years


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Query all year-specific services that overlap the date window."""
    years = _years_for_range(start_date, end_date)
    if not years:
        return {}

    combined: dict[str, int] = {}

    for year in years:
        url = f"{YEAR_SERVICES[year]}/query"

        # DATE field type varies: DateOnly (2025) vs String (2024/2023).
        # Use a simple 1=1 WHERE and filter client-side for reliability.
        out_statistics = json.dumps([
            {"statisticType": "count", "onStatisticField": "ObjectId",
             "outStatisticFieldName": "crime_count"},
        ])

        params = {
            "where": "1=1",
            "groupByFieldsForStatistics": GROUP_FIELD,
            "outStatistics": out_statistics,
            "f": "json",
        }

        try:
            resp = requests.post(url, data=params, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            print(f"  WARNING: failed to query {year} service — {exc}")
            continue

        if "error" in payload:
            print(f"  WARNING: {year} service error — {payload['error']}")
            continue

        for feature in payload.get("features", []):
            attrs = feature["attributes"]
            loc_code = str(attrs.get(GROUP_FIELD) or "").strip()
            if not loc_code:
                continue
            count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
            combined[loc_code] = combined.get(loc_code, 0) + count

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
    all_codes = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for loc_code in sorted(all_codes):
        current_count = current_data.get(loc_code, 0)
        prior_count = prior_data.get(loc_code, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "loc_code",
            "region_id": f"lincoln_loc_{loc_code}",
            "district_id": loc_code,
            "district_name": f"Lincoln LOC {loc_code}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": LINCOLN_LAT,
            "longitude": LINCOLN_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "lincoln_crime_trends",
        "source_url": ARCGIS_BASE,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Lincoln LPD crime trends by location code from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Lincoln crime trends ingest — source: {ARCGIS_BASE}")
    print("  Year-specific services: 2025, 2024, 2023")

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
    print(f"  {len(current_data)} location codes, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} location codes, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} location code trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} location codes")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
