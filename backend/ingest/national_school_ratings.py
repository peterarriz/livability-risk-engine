"""
backend/ingest/national_school_ratings.py
task: data-053
lane: data

Ingests public school locations for all active cities using NCES Common Core
of Data (CCD) via the Urban Institute Education Data API (free, no API key).

Source:
  https://educationdata.urban.org/api/v1/schools/ccd/directory/2022/
  Covers all US public schools with: school name, lat/lon, grades served.
  Year 2022 = School Year 2021-2022 (latest stable CCD directory release).

Method:
  1. For each active city, query the CCD directory endpoint filtered by
     city_location and fips (state FIPS code).
  2. Keep only open schools (school_status=1) with valid lat/lon.
  3. Deduplicate by ncessch (NCES school ID) across queries for cities with
     multiple NCES city_location values (e.g. NYC boroughs).
  4. Write staging file for load_neighborhood_quality.py.

Notes:
  - Chicago is excluded — CPS-specific ratings with richer attainment/growth
    fields are produced by il_school_ratings.py.
  - school_rating / school_attainment / school_growth are null for now.
    State report card API integration is tracked as data-054.
  - school_level: 1=primary, 2=middle, 3=high, 4=other

Output:
  data/raw/national_school_ratings.json

Usage:
  python backend/ingest/national_school_ratings.py
  python backend/ingest/national_school_ratings.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# School Year 2021-2022 is the latest stable NCES CCD directory release.
CCD_YEAR = 2022
CCD_BASE_URL = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{CCD_YEAR}/"

DEFAULT_OUTPUT_PATH = Path("data/raw/national_school_ratings.json")

# Seconds to wait between API requests (be a good API citizen — free tier)
REQUEST_DELAY_S = 0.5

# school_status=1 means the school is currently open / operational
SCHOOL_STATUS_OPEN = 1

# City configurations: (api_city_name, state_fips, city_slug)
# Multiple entries with the same slug are merged (used for cities with multiple
# NCES city_location values, e.g., NYC boroughs).
# Chicago is excluded — covered by il_school_ratings.py (CPS data).
CITY_CONFIGS: list[tuple[str, int, str]] = [
    ("Austin",          48,  "austin"),
    ("Seattle",         53,  "seattle"),
    # NYC boroughs have distinct city_location values in NCES
    ("New York",        36,  "nyc"),
    ("Brooklyn",        36,  "nyc"),
    ("Bronx",           36,  "nyc"),
    ("Queens",          36,  "nyc"),
    ("Staten Island",   36,  "nyc"),
    ("San Francisco",    6,  "san_francisco"),
    ("Kansas City",     29,  "kansas_city"),
    ("Denver",           8,  "denver"),
    ("Boston",          25,  "boston"),
    ("Milwaukee",       55,  "milwaukee"),
    ("Baltimore",       24,  "baltimore"),
    ("Nashville",       47,  "nashville"),
    ("Portland",        41,  "portland"),
    ("Washington",      11,  "dc"),
    ("Oklahoma City",   40,  "oklahoma_city"),
    ("San Antonio",     48,  "san_antonio"),
    ("San Diego",        6,  "san_diego"),
    ("Memphis",         47,  "memphis"),
    ("Louisville",      21,  "louisville"),
    ("Fresno",           6,  "fresno"),
    ("Sacramento",       6,  "sacramento"),
    ("Las Vegas",       32,  "las_vegas"),
    ("El Paso",         48,  "el_paso"),
    ("Tucson",           4,  "tucson"),
    ("Houston",         48,  "houston"),
    ("Charlotte",       37,  "charlotte"),
    ("Columbus",        39,  "columbus"),
    ("Minneapolis",     27,  "minneapolis"),
    ("Phoenix",          4,  "phoenix"),
    ("San Jose",         6,  "san_jose"),
    ("Jacksonville",    12,  "jacksonville"),
    ("Fort Worth",      48,  "fort_worth"),
    ("Indianapolis",    18,  "indianapolis"),
    ("Albuquerque",     35,  "albuquerque"),
    ("Raleigh",         37,  "raleigh"),
]


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_city_schools(
    city_name: str,
    fips: int,
    dry_run: bool = False,
) -> list[dict]:
    """
    Fetch CCD directory records for one city from the Urban Institute API.
    Returns a list of raw API result dicts with at least lat/lon populated.
    """
    params: dict = {
        "city_location":   city_name,
        "fips":            fips,
        "school_status":   SCHOOL_STATUS_OPEN,
        "per_page":        10000,
        "page":            1,
    }

    try:
        resp = requests.get(CCD_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  WARN: failed to fetch {city_name} (fips={fips}): {exc}", file=sys.stderr)
        return []

    try:
        data = resp.json()
    except ValueError as exc:
        print(f"  WARN: non-JSON response for {city_name}: {exc}", file=sys.stderr)
        return []

    results = data.get("results") or []

    if dry_run:
        # In dry-run mode, return only the first page (already fetched above)
        return results

    # Paginate if there are more records (unlikely for a single city but safe)
    total = data.get("count") or 0
    fetched = len(results)
    page = 2
    while fetched < total:
        params["page"] = page
        try:
            resp = requests.get(CCD_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            page_data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  WARN: pagination error at page {page} for {city_name}: {exc}", file=sys.stderr)
            break
        page_results = page_data.get("results") or []
        if not page_results:
            break
        results.extend(page_results)
        fetched = len(results)
        page += 1
        time.sleep(REQUEST_DELAY_S)

    return results


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_records(city_configs: list[tuple[str, int, str]], dry_run: bool) -> list[dict]:
    """
    Fetch and merge school records for all configured cities.
    Deduplicates by ncessch (NCES school ID).
    Returns records formatted for neighborhood_quality table.
    """
    seen: set[str] = set()
    records: list[dict] = []
    city_counts: dict[str, int] = {}

    # Track which slugs we've already processed for per-city totals
    slug_counts: dict[str, int] = {}

    for city_name, fips, slug in city_configs:
        print(f"  Fetching {city_name} (fips={fips}, slug={slug})...")
        raw = _fetch_city_schools(city_name, fips, dry_run=dry_run)
        time.sleep(REQUEST_DELAY_S)

        added = 0
        for school in raw:
            ncessch = str(school.get("ncessch") or "").strip()
            if not ncessch or ncessch in seen:
                continue

            lat_raw = school.get("latitude")
            lon_raw = school.get("longitude")
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                continue

            # Exclude implausible coordinates (0,0 or null)
            if lat == 0.0 and lon == 0.0:
                continue

            name = (school.get("school_name") or "").strip() or f"School {ncessch}"

            seen.add(ncessch)
            added += 1

            records.append({
                "region_type":       "school",
                "region_id":         f"nces_{ncessch}",
                "school_name":       name,
                # Ratings are null — state report card integration in data-054
                "school_rating":     None,
                "school_attainment": None,
                "school_growth":     None,
                "latitude":          lat,
                "longitude":         lon,
                # Metadata (not stored in DB but useful for debugging)
                "_city_slug":        slug,
                "_state_fips":       fips,
                "_school_level":     school.get("school_level"),
                "_grade_low":        school.get("grade_low"),
                "_grade_high":       school.get("grade_high"),
            })

        slug_counts[slug] = slug_counts.get(slug, 0) + added
        city_counts[city_name] = added
        print(f"    → {added} new records (total for {slug}: {slug_counts[slug]})")

        if dry_run:
            # In dry-run mode stop after a handful of cities to keep it fast
            non_zero = sum(1 for v in city_counts.values() if v > 0)
            if non_zero >= 3:
                print("  [dry-run] sampled 3 cities — stopping early.")
                break

    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    # Strip internal metadata fields before writing
    clean = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in records
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source":       "national_school_ratings",
        "source_url":   CCD_BASE_URL,
        "ccd_year":     CCD_YEAR,
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(clean),
        "records":      clean,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(clean)} records to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest public school locations for all active cities from the "
            "NCES Common Core of Data via the Urban Institute Education Data API."
        )
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
        help="Fetch data for a sample of cities but do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Fetching NCES CCD school directory data (year={CCD_YEAR})...")
    print(f"Source: {CCD_BASE_URL}")
    print(f"Cities configured: {len(CITY_CONFIGS)} query entries")
    if args.dry_run:
        print("[dry-run] Will sample first 3 cities only.")

    records = build_records(CITY_CONFIGS, dry_run=args.dry_run)

    print(f"\nTotal school records built: {len(records)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            sample = {k: v for k, v in records[0].items() if not k.startswith("_")}
            print(f"Sample record:\n{json.dumps(sample, indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
