"""
backend/ingest/scottsdale_crime_trends.py
task: data-058
lane: data

Ingests Scottsdale Police Department (SPD) crime data and calculates
crime trends by district.

Source:
  Scottsdale Open Data — Police Incident Reports
  Portal: https://data-cos-gis.hub.arcgis.com/datasets/police-incident-reports
  Service: MapServer layer 4 on maps.scottsdaleaz.gov
  Note: Only one rolling year of data is available. The script splits
        that year into two 6-month halves to compute a trend.

  Key fields:
    DateOccurred  — date of incident (string, MM/DD/YYYY)
    District      — two-letter district code (e.g. MK, FH)

Output:
  data/raw/scottsdale_crime_trends.json

Usage:
  python backend/ingest/scottsdale_crime_trends.py
  python backend/ingest/scottsdale_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SERVICE_URL = (
    "https://maps.scottsdaleaz.gov/arcgis/rest/services"
    "/OpenData_Tabular/MapServer/4"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/scottsdale_crime_trends.json")

DATE_FIELD = "DateOccurred"
GROUP_FIELD = "District"

SCOTTSDALE_LAT = 33.4942
SCOTTSDALE_LON = -111.9261

STABLE_THRESHOLD_PCT = 5.0

MAX_RECORD_COUNT = 1000


def _fetch_all_records() -> list[dict]:
    """Paginate through the MapServer to retrieve all records."""
    url = f"{SERVICE_URL}/query"
    all_features: list[dict] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": f"{DATE_FIELD},{GROUP_FIELD}",
            "resultOffset": str(offset),
            "resultRecordCount": str(MAX_RECORD_COUNT),
            "f": "json",
        }
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()

        if "error" in payload:
            raise RuntimeError(f"ArcGIS query error: {payload['error']}")

        features = payload.get("features", [])
        if not features:
            break

        all_features.extend(features)
        offset += len(features)

        # If fewer than requested, we've reached the end
        if len(features) < MAX_RECORD_COUNT:
            break

    return all_features


def _parse_date(date_str: str) -> datetime | None:
    """Parse MM/DD/YYYY date string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    all_records: list[dict],
) -> dict[str, int]:
    """Filter pre-fetched records by date range and count by district."""
    results: dict[str, int] = {}
    for feature in all_records:
        attrs = feature.get("attributes", {})
        date_val = _parse_date(str(attrs.get(DATE_FIELD) or ""))
        if date_val is None:
            continue
        if not (start_date <= date_val < end_date):
            continue
        district = str(attrs.get(GROUP_FIELD) or "").strip()
        if not district:
            continue
        results[district] = results.get(district, 0) + 1
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
        slug = district.lower().replace(" ", "_")
        records.append({
            "region_type": "district",
            "region_id": f"scottsdale_district_{slug}",
            "district_id": district,
            "district_name": f"District {district}",
            "crime_6mo": current_count,
            "crime_prior_6mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": SCOTTSDALE_LAT,
            "longitude": SCOTTSDALE_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "scottsdale_crime_trends",
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
        description="Ingest Scottsdale SPD crime trends by district from ArcGIS FeatureServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Scottsdale only publishes one rolling year of data, so we split
    # it into two 6-month halves to compute a trend direction.
    now = datetime.now()  # naive, matching parsed dates
    midpoint = now - timedelta(days=182)
    year_ago = now - timedelta(days=365)

    print(f"Fetching all Scottsdale police incident records...")
    try:
        all_records = _fetch_all_records()
    except Exception as exc:
        print(f"ERROR: failed to fetch records — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  Retrieved {len(all_records):,} total records.")

    print(f"\nCounting recent 6-month crimes ({midpoint:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data = fetch_crime_counts(midpoint, now, all_records)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nCounting prior 6-month crimes ({year_ago:%Y-%m-%d} → {midpoint:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(year_ago, midpoint, all_records)
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
