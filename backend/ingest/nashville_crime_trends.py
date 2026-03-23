"""
backend/ingest/nashville_crime_trends.py
task: data-048
lane: data

Ingests Metro Nashville Police Department crime data and calculates 12-month
crime trends by ZIP code via ArcGIS REST API.

Source:
  Metro Nashville Police Department Incidents:
  https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services
      /Metro_Nashville_Police_Department_Incidents_view/FeatureServer/0

  Verified 2026-03-23 via direct query (873k records).
  Note: data.nashville.gov (former Socrata portal) now redirects to
  ArcGIS Hub. The actual data lives on ArcGIS Online.

  Key fields:
    Incident_Number  — incident number (double)
    Incident_Occurred — epoch milliseconds
    Offense_Description — offense type
    ZIP_Code         — ZIP code (string, e.g. "37207.0")
    Zone             — police zone (NULL for recent records — deprecated)
    Latitude         — double
    Longitude        — double

  Note: The Zone field is NULL for all records after ~mid-2024. We group by
  ZIP_Code instead, which has good coverage (80+ zip codes in Nashville).

Method:
  1. Aggregate crime counts + avg lat/lon by ZIP code for the last 12 months
     via outStatistics.
  2. Aggregate crime counts + avg lat/lon by ZIP code for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/nashville_crime_trends.json — ZIP code crime trend records

Usage:
  python backend/ingest/nashville_crime_trends.py
  python backend/ingest/nashville_crime_trends.py --dry-run
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
    "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services"
    "/Metro_Nashville_Police_Department_Incidents_view/FeatureServer/0/query"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/nashville_crime_trends.json")

DATE_FIELD = "Incident_Occurred"   # epoch milliseconds
DISTRICT_FIELD = "ZIP_Code"        # ZIP code (Zone is NULL for recent data)
LAT_FIELD = "Latitude"             # double — supports avg()
LON_FIELD = "Longitude"            # double — supports avg()
COUNT_FIELD = "Incident_Number"    # used for count()

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# ArcGIS REST queries
# ---------------------------------------------------------------------------

def _timestamp_str(dt: datetime) -> str:
    """Format datetime as ArcGIS SQL TIMESTAMP literal."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_zip(raw: str | None) -> str | None:
    """Normalize ZIP code: strip '.0' suffix and whitespace."""
    if raw is None:
        return None
    z = str(raw).strip()
    if z.endswith(".0"):
        z = z[:-2]
    if not z or z.lower() in ("none", "null", ""):
        return None
    return z


def fetch_crime_counts_with_centroids(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total crime counts and average centroids per ZIP code for a date range.
    Uses ArcGIS outStatistics for server-side aggregation.
    Returns dict: zip_code → {count, lat, lon}.
    """
    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{_timestamp_str(start_date)}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{_timestamp_str(end_date)}'"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": COUNT_FIELD,
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
        zip_code = _normalize_zip(attrs.get(DISTRICT_FIELD))
        if not zip_code:
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
        results[zip_code] = {"count": count, "lat": avg_lat, "lon": avg_lon}

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
    All ZIP codes appearing in either window get a record.
    """
    all_zips = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zip_code in sorted(all_zips):
        curr = current_data.get(zip_code, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(zip_code, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "zip",
            "region_id": f"nashville_zip_{zip_code}",
            "district_id": zip_code,
            "district_name": f"Nashville ZIP {zip_code}",
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
        "source": "nashville_crime_trends",
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
        description="Ingest Nashville PD crime trends by ZIP code from ArcGIS REST API."
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

    print(f"Fetching current 12-month Nashville crime counts ({_timestamp_str(current_start)} → {_timestamp_str(now)})...")
    try:
        current_data = fetch_crime_counts_with_centroids(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} ZIP codes with current crime data.")

    print(f"\nFetching prior 12-month Nashville crime counts ({_timestamp_str(prior_start)} → {_timestamp_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} ZIP codes with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} ZIP code trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} ZIP codes")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
