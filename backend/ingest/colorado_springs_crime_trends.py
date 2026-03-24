"""
backend/ingest/colorado_springs_crime_trends.py
task: data-057
lane: data

Ingests Colorado Springs Police Department crime data and calculates 12-month
crime trends by division/district.

Source:
  ArcGIS Hub — data-cospatial.opendata.arcgis.com (City of Colorado Springs GIS)
  FeatureServer URL (MUST VERIFY):
    https://services3.arcgis.com/oR4yfmG5eJFhSqy7/arcgis/rest/services/
    CSPD_Incidents/FeatureServer/0

  Verify: python backend/ingest/colorado_springs_crime_trends.py --dry-run
  Or check: https://data-cospatial.opendata.arcgis.com (search "crime" or "police")
  Or: curl "https://hub.arcgis.com/api/v3/search?q=crime+Colorado+Springs+police&page[size]=5"

  Note: Colorado Springs has a smaller open data footprint. Crime data may be
  limited or only available as annual statistical reports. If no FeatureServer
  is found, this script will fail non-fatally.

  Key fields (MUST VERIFY via --dry-run):
    REPORT_DATE   — date of incident
    Division      — patrol division
    OBJECTID      — for count aggregation

Output:
  data/raw/colorado_springs_crime_trends.json

Usage:
  python backend/ingest/colorado_springs_crime_trends.py
  python backend/ingest/colorado_springs_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# MUST VERIFY service URL via: https://data-cospatial.opendata.arcgis.com
FEATURESERVER_URL = (
    "https://services3.arcgis.com/oR4yfmG5eJFhSqy7/arcgis/rest/services"
    "/CSPD_Incidents/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/colorado_springs_crime_trends.json")

DATE_FIELD = "REPORT_DATE"   # MUST VERIFY
GROUP_FIELD = "Division"     # MUST VERIFY — may be "District", "Beat", "Sector"

COLORADO_SPRINGS_LAT = 38.8339
COLORADO_SPRINGS_LON = -104.8214

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
        division = str(attrs.get(GROUP_FIELD) or "").strip().upper()
        if not division:
            continue
        count = int(attrs.get("crime_count") or 0)
        results[division] = results.get(division, 0) + count

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
    all_divisions = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for division in sorted(all_divisions):
        current_count = current_data.get(division, 0)
        prior_count = prior_data.get(division, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "division",
            "region_id": f"colorado_springs_division_{division}",
            "district_id": division,
            "district_name": f"Colorado Springs Division {division}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": COLORADO_SPRINGS_LAT,
            "longitude": COLORADO_SPRINGS_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "colorado_springs_crime_trends",
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
        description="Ingest Colorado Springs PD crime trends by division from ArcGIS."
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

    print("Fetching current 12-month Colorado Springs crime counts...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current Colorado Springs crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} divisions with current crime data.")

    print("Fetching prior 12-month Colorado Springs crime counts...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior Colorado Springs crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} divisions with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} division trend records.")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
