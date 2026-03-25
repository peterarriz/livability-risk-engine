"""
backend/ingest/dayton_crime_trends.py
task: data-070
lane: data

Ingests Dayton Police Department crime data and calculates 12-month
crime trends by district.

Source:
  ArcGIS MapServer — maps.daytonohio.gov (City of Dayton GIS)
  Service: Police/Crimes_Last_Two_Years/MapServer/0
  URL: https://maps.daytonohio.gov/gisservices/rest/services/Police/Crimes_Last_Two_Years/MapServer/0

  Key fields (verified 2026-03-25):
    reportdate  — date of incident (esriFieldTypeDate, epoch ms)
    district    — patrol district (e.g. "East District", "West District")
    x           — longitude
    y           — latitude

  Alternative (all data since 2016):
    .../Police/Crimes_Greater2016/MapServer/0

Output:
  data/raw/dayton_crime_trends.json

Usage:
  python backend/ingest/dayton_crime_trends.py
  python backend/ingest/dayton_crime_trends.py --dry-run
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

MAPSERVER_URL = (
    "https://maps.daytonohio.gov/gisservices/rest/services"
    "/Police/Crimes_Last_Two_Years/MapServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/dayton_crime_trends.json")

DATE_FIELD = "reportdate"
DISTRICT_FIELD = "district"
LAT_FIELD = "y"
LON_FIELD = "x"

DAYTON_LAT = 39.7589
DAYTON_LON = -84.1917

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def fetch_crime_counts_with_centroids(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    url = f"{MAPSERVER_URL}/query"

    where_clause = (
        f"{DATE_FIELD} >= {_date_str(start_date)} "
        f"AND {DATE_FIELD} < {_date_str(end_date)}"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
        {"statisticType": "avg", "onStatisticField": LAT_FIELD,
         "outStatisticFieldName": "avg_lat"},
        {"statisticType": "avg", "onStatisticField": LON_FIELD,
         "outStatisticFieldName": "avg_lon"},
    ])

    params = {
        "where": where_clause,
        "groupByFieldsForStatistics": DISTRICT_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(url, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    results: dict[str, dict] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        district = str(attrs.get(DISTRICT_FIELD) or "").strip().upper()
        if not district:
            continue
        try:
            count = int(attrs.get("crime_count") or 0)
        except (TypeError, ValueError):
            count = 0
        try:
            avg_lat = float(attrs.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(attrs.get("avg_lon") or 0) or None
        except (TypeError, ValueError):
            avg_lon = None
        results[district] = {"count": count, "lat": avg_lat, "lon": avg_lon}

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
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        curr = current_data.get(district, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(district, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "district",
            "region_id": f"dayton_district_{district.lower().replace(' ', '_')}",
            "district_id": district,
            "district_name": f"Dayton {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or DAYTON_LAT,
            "longitude": lon or DAYTON_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "dayton_crime_trends",
        "source_url": MAPSERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Dayton DPD crime trends by district from ArcGIS MapServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Dayton crime trends ingest — source: {MAPSERVER_URL}")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts_with_centroids(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} districts, {sum(d['count'] for d in current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} districts, {sum(d['count'] for d in prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
