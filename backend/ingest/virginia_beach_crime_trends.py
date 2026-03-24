"""
backend/ingest/virginia_beach_crime_trends.py
task: data-057
lane: data

Ingests Virginia Beach Police Department crime data and calculates 12-month
crime trends by precinct/district.

Source:
  ArcGIS FeatureServer — data.virginiabeach.gov
  FeatureServer URL:
    https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/
    Police_Incident_Reports_view/FeatureServer/0

  Key fields:
    Date_Occurred — date of incident
    Precinct      — patrol precinct
    OBJECTID      — for count aggregation

  Note: Non-spatial table (no geometry); uses Precinct for geographic grouping.

Output:
  data/raw/virginia_beach_crime_trends.json

Usage:
  python backend/ingest/virginia_beach_crime_trends.py
  python backend/ingest/virginia_beach_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

FEATURESERVER_URL = (
    "https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services"
    "/Police_Incident_Reports_view/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/virginia_beach_crime_trends.json")

DATE_FIELD = "Date_Occurred"
GROUP_FIELD = "Precinct"

VIRGINIA_BEACH_LAT = 36.8529
VIRGINIA_BEACH_LON = -75.9780

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = f"{FEATURESERVER_URL}/query"
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
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        precinct = str(attrs.get(GROUP_FIELD) or "").strip().upper()
        if not precinct:
            continue
        count = int(attrs.get("crime_count") or 0)
        results[precinct] = results.get(precinct, 0) + count

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
    all_precincts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for precinct in sorted(all_precincts):
        current_count = current_data.get(precinct, 0)
        prior_count = prior_data.get(precinct, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "precinct",
            "region_id": f"virginia_beach_precinct_{precinct}",
            "district_id": precinct,
            "district_name": f"Virginia Beach Precinct {precinct}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": VIRGINIA_BEACH_LAT,
            "longitude": VIRGINIA_BEACH_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "virginia_beach_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Virginia Beach PD crime trends by precinct from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print("Fetching current 12-month Virginia Beach crime counts...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current Virginia Beach crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} precincts with current crime data.")

    print("Fetching prior 12-month Virginia Beach crime counts...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior Virginia Beach crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} precincts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} precinct trend records.")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
