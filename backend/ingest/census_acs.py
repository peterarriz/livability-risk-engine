"""
backend/ingest/census_acs.py
task: data-040
lane: data

Ingests Census ACS 5-year demographic data for Cook County, IL census tracts.
No API key required for basic Census Bureau queries.

Sources:
  Census ACS 5-year API (2022 vintage):
    https://api.census.gov/data/2022/acs/acs5
  Census TIGER Web Services (tract centroids):
    https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/8/query

Variables fetched:
  B19013_001E  Median household income (dollars)
  B01003_001E  Total population
  B25002_001E  Total housing units
  B25002_003E  Vacant housing units  (→ vacancy_rate computed from these two)
  B25035_001E  Median year structure built

Output:
  data/raw/census_acs.json — census tract demographic records with centroids

Usage:
  python backend/ingest/census_acs.py
  python backend/ingest/census_acs.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACS_API_URL = "https://api.census.gov/data/2022/acs/acs5"
TIGER_TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "tigerWMS_Current/MapServer/8/query"
)

# Illinois FIPS: 17, Cook County FIPS: 031
STATE_FIPS = "17"
COUNTY_FIPS = "031"

# Census ACS variables: code → field name in output record
ACS_VARS = {
    "B19013_001E": "median_income",
    "B01003_001E": "population",
    "B25002_001E": "total_housing_units",
    "B25002_003E": "vacant_housing_units",
    "B25035_001E": "housing_age_med",
}

# Census Bureau sentinel value for suppressed/unreliable estimates
CENSUS_NULL = -666666666

TIGER_PAGE_SIZE = 1000
DEFAULT_OUTPUT_PATH = Path("data/raw/census_acs.json")


# ---------------------------------------------------------------------------
# ACS data fetch
# ---------------------------------------------------------------------------

def fetch_acs_data(dry_run: bool) -> dict[str, dict]:
    """
    Fetch Census ACS variables for all Cook County census tracts.
    Returns a dict: tract_fips (str) → {variable_name: value, ...}
    """
    print(
        f"Fetching Census ACS 5-year data for Cook County, IL "
        f"(state={STATE_FIPS}, county={COUNTY_FIPS})..."
    )

    var_list = ",".join(ACS_VARS.keys())
    params = {
        "get": var_list,
        "for": "tract:*",
        "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS}",
    }

    resp = requests.get(ACS_API_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    if not rows or len(rows) < 2:
        print("  WARN: Census ACS API returned no data rows.", file=sys.stderr)
        return {}

    headers = rows[0]
    data_rows = rows[1:]

    if dry_run:
        data_rows = data_rows[:10]
        print(f"  Dry-run: limiting to {len(data_rows)} tracts.")

    result: dict[str, dict] = {}
    for row in data_rows:
        row_dict = dict(zip(headers, row))
        tract_num = str(row_dict.get("tract", "") or "").strip().zfill(6)
        if not tract_num:
            continue

        tract_fips = f"{STATE_FIPS}{COUNTY_FIPS}{tract_num}"

        record: dict = {}
        for code, name in ACS_VARS.items():
            raw = row_dict.get(code)
            if raw is None:
                record[name] = None
            else:
                try:
                    val = int(raw)
                    record[name] = None if val == CENSUS_NULL else val
                except (ValueError, TypeError):
                    record[name] = None

        # Derive vacancy_rate from total and vacant housing units
        total = record.get("total_housing_units")
        vacant = record.get("vacant_housing_units")
        if total and total > 0 and vacant is not None:
            record["vacancy_rate"] = round(vacant / total * 100, 2)
        else:
            record["vacancy_rate"] = None

        record["tract_fips"] = tract_fips
        record["tract_num"] = tract_num
        result[tract_fips] = record

    print(f"  Fetched ACS data for {len(result)} census tracts.")
    return result


# ---------------------------------------------------------------------------
# TIGER tract centroid fetch
# ---------------------------------------------------------------------------

def fetch_tract_centroids() -> dict[str, tuple[float, float]]:
    """
    Fetch internal point (centroid) lat/lon for Cook County census tracts
    from the Census TIGER web services (layer 8 = Census Tracts).
    Returns a dict: tract_fips → (lat, lon)
    """
    print("Fetching census tract centroids from Census TIGER web service...")
    centroids: dict[str, tuple[float, float]] = {}
    offset = 0

    while True:
        params = {
            "where": f"STATEFP='{STATE_FIPS}' AND COUNTYFP='{COUNTY_FIPS}'",
            "outFields": "TRACT,INTPTLAT,INTPTLON",
            "returnGeometry": "false",
            "resultRecordCount": TIGER_PAGE_SIZE,
            "resultOffset": offset,
            "f": "json",
        }

        print(f"  Fetching tract centroids at offset {offset}...", end=" ", flush=True)
        try:
            resp = requests.get(TIGER_TRACTS_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"\n  WARN: TIGER API request failed: {exc}", file=sys.stderr)
            break

        data = resp.json()
        if "error" in data:
            err = data["error"]
            print(f"\n  WARN: TIGER API error: {err.get('message', err)}", file=sys.stderr)
            break

        features = data.get("features", [])
        print(f"{len(features)} tracts.")

        for feat in features:
            attrs = feat.get("attributes", {})
            # TIGER uses INTPTLAT / INTPTLON (internal point)
            tract_num = str(attrs.get("TRACT") or "").strip().zfill(6)
            lat_raw = attrs.get("INTPTLAT")
            lon_raw = attrs.get("INTPTLON")
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                continue

            tract_fips = f"{STATE_FIPS}{COUNTY_FIPS}{tract_num}"
            centroids[tract_fips] = (lat, lon)

        offset += len(features)
        if len(features) < TIGER_PAGE_SIZE:
            break
        if not data.get("exceededTransferLimit", False):
            break

    print(f"  Fetched centroids for {len(centroids)} census tracts.")
    return centroids


# ---------------------------------------------------------------------------
# Build output records
# ---------------------------------------------------------------------------

def build_records(
    acs_data: dict[str, dict],
    centroids: dict[str, tuple[float, float]],
) -> list[dict]:
    """Merge ACS data with tract centroids into neighborhood_quality records."""
    records = []
    for tract_fips, acs in acs_data.items():
        centroid = centroids.get(tract_fips)
        lat = centroid[0] if centroid else None
        lon = centroid[1] if centroid else None

        records.append({
            "region_type": "census_tract",
            "region_id": f"tract_{tract_fips}",
            "tract_fips": tract_fips,
            "median_income": acs.get("median_income"),
            "population": acs.get("population"),
            "vacancy_rate": acs.get("vacancy_rate"),
            "housing_age_med": acs.get("housing_age_med"),
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
        "source": "census_acs",
        "source_url": ACS_API_URL,
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
        description="Ingest Census ACS 5-year demographics for Cook County census tracts."
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
        help="Fetch limited data; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        acs_data = fetch_acs_data(args.dry_run)
    except Exception as exc:
        print(f"ERROR: Census ACS fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    if not acs_data:
        print("ERROR: no ACS data returned — check API availability.", file=sys.stderr)
        sys.exit(1)

    try:
        centroids = fetch_tract_centroids()
    except Exception as exc:
        print(f"WARN: TIGER centroid fetch failed — {exc}. Records will have no geom.", file=sys.stderr)
        centroids = {}

    records = build_records(acs_data, centroids)
    with_geom = sum(1 for r in records if r["latitude"] is not None)
    print(f"\nBuilt {len(records)} census tract records ({with_geom} with coordinates).")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
