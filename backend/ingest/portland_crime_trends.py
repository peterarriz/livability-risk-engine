"""
backend/ingest/portland_crime_trends.py
task: data-047
lane: data

Ingests Portland Police Bureau crime data and calculates 12-month crime trends
by precinct.

Source:
  Portland Police Bureau publishes crime data via ArcGIS FeatureServer.
  Service: Portland Maps Open Data — PPB Crime Incidents
  URL: https://services.arcgis.com/quVN97tn06YNGj9s/arcgis/rest/services
       /CrimeData/FeatureServer/0

  IMPORTANT: Verify this URL before first production run.
  To discover the correct service URL, search Portland's open data hub:
    https://hub.arcgis.com/api/v3/datasets?q=crime+portland&page[size]=10
  Or visit:
    https://opendata.portland.gov  (or https://portlandoregon.gov/police/60082)

  Key fields (verify with --dry-run):
    CaseNumber       — unique incident ID
    OccurDate        — epoch milliseconds
    OffenseType      — crime category
    Neighborhood     — neighborhood name
    PrecinctsCity    — precinct code (N, NE, NW, SE, SW, etc.)
    OpenDataLat, OpenDataLon — coordinates

Method:
  1. Query crime counts + avg lat/lon by precinct for the last 12 months.
  2. Query crime counts + avg lat/lon by precinct for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/portland_crime_trends.json — precinct crime trend records

Usage:
  python backend/ingest/portland_crime_trends.py
  python backend/ingest/portland_crime_trends.py --dry-run
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

ARCGIS_BASE_URL = (
    "https://services.arcgis.com/quVN97tn06YNGj9s/arcgis/rest/services"
    "/CrimeData/FeatureServer/0/query"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/portland_crime_trends.json")

# ArcGIS field names — verify with:
#   curl "<ARCGIS_BASE_URL>?where=1%3D1&outFields=*&resultRecordCount=1&f=json"
DATE_FIELD = "OccurDate"        # epoch milliseconds
DISTRICT_FIELD = "PrecinctsCity"
LAT_FIELD = "OpenDataLat"
LON_FIELD = "OpenDataLon"

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# ArcGIS REST queries
# ---------------------------------------------------------------------------

def _timestamp_str(dt: datetime) -> str:
    """Format datetime as ArcGIS SQL TIMESTAMP literal."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fetch_crime_counts_with_centroids(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total crime counts and approximate centroids per precinct for a date range.

    Uses ArcGIS outStatistics for server-side aggregation by PrecinctsCity.
    Returns dict: precinct → {count, lat, lon}.
    """
    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{_timestamp_str(start_date)}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{_timestamp_str(end_date)}'"
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

    resp = requests.get(ARCGIS_BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS query error: {data['error']}")

    results: dict[str, dict] = {}
    for feature in data.get("features", []):
        attrs = feature["attributes"]
        precinct = str(attrs.get(DISTRICT_FIELD) or "").strip().upper()
        if not precinct:
            continue
        count = int(attrs.get("crime_count", 0))
        try:
            avg_lat = float(attrs.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(attrs.get("avg_lon") or 0) or None
        except (TypeError, ValueError):
            avg_lon = None
        results[precinct] = {"count": count, "lat": avg_lat, "lon": avg_lon}

    return results


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_trend_records(
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    All precincts appearing in either window get a record.
    """
    all_precincts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for precinct in sorted(all_precincts):
        curr = current_data.get(precinct, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(precinct, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "precinct",
            "region_id": f"portland_precinct_{precinct.lower().replace(' ', '_')}",
            "district_id": precinct,
            "district_name": f"Portland Precinct {precinct}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat,
            "longitude": lon,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "portland_crime_trends",
        "source_url": ARCGIS_BASE_URL.replace("/query", ""),
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Portland PPB crime trends by precinct from ArcGIS REST API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Portland crime counts ({_timestamp_str(current_start)} → {_timestamp_str(now)})...")
    try:
        current_data = fetch_crime_counts_with_centroids(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} precincts with current crime data.")

    print(f"\nFetching prior 12-month Portland crime counts ({_timestamp_str(prior_start)} → {_timestamp_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} precincts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} precinct trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} precincts")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
