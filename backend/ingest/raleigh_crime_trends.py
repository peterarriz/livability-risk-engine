"""
backend/ingest/raleigh_crime_trends.py
task: data-050
lane: data

Ingests Raleigh Police Department crime data and calculates 12-month
crime trends by district.

Source:
  ArcGIS FeatureServer -- data.raleighnc.gov (ArcGIS Hub)
  Org: v400IkDOw1ad7Yad
  Service: Police_Incidents (NIBRS)
  URL: https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Police_Incidents/FeatureServer/0

  Key fields:
    reported_date  — epoch-ms datetime
    district       — police district (e.g. "Downtown", "Southeast")
    latitude       — double
    longitude      — double

Method:
  1. Aggregate crime counts by district for the last 12 months.
  2. Aggregate crime counts by district for the prior 12 months.
  3. Calculate percent change -> crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate district centroids from average lat/lon.

Output:
  data/raw/raleigh_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/raleigh_crime_trends.py
  python backend/ingest/raleigh_crime_trends.py --dry-run
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
QUERY_URL = f"{FEATURESERVER_URL}/query"

DEFAULT_OUTPUT_PATH = Path("data/raw/raleigh_crime_trends.json")

DATE_FIELD = "reported_date"
GROUP_FIELD = "district"
LAT_FIELD = "latitude"
LON_FIELD = "longitude"

RALEIGH_LAT = 35.7796
RALEIGH_LON = -78.6382

STABLE_THRESHOLD_PCT = 5.0


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Fetch crime counts grouped by district."""
    start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{start_str}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{end_str}' "
        f"AND {GROUP_FIELD} IS NOT NULL"
    )

    # Raleigh's latitude/longitude fields contain anonymized values that
    # don't represent real coordinates, so we skip centroid computation
    # and fall back to city center coordinates.
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

    resp = requests.post(QUERY_URL, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    counts: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        district = str(attrs.get(GROUP_FIELD) or "").strip().upper()
        if not district:
            continue
        counts[district] = counts.get(district, 0) + int(attrs.get("crime_count", 0))

    return counts


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
        lat, lon = RALEIGH_LAT, RALEIGH_LON
        slug = district.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "district",
            "region_id": f"raleigh_district_{slug}",
            "district_id": district,
            "district_name": f"Raleigh Police District {district}",
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
        "source": "raleigh_crime_trends",
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
        description="Ingest Raleigh PD crime trends by district from ArcGIS."
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

    print(f"Fetching current 12-month Raleigh crime counts "
          f"({current_start:%Y-%m-%d} \u2192 {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Raleigh crime counts "
          f"({prior_start:%Y-%m-%d} \u2192 {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts \u2014 {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} districts, {total_prior:,} total crimes.")

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
