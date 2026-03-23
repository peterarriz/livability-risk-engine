"""
backend/ingest/charlotte_crime_trends.py
task: data-050
lane: data

Ingests Charlotte-Mecklenburg Police Department (CMPD) crime data and
calculates 12-month crime trends by division.

Source:
  Socrata — data.charlottenc.gov
  Dataset: CMPD Incident Report
  Dataset ID: cdym-9n4y (MUST VERIFY — run discover to confirm)

  Verify dataset ID:
    curl "https://data.charlottenc.gov/api/catalog/v1?q=cmpd+incident&limit=5"
    curl "https://data.charlottenc.gov/resource/cdym-9n4y.json?$limit=1"

  Key fields:
    globalid          — unique incident ID
    date_reported     — ISO 8601 datetime string
    division          — CMPD division (EASTWAY, NORTH, SOUTH, etc.)
    latitude, longitude — coordinates

Method:
  1. Aggregate crime counts by division for the last 12 months.
  2. Aggregate crime counts by division for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate division centroids from average lat/lon of incidents.

Output:
  data/raw/charlotte_crime_trends.json — division crime trend records

Usage:
  python backend/ingest/charlotte_crime_trends.py
  python backend/ingest/charlotte_crime_trends.py --dry-run

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

SOCRATA_DOMAIN = "data.charlottenc.gov"
# MUST VERIFY: run the following to confirm the correct dataset ID:
#   curl "https://data.charlottenc.gov/api/catalog/v1?q=cmpd+incident&limit=5"
DATASET_ID = "cdym-9n4y"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/charlotte_crime_trends.json")

# Date field and group field in the CMPD Incident Reports dataset.
# MUST VERIFY field names:
#   curl "https://data.charlottenc.gov/resource/cdym-9n4y.json?$limit=1"
DATE_FIELD = "date_reported"
GROUP_FIELD = "division"

CHARLOTTE_LAT = 35.2271
CHARLOTTE_LON = -80.8431

STABLE_THRESHOLD_PCT = 5.0
PAGE_SIZE = 50000


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """
    Fetch crime counts grouped by division, plus centroid coordinates.
    Returns (counts_by_division, centroids_by_division).
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
        division = str(row.get(GROUP_FIELD) or "").strip().upper()
        if not division:
            continue
        counts[division] = counts.get(division, 0) + int(row.get("crime_count", 0))
        try:
            lat = float(row.get("centroid_lat") or CHARLOTTE_LAT)
            lon = float(row.get("centroid_lon") or CHARLOTTE_LON)
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
        description="Ingest CMPD crime trends by division from Socrata."
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
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data, centroids = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} divisions, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Charlotte crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data, prior_centroids = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} divisions, {total_prior:,} total crimes.")

    # Prefer current-period centroids; fall back to prior
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
