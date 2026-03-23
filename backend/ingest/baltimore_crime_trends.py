"""
backend/ingest/baltimore_crime_trends.py
task: data-048
lane: data

Ingests Baltimore Police Department crime data and calculates 12-month
crime trends by district via ArcGIS REST API.

Source:
  NIBRS Group A Crime Data (2022-present):
  https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services
      /NIBRS_GroupA_Crime_Data/FeatureServer/0

  Verified 2026-03-23 via direct query (242k records).
  Note: data.baltimorecity.gov (former Socrata portal) now redirects to
  ArcGIS Hub. The actual data lives on ArcGIS Online.

  Key fields:
    CCNumber       — case number (string)
    CrimeDateTime  — epoch milliseconds
    Description    — offense type
    New_District   — police district (CENTRAL, EASTERN, etc.)
    Latitude       — string (not numeric — avg() not supported in outStatistics)
    Longitude      — string

Method:
  1. Aggregate crime counts by district for the last 12 months via outStatistics.
  2. Aggregate crime counts by district for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Use well-known Baltimore district centroids (Latitude/Longitude are strings
     so server-side avg() is not possible).

Output:
  data/raw/baltimore_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/baltimore_crime_trends.py
  python backend/ingest/baltimore_crime_trends.py --dry-run
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
    "https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services"
    "/NIBRS_GroupA_Crime_Data/FeatureServer/0/query"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/baltimore_crime_trends.json")

DATE_FIELD = "CrimeDateTime"      # epoch milliseconds
DISTRICT_FIELD = "New_District"
COUNT_FIELD = "CCNumber"           # used for count() — OBJECTID doesn't exist

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0

# Well-known Baltimore police district centroids (approximate).
# Latitude/Longitude fields on this dataset are strings, so server-side
# avg() via outStatistics is not supported.
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "CENTRAL":   (39.2904, -76.6122),
    "EASTERN":   (39.2989, -76.5840),
    "NORTHEAST": (39.3226, -76.5779),
    "NORTHERN":  (39.3380, -76.6250),
    "NORTHWEST": (39.3162, -76.6590),
    "SOUTHEAST": (39.2750, -76.5710),
    "SOUTHERN":  (39.2650, -76.6200),
    "SOUTHWEST": (39.2830, -76.6530),
    "WESTERN":   (39.3060, -76.6450),
}


# ---------------------------------------------------------------------------
# ArcGIS REST queries
# ---------------------------------------------------------------------------

def _timestamp_str(dt: datetime) -> str:
    """Format datetime as ArcGIS SQL TIMESTAMP literal."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """
    Fetch total crime counts per district for a date range via outStatistics.
    Returns dict: district → count.
    """
    where_clause = (
        f"{DATE_FIELD} >= TIMESTAMP '{_timestamp_str(start_date)}' "
        f"AND {DATE_FIELD} < TIMESTAMP '{_timestamp_str(end_date)}'"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": COUNT_FIELD,
         "outStatisticFieldName": "crime_count"},
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

    results: dict[str, int] = {}
    for feature in data.get("features", []):
        attrs = feature["attributes"]
        district = str(attrs.get(DISTRICT_FIELD) or "").strip().upper()
        if not district or district in ("", "N/A"):
            continue
        results[district] = int(attrs.get("crime_count", 0))

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
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    All districts appearing in either window get a record.
    """
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        centroid = DISTRICT_CENTROIDS.get(district)
        lat = centroid[0] if centroid else None
        lon = centroid[1] if centroid else None
        records.append({
            "region_type": "district",
            "region_id": f"baltimore_district_{district.lower().replace(' ', '_')}",
            "district_id": district,
            "district_name": f"Baltimore District {district.title()}",
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
        "source": "baltimore_crime_trends",
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
        description="Ingest BPD crime trends by district from ArcGIS REST API."
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

    print(f"Fetching current 12-month Baltimore crime counts ({_timestamp_str(current_start)} → {_timestamp_str(now)})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} districts with current crime data.")

    print(f"\nFetching prior 12-month Baltimore crime counts ({_timestamp_str(prior_start)} → {_timestamp_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} districts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
