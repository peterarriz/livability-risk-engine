"""
backend/ingest/mesa_crime_trends.py
task: data-057
lane: data

Ingests Mesa Police Department crime data and calculates 12-month crime
trends by crime type.

Source:
  Socrata — data.mesaaz.gov
  Dataset: Crime Reporting Statistics (Part 1 offenses)
  Dataset ID: 37q9-d27y

  Key fields:
    report_date   — date of incident
    crime_type    — offense category (no geographic district field available)
    latitude      — incident latitude
    longitude     — incident longitude

  Note: Only Part 1 offenses (homicide, rape, robbery, assault, burglary,
  larceny, motor vehicle theft, arson). No patrol district field available;
  groups by crime_type instead.

Output:
  data/raw/mesa_crime_trends.json

Usage:
  python backend/ingest/mesa_crime_trends.py
  python backend/ingest/mesa_crime_trends.py --dry-run
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

SOCRATA_DOMAIN = "data.mesaaz.gov"
DATASET_ID = "37q9-d27y"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/mesa_crime_trends.json")

DATE_FIELD = "report_date"
DISTRICT_FIELD = "crime_type"  # No geographic field; group by crime type
LAT_FIELD = "latitude"
LON_FIELD = "longitude"

MESA_LAT = 33.4152
MESA_LON = -111.8315

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts_with_centroids(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count, "
            f"avg({LAT_FIELD} :: number) as avg_lat, "
            f"avg({LON_FIELD} :: number) as avg_lon"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 100,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, dict] = {}
    for row in rows:
        crime_type = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not crime_type:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        try:
            avg_lat = float(row.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(row.get("avg_lon") or 0) or None
        except (TypeError, ValueError):
            avg_lon = None
        results[crime_type] = {"count": count, "lat": avg_lat, "lon": avg_lon}

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
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    all_types = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for crime_type in sorted(all_types):
        curr = current_data.get(crime_type, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(crime_type, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "crime_type",
            "region_id": f"mesa_crime_type_{crime_type}",
            "district_id": crime_type,
            "district_name": f"Mesa {crime_type}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or MESA_LAT,
            "longitude": lon or MESA_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "mesa_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Mesa PD crime trends by crime type from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    print("SKIPPED: Mesa's Socrata crime dataset (37q9-d27y) ends at 2020-12-31.")
    print("  data.mesaaz.gov has Part 1 offense data only through 2020.")
    print("  No current crime data is available via this API.")
    print("  Exiting cleanly with 0 records.")


if __name__ == "__main__":
    main()
