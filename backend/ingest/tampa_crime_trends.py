"""
backend/ingest/tampa_crime_trends.py
task: data-082
lane: data

Ingests Tampa Police Department crime data and calculates 12-month
crime trends by district via ArcGIS outStatistics aggregation.

Source:
  ArcGIS FeatureServer — org v400IkDOw1ad7Yad (same as Raleigh permits)
  Service: Police_Incidents/FeatureServer/0 (616K+ records, updated daily)

  Key fields: reported_date (esriFieldTypeDate), district (string),
              crime_type (string). Has point geometry.

  Note: Daily_Police_Incidents is a rolling 1-day feed (~127 records).
  Police_Incidents is the full historical dataset used here.

Output:
  data/raw/tampa_crime_trends.json

Usage:
  python backend/ingest/tampa_crime_trends.py
  python backend/ingest/tampa_crime_trends.py --dry-run
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

FEATURESERVER_URL = (
    "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services"
    "/Police_Incidents/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/tampa_crime_trends.json")

DATE_FIELD = "reported_date"
GROUP_FIELD = "district"

DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Downtown":  (27.950, -82.458),
    "North":     (28.020, -82.460),
    "Northeast": (28.010, -82.400),
    "Northwest": (28.010, -82.510),
    "Southeast": (27.920, -82.400),
    "Southwest": (27.920, -82.510),
}

TAMPA_LAT = 27.9506
TAMPA_LON = -82.4572

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
        district = str(attrs.get(GROUP_FIELD) or "").strip()
        if not district or district == "UNK":
            continue
        count = int(attrs.get("crime_count") or 0)
        results[district] = results.get(district, 0) + count
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
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        centroid = DISTRICT_CENTROIDS.get(district)
        lat = centroid[0] if centroid else TAMPA_LAT
        lon = centroid[1] if centroid else TAMPA_LON
        slug = district.lower().replace(" ", "_")
        records.append({
            "region_type": "district",
            "region_id": f"tampa_district_{slug}",
            "district_id": district,
            "district_name": f"Tampa {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat,
            "longitude": lon,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "tampa_crime_trends",
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
        description="Ingest Tampa PD crime trends by district from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Tampa crime trends ingest — source: {FEATURESERVER_URL}")

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
    print(f"  {len(current_data)} districts, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} districts, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    for r in records:
        print(f"  {r['district_name']}: {r['crime_12mo']:,} current, {r['crime_prior_12mo']:,} prior → {r['crime_trend']} ({r['crime_trend_pct']:+.1f}%)")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
