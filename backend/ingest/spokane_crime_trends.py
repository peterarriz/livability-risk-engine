"""
backend/ingest/spokane_crime_trends.py
task: data-058
lane: data

Ingests Spokane Police Department (SPD) crime data and calculates
12-month crime trends by precinct/sector.

Source:
  Socrata — data.spokanecity.org (City of Spokane Open Data)
  Dataset: SPD Crime Incidents (MUST VERIFY dataset ID)
  Verify: curl "https://data.spokanecity.org/api/catalog/v1?q=crime&limit=10"
  Sample: curl "https://data.spokanecity.org/resource/{DATASET_ID}.json?$limit=1"

  Key fields (MUST VERIFY field names via --dry-run):
    reported_date or crime_date — date of incident
    precinct or sector          — geographic grouping
    latitude, longitude         — incident coordinates

Output:
  data/raw/spokane_crime_trends.json

Usage:
  python backend/ingest/spokane_crime_trends.py
  python backend/ingest/spokane_crime_trends.py --dry-run
  python backend/ingest/spokane_crime_trends.py --discover

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_DOMAIN = "data.spokanecity.org"
# MUST VERIFY dataset ID via: curl "https://data.spokanecity.org/api/catalog/v1?q=crime&limit=10"
DATASET_ID = "4gj6-ujfi"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/spokane_crime_trends.json")

# MUST VERIFY field names by running: python ... --dry-run
DATE_FIELD = "reported_date"  # MUST VERIFY — may be "crime_date" or "date_reported"
DISTRICT_FIELD = "precinct"   # MUST VERIFY — may be "sector" or "reporting_area"
LAT_FIELD = "latitude"
LON_FIELD = "longitude"

SPOKANE_LAT = 47.6587
SPOKANE_LON = -117.4260

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts_with_centroids(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count, "
            f"avg({LAT_FIELD} :: number) as avg_lat, "
            f"avg({LON_FIELD} :: number) as avg_lon"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 200,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"Socrata query error: {rows}")

    results: dict[str, dict] = {}
    for row in rows:
        district = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not district:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        try:
            avg_lat = float(row.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(row.get("avg_lon") or 0) or None
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
        slug = district.lower().replace(" ", "_")
        records.append({
            "region_type": "precinct",
            "region_id": f"spokane_precinct_{slug}",
            "district_id": district,
            "district_name": f"Spokane Precinct {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or SPOKANE_LAT,
            "longitude": lon or SPOKANE_LON,
        })
    return records


def discover_datasets() -> None:
    """Search Spokane Socrata portal for crime datasets."""
    url = f"https://{SOCRATA_DOMAIN}/api/catalog/v1"
    for q in ["crime", "police incident", "SPD"]:
        resp = requests.get(url, params={"q": q, "limit": 5}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"\nQuery: {q!r}")
        for r in data.get("results", []):
            meta = r.get("resource", {})
            print(f"  {meta.get('id')} — {meta.get('name')}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "spokane_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Spokane SPD crime trends by precinct from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="Search data.spokanecity.org for crime datasets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if args.discover:
        discover_datasets()
        return

    print(f"NOTE: DATASET_ID={DATASET_ID!r} MUST VERIFY. Run --discover to find the correct ID.")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Spokane crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts_with_centroids(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} precincts with current crime data.")

    print(f"\nFetching prior 12-month Spokane crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(app_token, prior_start, prior_end)
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
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
