"""
backend/ingest/orlando_crime_trends.py
task: data-057
lane: data

Ingests Orlando Police Department crime data and calculates 12-month crime
trends by zone/district.

Source:
  ArcGIS Hub — data-cityoforlando.opendata.arcgis.com
  FeatureServer URL (MUST VERIFY):
    https://services1.arcgis.com/ySBMu4XsNZMHPCce/arcgis/rest/services/
    OPD_Crime_Incidents/FeatureServer/0

  Verify: python backend/ingest/orlando_crime_trends.py --dry-run
  Or check: https://data-cityoforlando.opendata.arcgis.com (search "crime")
  Or: curl "https://hub.arcgis.com/api/v3/search?q=crime+incidents+Orlando&page[size]=5"

  Key fields (MUST VERIFY via --dry-run):
    INCIDENTDate — date of incident
    ZONE         — patrol zone
    OBJECTID     — for count aggregation

Output:
  data/raw/orlando_crime_trends.json

Usage:
  python backend/ingest/orlando_crime_trends.py
  python backend/ingest/orlando_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# MUST VERIFY service URL via: https://data-cityoforlando.opendata.arcgis.com
FEATURESERVER_URL = (
    "https://services1.arcgis.com/ySBMu4XsNZMHPCce/arcgis/rest/services"
    "/OPD_Crime_Incidents/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/orlando_crime_trends.json")

DATE_FIELD = "INCIDENTDate"   # MUST VERIFY
GROUP_FIELD = "ZONE"          # MUST VERIFY — may be "District", "Sector", "Beat"

ORLANDO_LAT = 28.5383
ORLANDO_LON = -81.3792

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
        zone = str(attrs.get(GROUP_FIELD) or "").strip().upper()
        if not zone:
            continue
        count = int(attrs.get("crime_count") or 0)
        results[zone] = results.get(zone, 0) + count

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
    all_zones = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zone in sorted(all_zones):
        current_count = current_data.get(zone, 0)
        prior_count = prior_data.get(zone, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "zone",
            "region_id": f"orlando_zone_{zone}",
            "district_id": zone,
            "district_name": f"Orlando Zone {zone}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": ORLANDO_LAT,
            "longitude": ORLANDO_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "orlando_crime_trends",
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
        description="Ingest Orlando OPD crime trends by zone from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Orlando: no public crime data API available.")
    print("  The OPD Crimes dataset on data.cityoforlando.net has been removed or made private.")
    print("  Writing 0-record staging file.")
    write_staging_file([], args.output)


if __name__ == "__main__":
    main()
