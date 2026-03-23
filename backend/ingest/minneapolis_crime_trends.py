"""
backend/ingest/minneapolis_crime_trends.py
task: data-050
lane: data

Ingests Minneapolis Police Department (MPD) crime data and calculates
12-month crime trends by precinct.

Source:
  Socrata — opendata.minneapolismn.gov (ArcGIS Hub with Socrata-compat layer)
  OR Minneapolis Open Data: data.minneapolismn.gov (Socrata)

  Dataset: Minneapolis Police Department Incidents
  Dataset ID: k65s-ce4x (MUST VERIFY — run discover to confirm)

  Verify dataset ID:
    curl "https://opendata.ci.minneapolis.mn.us/api/catalog/v1?q=police+incident&limit=5"
    # Alternative domain: data.minneapolismn.gov
    curl "https://data.minneapolismn.gov/api/catalog/v1?q=police+incident&limit=5"
    curl "https://data.minneapolismn.gov/resource/k65s-ce4x.json?$limit=1"

  Key fields (MUST VERIFY via sample query):
    reporteddate  — date of incident report
    precinct      — police precinct (1-5)
    latitude, longitude — coordinates

Method:
  1. Aggregate crime counts by precinct for the last 12 months.
  2. Aggregate crime counts by precinct for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate precinct centroids from average lat/lon.

Output:
  data/raw/minneapolis_crime_trends.json — precinct crime trend records

Usage:
  python backend/ingest/minneapolis_crime_trends.py
  python backend/ingest/minneapolis_crime_trends.py --dry-run

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

# MUST VERIFY: try both domains and dataset IDs below
# Primary: data.minneapolismn.gov (classic Socrata portal)
# Dataset: Minneapolis Police Department Crime Data
# Verify: curl "https://data.minneapolismn.gov/api/catalog/v1?q=crime+incident&limit=5"
SOCRATA_DOMAIN = "data.minneapolismn.gov"
DATASET_ID = "k65s-ce4x"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/minneapolis_crime_trends.json")

# MUST VERIFY field names via sample query:
#   curl "https://data.minneapolismn.gov/resource/k65s-ce4x.json?$limit=1"
DATE_FIELD = "reporteddate"
GROUP_FIELD = "precinct"

MINNEAPOLIS_LAT = 44.9778
MINNEAPOLIS_LON = -93.2650

STABLE_THRESHOLD_PCT = 5.0
PAGE_SIZE = 50000


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """
    Fetch crime counts grouped by precinct, plus centroid coordinates.
    Returns (counts_by_precinct, centroids_by_precinct).
    """
    app_token = os.environ.get("SOCRATA_APP_TOKEN", "")
    headers = {"X-App-Token": app_token} if app_token else {}

    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")

    select_clause = (
        f"count(*) as crime_count,"
        f" avg(latitude) as centroid_lat,"
        f" avg(longitude) as centroid_lon,"
        f" {GROUP_FIELD}"
    )

    params = {
        "$select": select_clause,
        "$where": (
            f"{DATE_FIELD} >= '{start_str}' "
            f"AND {DATE_FIELD} < '{end_str}' "
            f"AND {GROUP_FIELD} IS NOT NULL"
        ),
        "$group": GROUP_FIELD,
        "$limit": PAGE_SIZE,
    }

    resp = requests.get(CRIMES_URL, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    counts: dict[str, int] = {}
    centroids: dict[str, tuple[float, float]] = {}
    for row in rows:
        precinct = str(row.get(GROUP_FIELD) or "").strip()
        if not precinct:
            continue
        counts[precinct] = counts.get(precinct, 0) + int(row.get("crime_count", 0))
        try:
            lat = float(row.get("centroid_lat") or MINNEAPOLIS_LAT)
            lon = float(row.get("centroid_lon") or MINNEAPOLIS_LON)
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
        description="Ingest Minneapolis MPD crime trends by precinct from Socrata."
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
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data, centroids = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} precincts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Minneapolis crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data, prior_centroids = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
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
