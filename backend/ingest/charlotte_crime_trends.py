"""
backend/ingest/charlotte_crime_trends.py
task: data-050
lane: data

Ingests Charlotte-Mecklenburg Police Department (CMPD) crime data and
calculates 12-month crime trends by patrol division.

Source:
  ArcGIS MapServer — gis.charlottenc.gov
  Service: CMPD Incidents
  URL: https://gis.charlottenc.gov/arcgis/rest/services/CMPD/CMPDIncidents/MapServer/0

  Key fields:
    DATE_REPORTED          — epoch-ms datetime
    CMPD_PATROL_DIVISION   — patrol division name (e.g. "Steele Creek", "Metro")
    LATITUDE_PUBLIC        — latitude
    LONGITUDE_PUBLIC       — longitude

Method:
  1. Aggregate crime counts by division for the last 12 months.
  2. Aggregate crime counts by division for the prior 12 months.
  3. Calculate percent change -> crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate division centroids from average lat/lon of incidents.

Output:
  data/raw/charlotte_crime_trends.json — division crime trend records

Usage:
  python backend/ingest/charlotte_crime_trends.py
  python backend/ingest/charlotte_crime_trends.py --dry-run
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

QUERY_URL = (
    "https://gis.charlottenc.gov/arcgis/rest/services/CMPD"
    "/CMPDIncidents/MapServer/0/query"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/charlotte_crime_trends.json")

DATE_FIELD = "DATE_REPORTED"
GROUP_FIELD = "CMPD_PATROL_DIVISION"
LAT_FIELD = "LATITUDE_PUBLIC"
LON_FIELD = "LONGITUDE_PUBLIC"

CHARLOTTE_LAT = 35.2271
CHARLOTTE_LON = -80.8431

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """
    Fetch crime counts grouped by division, plus centroid coordinates.
    Returns (counts_by_division, centroids_by_division).
    """
    start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{start_str}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{end_str}'"
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
        division = str(attrs.get(GROUP_FIELD) or "").strip()
        if not division:
            continue
        counts[division] = counts.get(division, 0) + int(attrs.get("crime_count", 0))
        try:
            lat = float(attrs.get("centroid_lat") or CHARLOTTE_LAT)
            lon = float(attrs.get("centroid_lon") or CHARLOTTE_LON)
        except (TypeError, ValueError):
            lat, lon = CHARLOTTE_LAT, CHARLOTTE_LON
        centroids[division] = (lat, lon)

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
    all_divisions = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for division in sorted(all_divisions):
        current_count = current_data.get(division, 0)
        prior_count = prior_data.get(division, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat, lon = centroids.get(division, (CHARLOTTE_LAT, CHARLOTTE_LON))
        slug = division.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "division",
            "region_id": f"charlotte_division_{slug}",
            "district_id": division,
            "district_name": f"Charlotte CMPD {division.title()} Division",
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
        "source": "charlotte_crime_trends",
        "source_url": QUERY_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest CMPD crime trends by division from ArcGIS."
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

    print(f"Fetching current 12-month Charlotte crime counts "
          f"({current_start:%Y-%m-%d} \u2192 {now:%Y-%m-%d})...")
    try:
        current_data, centroids = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} divisions, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Charlotte crime counts "
          f"({prior_start:%Y-%m-%d} \u2192 {prior_end:%Y-%m-%d})...")
    try:
        prior_data, prior_centroids = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} divisions, {total_prior:,} total crimes.")

    for division, coords in prior_centroids.items():
        if division not in centroids:
            centroids[division] = coords

    records = build_trend_records(current_data, prior_data, centroids)
    print(f"\nBuilt {len(records)} division trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} divisions")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
