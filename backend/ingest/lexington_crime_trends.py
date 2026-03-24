"""
backend/ingest/lexington_crime_trends.py
task: data-057
lane: data

Ingests Lexington-Fayette Urban County Government (LFUCG) police crime data
and calculates 12-month crime trends by division/zone.

Source:
  Socrata — data.lexingtonky.gov (MUST VERIFY portal type)
  Dataset: LFUCG Police Crime Incidents
  Dataset ID: e5v3-4r22 (MUST VERIFY via catalog API)
  Verify: curl "https://data.lexingtonky.gov/api/catalog/v1?q=crime+police&limit=5"

  Alternative: If data.lexingtonky.gov is ArcGIS Hub rather than Socrata,
  this script will fail and the portal type needs to be updated.
  Check: curl "https://data.lexingtonky.gov/api/catalog/v1?q=crime&limit=1"
  If that returns JSON with "results" array — it's Socrata.
  If it returns HTML or 404 — it's not Socrata; update to ArcGIS pattern.

  Key fields (MUST VERIFY field names via --dry-run):
    date_reported — date of incident
    division      — police division/zone
    latitude      — incident latitude
    longitude     — incident longitude

  Lexington-Fayette is a consolidated city-county government.

Output:
  data/raw/lexington_crime_trends.json

Usage:
  python backend/ingest/lexington_crime_trends.py
  python backend/ingest/lexington_crime_trends.py --dry-run
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

SOCRATA_DOMAIN = "data.lexingtonky.gov"
# MUST VERIFY dataset ID via: curl "https://data.lexingtonky.gov/api/catalog/v1?q=crime&limit=5"
DATASET_ID = "e5v3-4r22"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/lexington_crime_trends.json")

DATE_FIELD = "date_reported"   # MUST VERIFY
DISTRICT_FIELD = "division"    # MUST VERIFY — may be "zone", "beat", "sector"
LAT_FIELD = "latitude"
LON_FIELD = "longitude"

LEXINGTON_LAT = 38.0406
LEXINGTON_LON = -84.5037

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
        division = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not division:
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
        results[division] = {"count": count, "lat": avg_lat, "lon": avg_lon}

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
    all_divisions = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for division in sorted(all_divisions):
        curr = current_data.get(division, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(division, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "division",
            "region_id": f"lexington_division_{division}",
            "district_id": division,
            "district_name": f"Lexington Division {division}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or LEXINGTON_LAT,
            "longitude": lon or LEXINGTON_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "lexington_crime_trends",
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
        description="Ingest Lexington LFUCG crime trends by division from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    print("SKIPPED: Lexington does not publish crime data through a public API.")
    print("  data.lexingtonky.gov is an ArcGIS Hub with no crime incident layers.")
    print("  Only PDF monthly NIBRS reports are available at lexingtonky.gov.")
    print("  Exiting cleanly with 0 records.")


if __name__ == "__main__":
    main()
