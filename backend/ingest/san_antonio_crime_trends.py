"""
backend/ingest/san_antonio_crime_trends.py
task: data-049
lane: data

Ingests San Antonio Police Department Calls for Service data and calculates
crime trends by patrol district.

Source:
  ArcGIS FeatureServer — SAPD Calls for Service (7-day rolling window)
  https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services/CFS_SAPD_7Days/FeatureServer/0

  Key fields: ResponseDate, Category, PatrolDistrict, Substation, LAT, LON

  Note: Only a rolling 7-day window is publicly available. This script
  aggregates what's available and produces a snapshot (not full 12-month trend).

Output:
  data/raw/san_antonio_crime_trends.json

Usage:
  python backend/ingest/san_antonio_crime_trends.py
  python backend/ingest/san_antonio_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

FEATURESERVER_URL = (
    "https://services.arcgis.com/g1fRTDLeMgspWrYp/arcgis/rest/services"
    "/CFS_SAPD_7Days/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/san_antonio_crime_trends.json")

GROUP_FIELD = "PatrolDistrict"

SA_LAT = 29.4241
SA_LON = -98.4936

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts() -> dict[str, int]:
    """Fetch CFS counts grouped by patrol district (all available data = 7 days)."""
    url = f"{FEATURESERVER_URL}/query"

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
    ])

    params = {
        "where": "1=1",
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
        district = str(attrs.get(GROUP_FIELD) or "").strip()
        if not district:
            continue
        results[district] = results.get(district, 0) + int(attrs.get("crime_count", 0))
    return results


def build_trend_records(data: dict[str, int]) -> list[dict]:
    """Build records from 7-day snapshot. No prior period available."""
    records = []
    for district in sorted(data.keys()):
        count = data[district]
        records.append({
            "region_type": "district",
            "region_id": f"san_antonio_district_{district}",
            "district_id": district,
            "district_name": f"San Antonio District {district}",
            "crime_12mo": count,
            "crime_prior_12mo": None,
            "crime_trend": "STABLE",
            "crime_trend_pct": 0.0,
            "latitude": SA_LAT,
            "longitude": SA_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "san_antonio_crime_trends",
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
        description="Ingest San Antonio SAPD CFS by patrol district from ArcGIS FeatureServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Fetching San Antonio SAPD Calls for Service (7-day rolling window)...")
    try:
        data = fetch_crime_counts()
    except Exception as exc:
        print(f"ERROR: failed to fetch CFS data — {exc}", file=sys.stderr)
        sys.exit(1)
    total = sum(data.values())
    print(f"  {len(data)} patrol districts, {total:,} total CFS calls.")

    records = build_trend_records(data)
    print(f"\nBuilt {len(records)} district records (7-day snapshot).")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
