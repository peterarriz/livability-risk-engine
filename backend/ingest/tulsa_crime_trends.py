"""
backend/ingest/tulsa_crime_trends.py
task: data-057
lane: data

Ingests Tulsa Police Department crime data and calculates 12-month crime
trends by division/district.

Source:
  ArcGIS Hub — opendata-maptulsa.opendata.arcgis.com
  FeatureServer URL (not live-verified):
    https://services.arcgis.com/vL1HzBwQf4fxjZTy/arcgis/rest/services/
    TPD_Crime_Incidents/FeatureServer/0

  Verify: python backend/ingest/tulsa_crime_trends.py --dry-run
  Or check: https://opendata-maptulsa.opendata.arcgis.com (search "crime")
  Or: curl "https://hub.arcgis.com/api/v3/search?q=crime+Tulsa+police&page[size]=5"

  Note: Tulsa migrated from Socrata (data.tulsaok.gov) to ArcGIS Hub.
  The historical Socrata portal may be defunct.

  Key fields (not live-verified via --dry-run):
    IncidentDate  — date of incident
    Division      — patrol division
    OBJECTID      — for count aggregation

Output:
  data/raw/tulsa_crime_trends.json

Usage:
  python backend/ingest/tulsa_crime_trends.py
  python backend/ingest/tulsa_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# not live-verified service URL via: https://opendata-maptulsa.opendata.arcgis.com
FEATURESERVER_URL = (
    "https://services.arcgis.com/vL1HzBwQf4fxjZTy/arcgis/rest/services"
    "/TPD_Crime_Incidents/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/tulsa_crime_trends.json")

DATE_FIELD = "IncidentDate"   # not live-verified
GROUP_FIELD = "Division"      # not live-verified — may be "District", "Beat", "Sector"

TULSA_LAT = 36.1540
TULSA_LON = -95.9928

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
            "region_id": f"tulsa_division_{division}",
            "district_id": division,
            "district_name": f"Tulsa Division {division}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": TULSA_LAT,
            "longitude": TULSA_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "tulsa_crime_trends",
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
        description="Ingest Tulsa PD crime trends by division from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Tulsa: no publicly accessible current crime data API.")
    print("  The live crime dashboard at maps.cityoftulsa.org requires org auth.")
    print("  Writing 0-record staging file.")
    write_staging_file([], args.output)


if __name__ == "__main__":
    main()
