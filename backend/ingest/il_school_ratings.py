"""
backend/ingest/il_school_ratings.py
task: data-045
lane: data

Ingests Chicago Public Schools performance ratings with lat/lon coordinates.

Sources:
  https://data.cityofchicago.org/resource/twrw-chuq.json
  Dataset: CPS School Progress Reports SY2425
  (student attainment, growth, culture-climate, creative school certification)

  https://data.cityofchicago.org/resource/cu4u-b4d9.json
  Dataset: CPS School Profile Information SY2324
  (school lat/lon, primary category, enrollment)

Method:
  1. Fetch all progress report records (SY2425) for current performance data.
  2. Fetch all school profile records (SY2324) for lat/lon coordinates.
  3. Join on school_id to produce records with both ratings and locations.
  4. Write staging file for load_neighborhood_quality.py.

Output:
  data/raw/il_school_ratings.json -- school performance records

Usage:
  python backend/ingest/il_school_ratings.py
  python backend/ingest/il_school_ratings.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  -- increases Socrata API rate limits
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# SY2425 progress reports: current attainment, growth, climate ratings
PROGRESS_URL = "https://data.cityofchicago.org/resource/twrw-chuq.json"

# SY2324 profile: school lat/lon coordinates and metadata
PROFILE_URL = "https://data.cityofchicago.org/resource/cu4u-b4d9.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/il_school_ratings.json")

# Fields we pull from the progress report dataset
PROGRESS_FIELDS = (
    "school_id,"
    "short_name,"
    "student_attainment_rating,"
    "student_growth_rating,"
    "culture_climate_rating,"
    "creative_school_certification,"
    "student_attendance_avg_pct,"
    "school_survey_safety"
)

# Fields we pull from the profile dataset
PROFILE_FIELDS = (
    "school_id,"
    "short_name,"
    "long_name,"
    "school_latitude,"
    "school_longitude,"
    "primary_category"
)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_all(url: str, select: str, app_token: str | None, limit: int = 0) -> list[dict]:
    """Paginated Socrata fetch. If limit > 0, cap results at that count."""
    page_size = 1000
    offset = 0
    results: list[dict] = []
    while True:
        params: dict = {
            "$select": select,
            "$limit": page_size,
            "$offset": offset,
        }
        if app_token:
            params["$$app_token"] = app_token

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        results.extend(page)
        if limit and len(results) >= limit:
            return results[:limit]
        if len(page) < page_size:
            break
        offset += page_size
    return results


def fetch_progress_reports(app_token: str | None, limit: int = 0) -> dict[str, dict]:
    """
    Fetch SY2425 progress reports. Returns dict keyed by school_id.
    """
    print("Fetching CPS School Progress Reports (SY2425)...")
    rows = _fetch_all(PROGRESS_URL, PROGRESS_FIELDS, app_token, limit=limit)
    result: dict[str, dict] = {}
    for row in rows:
        sid = str(row.get("school_id", "")).strip()
        if sid:
            result[sid] = row
    print(f"  Fetched progress reports for {len(result)} schools.")
    return result


def fetch_school_profiles(app_token: str | None, limit: int = 0) -> dict[str, dict]:
    """
    Fetch SY2324 school profiles for lat/lon coordinates.
    Returns dict keyed by school_id.
    """
    print("Fetching CPS School Profiles (SY2324) for coordinates...")
    rows = _fetch_all(PROFILE_URL, PROFILE_FIELDS, app_token, limit=limit)
    result: dict[str, dict] = {}
    for row in rows:
        sid = str(row.get("school_id", "")).strip()
        lat = row.get("school_latitude")
        lon = row.get("school_longitude")
        if sid and lat and lon:
            result[sid] = row
    print(f"  Fetched profiles with coordinates for {len(result)} schools.")
    return result


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_records(
    progress: dict[str, dict],
    profiles: dict[str, dict],
) -> list[dict]:
    """
    Join progress reports with profile coordinates to produce school rating records.
    Only schools with both ratings and coordinates are included.
    """
    records: list[dict] = []
    joined = 0
    for school_id, report in progress.items():
        profile = profiles.get(school_id)
        if not profile:
            continue
        joined += 1

        try:
            lat = float(profile["school_latitude"])
            lon = float(profile["school_longitude"])
        except (TypeError, ValueError, KeyError):
            continue

        # Use creative_school_certification as the overall composite rating.
        # Falls back to attainment rating if certification is absent.
        overall = (
            report.get("creative_school_certification")
            or report.get("student_attainment_rating")
        )

        name = (
            profile.get("long_name")
            or profile.get("short_name")
            or report.get("short_name")
            or f"School {school_id}"
        )

        records.append({
            "region_type": "school",
            "region_id": f"cps_{school_id}",
            "school_name": name,
            "school_rating": overall,
            "school_attainment": report.get("student_attainment_rating"),
            "school_growth": report.get("student_growth_rating"),
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
        "source": "il_school_ratings",
        "source_url": PROGRESS_URL,
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
        description="Ingest CPS school ratings from the Chicago Data Portal Socrata API."
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

    limit = 10 if args.dry_run else 0

    try:
        progress = fetch_progress_reports(app_token, limit=limit)
    except Exception as exc:
        print(f"ERROR: failed to fetch progress reports -- {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        profiles = fetch_school_profiles(app_token, limit=limit)
    except Exception as exc:
        print(f"ERROR: failed to fetch school profiles -- {exc}", file=sys.stderr)
        sys.exit(1)

    if not progress:
        print("ERROR: no progress reports fetched.", file=sys.stderr)
        sys.exit(1)

    records = build_records(progress, profiles)
    print(f"\nBuilt {len(records)} school rating records.")

    # Show rating distribution
    rating_counts: dict[str, int] = {}
    for r in records:
        rt = r.get("school_rating") or "UNKNOWN"
        rating_counts[rt] = rating_counts.get(rt, 0) + 1
    for rating, count in sorted(rating_counts.items()):
        print(f"  {rating}: {count} schools")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
