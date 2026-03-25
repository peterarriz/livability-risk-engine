"""
backend/ingest/gilbert_crime_trends.py
task: data-058, data-059, data-066
lane: data

Ingests Gilbert Police Department (GPD) crime data and calculates
12-month crime trends by district.

Source:
  ArcGIS FeatureServer — Gilbert AZ Open Data
  Portal: https://data.gilbertaz.gov
  Service: GPD_Crime_Incidents FeatureServer/0 (ENDPOINT BLOCKED — see below)

  Key fields:
    IncidentDate — date of incident (MUST VERIFY)
    District     — geographic grouping (MUST VERIFY)

BLOCKED (data-066, 2026-03-25):
  Org ID K1VMQDQNLVxLvLqs is confirmed INVALID (returns HTTP 400 "Invalid URL").
  FEATURESERVER_URL below is a placeholder that will not work.

  To fix:
    1. Visit https://data.gilbertaz.gov
    2. Search for "Police Incidents" or "Crime" dataset
    3. Click "I want to use this" → "API" to get the FeatureServer URL
    4. Extract the org ID (alphanumeric segment after services.arcgis.com/)
    5. Update FEATURESERVER_URL below
    6. Verify DATE_FIELD and GROUP_FIELD match actual layer fields
    7. Re-run: python backend/ingest/gilbert_crime_trends.py --dry-run
    8. Update SKILL.md ArcGIS-Based table row for Gilbert AZ
    9. Update us_city_permits_arcgis.py gilbert service_url with same org ID

  Helper: python backend/ingest/verify_arcgis_endpoints.py --city gilbert --discover

Output:
  data/raw/gilbert_crime_trends.json

Usage:
  python backend/ingest/gilbert_crime_trends.py
  python backend/ingest/gilbert_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

FEATURESERVER_URL = (
    "https://services.arcgis.com/K1VMQDQNLVxLvLqs/ArcGIS/rest/services"
    "/GPD_Crime_Incidents/FeatureServer/0"  # INVALID — org ID K1VMQDQNLVxLvLqs returns 400; see docstring
)

DEFAULT_OUTPUT_PATH = Path("data/raw/gilbert_crime_trends.json")

DATE_FIELD = "IncidentDate"  # MUST VERIFY — endpoint is blocked; verify after org ID is fixed
GROUP_FIELD = "District"  # MUST VERIFY — endpoint is blocked; verify after org ID is fixed

GILBERT_LAT = 33.3528
GILBERT_LON = -111.7890

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
        if not district:
            continue
        count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
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
        slug = district.lower().replace(" ", "_")
        records.append({
            "region_type": "district",
            "region_id": f"gilbert_district_{slug}",
            "district_id": district,
            "district_name": f"Gilbert {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": GILBERT_LAT,
            "longitude": GILBERT_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "gilbert_crime_trends",
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
        description="Ingest Gilbert GPD crime trends by district from ArcGIS FeatureServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Source: {FEATURESERVER_URL}")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Gilbert crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Gilbert crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
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
