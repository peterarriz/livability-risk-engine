"""
backend/ingest/las_vegas_crime_trends.py
task: data-049
lane: data

Ingests Las Vegas Metropolitan Police Department crime data and calculates
12-month crime trends by area command.

Source:
  ArcGIS FeatureServer — LVMPD NIBRS Reported Crimes
  Yearly layers: LVMPD_Reported_NIBRS_Crimes_Against_Persons, etc.
  Calls for Service: LVMPD_Calls_For_Service_{year}

  Key fields: ReportedOn/IncidentDate, Area_Command/Beat, OffenseGroup

Output:
  data/raw/las_vegas_crime_trends.json

Usage:
  python backend/ingest/las_vegas_crime_trends.py
  python backend/ingest/las_vegas_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# Use CFS yearly layers — they have good geographic breakdown
CFS_TEMPLATE = (
    "https://services.arcgis.com/jjSk6t82vIntwDbs/arcgis/rest/services"
    "/LVMPD_Calls_For_Service_{year}/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/las_vegas_crime_trends.json")

DATE_FIELD = "IncidentDate"
GROUP_FIELD = "Classification"

LAS_VEGAS_LAT = 36.1699
LAS_VEGAS_LON = -115.1398

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def _years_in_range(start_date: datetime, end_date: datetime) -> list[int]:
    years = set()
    d = start_date
    while d <= end_date:
        years.add(d.year)
        d += timedelta(days=365)
    years.add(end_date.year)
    return sorted(years)


def _fetch_year_counts(
    year: int,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = CFS_TEMPLATE.format(year=year) + "/query"

    where_clause = (
        f"{DATE_FIELD} >= {_date_str(start_date)} "
        f"AND {DATE_FIELD} < {_date_str(end_date)}"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
    ])

    params = {
        "where": where_clause,
        "groupByFieldsForStatistics": GROUP_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(url, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error (year {year}): {payload['error']}")

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        group = str(attrs.get(GROUP_FIELD) or "").strip()
        if not group:
            continue
        results[group] = results.get(group, 0) + int(attrs.get("crime_count", 0))
    return results


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    combined: dict[str, int] = {}
    for year in _years_in_range(start_date, end_date):
        print(f"    Querying LVMPD CFS {year}...", end=" ", flush=True)
        try:
            year_counts = _fetch_year_counts(year, start_date, end_date)
            total = sum(year_counts.values())
            print(f"{total:,} calls")
            for group, count in year_counts.items():
                combined[group] = combined.get(group, 0) + count
        except Exception as exc:
            print(f"WARN: {exc}")
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
    all_groups = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for group in sorted(all_groups):
        current_count = current_data.get(group, 0)
        prior_count = prior_data.get(group, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = group.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "city",
            "region_id": f"las_vegas_type_{slug}",
            "district_id": group,
            "district_name": f"Las Vegas — {group}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": LAS_VEGAS_LAT,
            "longitude": LAS_VEGAS_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "las_vegas_crime_trends",
        "source_url": CFS_TEMPLATE.format(year="YYYY"),
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Las Vegas LVMPD crime trends by category from ArcGIS FeatureServer."
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

    print(f"Fetching current 12-month Las Vegas crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data = fetch_crime_counts(current_start, now)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} categories, {total_current:,} total calls.")

    print(f"\nFetching prior 12-month Las Vegas crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(prior_start, prior_end)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} categories, {total_prior:,} total calls.")

    if not current_data and not prior_data:
        print("ERROR: no data returned.", file=sys.stderr)
        sys.exit(1)

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} category trend records.")

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
