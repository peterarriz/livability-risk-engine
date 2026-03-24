"""
backend/ingest/madison_crime_trends.py
task: data-058
lane: data

Ingests Madison Police Department (MPD) crime data and calculates
12-month crime trends by incident type.

Source:
  ArcGIS Hub — data-cityofmadison.opendata.arcgis.com
  Dataset: Police Incident Reports (ArcGIS item 61c36ee8e2d14cd094a265a288e27151)
  Service: MapServer layer 2 on maps.cityofmadison.com (OPEN_DB_TABLES)
  Download: GeoJSON bulk download via opendata.arcgis.com

  Note: This dataset contains selected incidents only (those chosen by the
        Officer In Charge for public interest). Records have no geometry
        (lat/lon) and no sector/district field, so trends are grouped by
        IncidentType and use the city centroid for coordinates.

  Key fields:
    IncidentDate  — ISO-8601 date string (e.g. "2023-04-02T18:08:00Z")
    IncidentType  — category of incident (e.g. "Robbery", "Battery")

Output:
  data/raw/madison_crime_trends.json

Usage:
  python backend/ingest/madison_crime_trends.py
  python backend/ingest/madison_crime_trends.py --dry-run
  python backend/ingest/madison_crime_trends.py --discover
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

GEOJSON_URL = (
    "https://opendata.arcgis.com/api/v3/datasets/"
    "61c36ee8e2d14cd094a265a288e27151_2/downloads/data"
    "?format=geojson&spatialRefId=4326"
)

SERVICE_URL = (
    "https://maps.cityofmadison.com/arcgis/rest/services"
    "/Public/OPEN_DB_TABLES/MapServer/2"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/madison_crime_trends.json")

DATE_FIELD = "IncidentDate"
GROUP_FIELD = "IncidentType"

MADISON_LAT = 43.0731
MADISON_LON = -89.4012

STABLE_THRESHOLD_PCT = 5.0


def _parse_date(date_str: str) -> datetime | None:
    """Parse ISO-8601 date string from the GeoJSON download."""
    if not date_str:
        return None
    try:
        # Handle "2023-04-02T18:08:00Z" format
        return datetime.strptime(date_str.strip(), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _fetch_all_features() -> list[dict]:
    """Download the full GeoJSON dataset from ArcGIS Hub."""
    print(f"  Downloading GeoJSON from ArcGIS Hub...")
    resp = requests.get(GEOJSON_URL, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, dict) or "features" not in data:
        raise RuntimeError(f"Unexpected GeoJSON response: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    return data["features"]


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    all_features: list[dict],
) -> dict[str, int]:
    """Filter pre-fetched GeoJSON features by date range and count by incident type."""
    results: dict[str, int] = {}
    for feature in all_features:
        props = feature.get("properties", {})
        date_val = _parse_date(str(props.get(DATE_FIELD) or ""))
        if date_val is None:
            continue
        if not (start_date <= date_val < end_date):
            continue
        group = str(props.get(GROUP_FIELD) or "").strip()
        if not group:
            continue
        results[group] = results.get(group, 0) + 1
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
    period_label: str = "12mo",
) -> list[dict]:
    all_groups = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for group in sorted(all_groups):
        current_count = current_data.get(group, 0)
        prior_count = prior_data.get(group, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = group.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "incident_type",
            "region_id": f"madison_type_{slug}",
            "district_id": group,
            "district_name": group,
            f"crime_{period_label}": current_count,
            f"crime_prior_{period_label}": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": MADISON_LAT,
            "longitude": MADISON_LON,
        })
    return records


def discover_datasets() -> None:
    """Print field names and date range from a sample of the dataset."""
    print("Fetching Police Incident Reports from ArcGIS Hub...")
    features = _fetch_all_features()
    print(f"  Total features: {len(features)}")

    if not features:
        print("  No features found.")
        return

    # Show field names from first record
    props = features[0].get("properties", {})
    print(f"\n  Fields: {list(props.keys())}")

    # Date range
    dates = []
    types: set[str] = set()
    for f in features:
        p = f.get("properties", {})
        d = _parse_date(str(p.get(DATE_FIELD) or ""))
        if d:
            dates.append(d)
        t = p.get(GROUP_FIELD, "")
        if t:
            types.add(t)

    dates.sort()
    if dates:
        print(f"  Date range: {dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d}")
    print(f"\n  Incident types ({len(types)}):")
    for t in sorted(types):
        print(f"    {t}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "madison_crime_trends",
        "source_url": SERVICE_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Madison MPD crime trends by incident type from ArcGIS Hub."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="Show available fields and incident types.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover_datasets()
        return

    print("Fetching all Madison Police Incident Reports from ArcGIS Hub...")
    try:
        all_features = _fetch_all_features()
    except Exception as exc:
        print(f"ERROR: failed to fetch records — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  Retrieved {len(all_features):,} total records.")

    # Determine the latest date in the dataset to anchor our windows
    dates = []
    for f in all_features:
        d = _parse_date(str(f.get("properties", {}).get(DATE_FIELD) or ""))
        if d:
            dates.append(d)
    if not dates:
        print("ERROR: no valid dates found in data.", file=sys.stderr)
        sys.exit(1)

    latest = max(dates)
    print(f"  Latest incident date: {latest:%Y-%m-%d}")

    # Use 12-month windows anchored to the latest date in the dataset
    current_end = latest + timedelta(days=1)
    current_start = current_end - timedelta(days=365)
    prior_start = current_start - timedelta(days=365)
    prior_end = current_start

    print(f"\nCounting current 12-month crimes ({current_start:%Y-%m-%d} -> {current_end:%Y-%m-%d})...")
    current_data = fetch_crime_counts(current_start, current_end, all_features)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} incident types, {total_current:,} total incidents.")

    print(f"\nCounting prior 12-month crimes ({prior_start:%Y-%m-%d} -> {prior_end:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(prior_start, prior_end, all_features)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} incident types, {total_prior:,} total incidents.")

    records = build_trend_records(current_data, prior_data, period_label="12mo")
    print(f"\nBuilt {len(records)} incident-type trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} types")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
