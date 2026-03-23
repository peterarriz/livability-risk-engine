"""
backend/ingest/chicago_crime_trends.py
task: data-040
lane: data

Ingests Chicago crime data and calculates 12-month crime trends by community area.

Source:
  https://data.cityofchicago.org/resource/31yy-ehbz.json
  Dataset: Crimes — 2001 to Present (Chicago Police Department)

Method:
  1. Aggregate crime counts by community area for the last 12 months (current window).
  2. Aggregate crime counts by community area for the prior 12 months (baseline).
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Fetch community area centroids from the Chicago Data Portal for spatial lookup.

Output:
  data/raw/chicago_crime_trends.json — community area crime trend records

Usage:
  python backend/ingest/chicago_crime_trends.py
  python backend/ingest/chicago_crime_trends.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — increases Socrata API rate limits
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

CRIMES_URL = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
COMMUNITY_AREAS_URL = "https://data.cityofchicago.org/resource/igwz-8jzy.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_crime_trends.json")

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Community area geometry helpers
# ---------------------------------------------------------------------------

def _polygon_centroid(geom: dict) -> tuple[float, float] | None:
    """
    Compute approximate centroid from a GeoJSON Polygon or MultiPolygon.
    Returns (lat, lon) or None.
    """
    geom_type = (geom or {}).get("type", "")
    coords = (geom or {}).get("coordinates", [])
    if not coords:
        return None

    try:
        if geom_type == "MultiPolygon":
            ring = coords[0][0]  # first polygon, outer ring
        elif geom_type == "Polygon":
            ring = coords[0]
        else:
            return None

        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        lon = sum(xs) / len(xs)
        lat = sum(ys) / len(ys)
        return lat, lon
    except (IndexError, TypeError, ZeroDivisionError):
        return None


def fetch_community_areas(app_token: str | None) -> dict[str, dict]:
    """
    Fetch Chicago community area boundaries and compute approximate centroids.
    Returns a dict keyed by area_numbe (string) → {community_area, community_name, lat, lon}.
    """
    print("Fetching Chicago community area boundaries...")
    params: dict = {"$limit": 100}
    if app_token:
        params["$$app_token"] = app_token

    try:
        resp = requests.get(COMMUNITY_AREAS_URL, params=params, timeout=30)
        resp.raise_for_status()
        areas = resp.json()
    except Exception as exc:
        print(f"  WARN: could not fetch community area boundaries: {exc}", file=sys.stderr)
        return {}

    centroids: dict[str, dict] = {}
    for area in areas:
        area_num = str(area.get("area_numbe", "") or "").strip()
        name = area.get("community", "")
        geom = area.get("the_geom")
        if not area_num:
            continue

        centroid = _polygon_centroid(geom) if geom else None
        centroids[area_num] = {
            "community_area": area_num,
            "community_name": name,
            "latitude": centroid[0] if centroid else None,
            "longitude": centroid[1] if centroid else None,
        }

    print(f"  Fetched centroids for {len(centroids)} community areas.")
    return centroids


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """
    Fetch total crime counts per community area for a date range via SoQL GROUP BY.
    Returns a dict: community_area_num → count.
    """
    where_clause = (
        f"date >= '{_date_str(start_date)}' AND date < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": "community_area, count(*) as crime_count",
        "$where": where_clause,
        "$group": "community_area",
        "$limit": 200,  # 77 community areas; headroom for null/other values
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    counts: dict[str, int] = {}
    for row in rows:
        area = str(row.get("community_area", "") or "").strip()
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        if area:
            counts[area] = count

    return counts


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def _classify_trend(current: int, prior: int) -> tuple[str, float]:
    """
    Classify crime trend given current and prior 12-month counts.
    Returns (trend_label, pct_change).
    """
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
    area_centroids: dict[str, dict],
    counts_current: dict[str, int],
    counts_prior: dict[str, int],
) -> list[dict]:
    """
    Merge crime counts with community area centroids to produce trend records.
    Every community area with a centroid gets a record, even if crime count is 0.
    """
    records = []
    for area_num, area_info in area_centroids.items():
        current = counts_current.get(area_num, 0)
        prior = counts_prior.get(area_num, 0)
        trend, trend_pct = _classify_trend(current, prior)
        records.append({
            "region_type": "community_area",
            "region_id": f"chicago_ca_{area_num}",
            "community_area": area_num,
            "community_name": area_info["community_name"],
            "crime_12mo": current,
            "crime_prior_12mo": prior,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": area_info["latitude"],
            "longitude": area_info["longitude"],
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "chicago_crime_trends",
        "source_url": CRIMES_URL,
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
        description="Ingest Chicago crime trends by community area from the Socrata API."
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
    app_token = os.environ.get("CHICAGO_SOCRATA_APP_TOKEN")

    if not app_token:
        print(
            "Note: CHICAGO_SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register free at https://data.cityofchicago.org/profile/app_tokens"
        )

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    try:
        area_centroids = fetch_community_areas(app_token)
    except Exception as exc:
        print(f"ERROR: failed to fetch community areas — {exc}", file=sys.stderr)
        sys.exit(1)

    if not area_centroids:
        print("ERROR: no community area centroids fetched — cannot build records.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFetching current 12-month crime counts ({_date_str(current_start)} → {_date_str(now)})...")
    try:
        counts_current = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(counts_current)} community areas with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        counts_prior = fetch_crime_counts(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(counts_prior)} community areas with prior crime data.")

    records = build_trend_records(area_centroids, counts_current, counts_prior)
    print(f"\nBuilt {len(records)} community area trend records.")

    # Show trend summary
    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} community areas")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
