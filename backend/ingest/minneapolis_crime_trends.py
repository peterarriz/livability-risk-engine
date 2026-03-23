"""
backend/ingest/minneapolis_crime_trends.py
task: data-050
lane: data

Ingests Minneapolis Police Department (MPD) crime data and calculates
12-month crime trends by precinct.

Source:
  ArcGIS FeatureServer -- opendata.minneapolismn.gov (ArcGIS Hub)
  Org: City_of_Minneapolis (afSMGVsC7QlRK1kZ)
  Service: Crime_Data
  URL: https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/Crime_Data/FeatureServer/0

  Key fields:
    Reported_Date  -- epoch-ms datetime
    Precinct       -- integer (1-5)
    Latitude       -- double
    Longitude      -- double

Method:
  1. Aggregate crime counts by precinct for the last 12 months.
  2. Aggregate crime counts by precinct for the prior 12 months.
  3. Calculate percent change -> crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate precinct centroids from average lat/lon.

Output:
  data/raw/minneapolis_crime_trends.json -- precinct crime trend records

Usage:
  python backend/ingest/minneapolis_crime_trends.py
  python backend/ingest/minneapolis_crime_trends.py --dry-run
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
    "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services"
    "/Crime_Data/FeatureServer/0"
)
QUERY_URL = f"{FEATURESERVER_URL}/query"

DEFAULT_OUTPUT_PATH = Path("data/raw/minneapolis_crime_trends.json")

DATE_FIELD = "Reported_Date"
GROUP_FIELD = "Precinct"
LAT_FIELD = "Latitude"
LON_FIELD = "Longitude"

MINNEAPOLIS_LAT = 44.9778
MINNEAPOLIS_LON = -93.2650

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """
    Fetch crime counts grouped by precinct, plus centroid coordinates.
    Returns (counts_by_precinct, centroids_by_precinct).
    """
    start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{start_str}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{end_str}' "
        f"AND {GROUP_FIELD} IS NOT NULL"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
        {"statisticType": "avg", "onStatisticField": LAT_FIELD,
         "outStatisticFieldName": "centroid_lat"},
        {"statisticType": "avg", "onStatisticField": LON_FIELD,
         "outStatisticFieldName": "centroid_lon"},
    ])

    params = {
        "where": where_clause,
        "groupByFieldsForStatistics": GROUP_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(QUERY_URL, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    counts: dict[str, int] = {}
    centroids: dict[str, tuple[float, float]] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        precinct = str(attrs.get(GROUP_FIELD) or "").strip()
        if not precinct:
            continue
        counts[precinct] = counts.get(precinct, 0) + int(attrs.get("crime_count", 0))
        try:
            lat = float(attrs.get("centroid_lat") or MINNEAPOLIS_LAT)
            lon = float(attrs.get("centroid_lon") or MINNEAPOLIS_LON)
        except (TypeError, ValueError):
            lat, lon = MINNEAPOLIS_LAT, MINNEAPOLIS_LON
        centroids[precinct] = (lat, lon)

    return counts, centroids


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
    centroids: dict[str, tuple[float, float]],
) -> list[dict]:
    all_precincts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for precinct in sorted(all_precincts):
        current_count = current_data.get(precinct, 0)
        prior_count = prior_data.get(precinct, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat, lon = centroids.get(precinct, (MINNEAPOLIS_LAT, MINNEAPOLIS_LON))
        slug = precinct.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "precinct",
            "region_id": f"minneapolis_precinct_{slug}",
            "district_id": precinct,
            "district_name": f"Minneapolis Precinct {precinct}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "minneapolis_crime_trends",
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
        description="Ingest Minneapolis MPD crime trends by precinct from ArcGIS."
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

    print(f"Fetching current 12-month Minneapolis crime counts "
          f"({current_start:%Y-%m-%d} \u2192 {now:%Y-%m-%d})...")
    try:
        current_data, centroids = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} precincts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Minneapolis crime counts "
          f"({prior_start:%Y-%m-%d} \u2192 {prior_end:%Y-%m-%d})...")
    try:
        prior_data, prior_centroids = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} precincts, {total_prior:,} total crimes.")

    for precinct, coords in prior_centroids.items():
        if precinct not in centroids:
            centroids[precinct] = coords

    records = build_trend_records(current_data, prior_data, centroids)
    print(f"\nBuilt {len(records)} precinct trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} precincts")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
