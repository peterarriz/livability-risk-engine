"""
backend/ingest/census_acs.py
task: data-052
lane: data

Ingests Census ACS 5-year demographic data for ALL US census tracts
nationally (~85,000 tracts across 52 states/territories).
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

Coverage: all 50 US states + DC + Puerto Rico (52 state FIPS codes).
Fetched state-by-state — each ACS call returns all tracts in one state.

Output:
  data/raw/census_acs.json — census tract demographic records with centroids

Usage:
  python backend/ingest/census_acs.py
  python backend/ingest/census_acs.py --dry-run
  python backend/ingest/census_acs.py --states IL,CA,TX   # test subset
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

# All 52 US states + DC + PR by FIPS code.
# Census ACS API accepts state FIPS; we query for=tract:* in=state:XX.
ALL_STATES: list[tuple[str, str]] = [
    ("01", "Alabama"), ("02", "Alaska"), ("04", "Arizona"), ("05", "Arkansas"),
    ("06", "California"), ("08", "Colorado"), ("09", "Connecticut"), ("10", "Delaware"),
    ("11", "District of Columbia"), ("12", "Florida"), ("13", "Georgia"), ("15", "Hawaii"),
    ("16", "Idaho"), ("17", "Illinois"), ("18", "Indiana"), ("19", "Iowa"),
    ("20", "Kansas"), ("21", "Kentucky"), ("22", "Louisiana"), ("23", "Maine"),
    ("24", "Maryland"), ("25", "Massachusetts"), ("26", "Michigan"), ("27", "Minnesota"),
    ("28", "Mississippi"), ("29", "Missouri"), ("30", "Montana"), ("31", "Nebraska"),
    ("32", "Nevada"), ("33", "New Hampshire"), ("34", "New Jersey"), ("35", "New Mexico"),
    ("36", "New York"), ("37", "North Carolina"), ("38", "North Dakota"), ("39", "Ohio"),
    ("40", "Oklahoma"), ("41", "Oregon"), ("42", "Pennsylvania"), ("44", "Rhode Island"),
    ("45", "South Carolina"), ("46", "South Dakota"), ("47", "Tennessee"), ("48", "Texas"),
    ("49", "Utah"), ("50", "Vermont"), ("51", "Virginia"), ("53", "Washington"),
    ("54", "West Virginia"), ("55", "Wisconsin"), ("56", "Wyoming"),
    ("72", "Puerto Rico"),
]

# Abbreviation → FIPS lookup for --states filter
_STATE_ABBREV_TO_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72",
}

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
# ACS data fetch — single county
# ---------------------------------------------------------------------------

def fetch_acs_data_for_state(
    state_fips: str,
    label: str,
    dry_run: bool,
) -> dict[str, dict]:
    """
    Fetch Census ACS variables for all census tracts in one state.
    Returns a dict: tract_fips (str) → {variable_name: value, ...}
    """
    var_list = ",".join(ACS_VARS.keys())
    params = {
        "get": var_list,
        "for": "tract:*",
        "in": f"state:{state_fips}",
    }

    try:
        resp = requests.get(ACS_API_URL, params=params, timeout=120)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        print(f"  WARN: ACS fetch failed for {label}: {exc}", file=sys.stderr)
        return {}

    if not rows or len(rows) < 2:
        print(f"  WARN: Census ACS API returned no data rows for {label}.", file=sys.stderr)
        return {}

    headers = rows[0]
    data_rows = rows[1:]

    if dry_run:
        data_rows = data_rows[:5]

    result: dict[str, dict] = {}
    for row in data_rows:
        row_dict = dict(zip(headers, row))
        county_fips = str(row_dict.get("county", "") or "").strip().zfill(3)
        tract_num = str(row_dict.get("tract", "") or "").strip().zfill(6)
        if not tract_num or not county_fips:
            continue

        tract_fips = f"{state_fips}{county_fips}{tract_num}"

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

    return result


def fetch_acs_data(states: list[tuple[str, str]], dry_run: bool) -> dict[str, dict]:
    """
    Fetch Census ACS variables for all census tracts in the given states.
    Returns a combined dict: tract_fips (str) → {variable_name: value, ...}
    """
    print(f"Fetching Census ACS 5-year data for {len(states)} states...")
    combined: dict[str, dict] = {}
    for i, (state_fips, label) in enumerate(states, 1):
        print(f"  [{i}/{len(states)}] {label} (FIPS {state_fips})...", end=" ", flush=True)
        state_data = fetch_acs_data_for_state(state_fips, label, dry_run)
        combined.update(state_data)
        print(f"{len(state_data)} tracts.")

    print(f"  Total ACS tracts fetched: {len(combined)}")
    return combined


# ---------------------------------------------------------------------------
# TIGER tract centroid fetch — single county
# ---------------------------------------------------------------------------

def fetch_tract_centroids_for_state(
    state_fips: str,
    label: str,
) -> dict[str, tuple[float, float]]:
    """
    Fetch internal point (centroid) lat/lon for all census tracts in one state
    from the Census TIGER web services (layer 8 = Census Tracts).
    Returns a dict: tract_fips → (lat, lon)
    """
    centroids: dict[str, tuple[float, float]] = {}
    offset = 0

    while True:
        params = {
            "where": f"STATE='{state_fips}'",
            "outFields": "STATE,COUNTY,TRACT,INTPTLAT,INTPTLON",
            "returnGeometry": "false",
            "resultRecordCount": TIGER_PAGE_SIZE,
            "resultOffset": offset,
            "f": "json",
        }

        try:
            resp = requests.get(TIGER_TRACTS_URL, params=params, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            print(f"\n    WARN: TIGER API failed for {label} at offset {offset}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        if "error" in data:
            err = data["error"]
            print(f"\n    WARN: TIGER error for {label}: {err.get('message', err)}", file=sys.stderr)
            break

        features = data.get("features", [])

        for feat in features:
            attrs = feat.get("attributes", {})
            county_fips = str(attrs.get("COUNTY") or "").strip().zfill(3)
            tract_num = str(attrs.get("TRACT") or "").strip().zfill(6)
            lat_raw = attrs.get("INTPTLAT")
            lon_raw = attrs.get("INTPTLON")
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                continue

            tract_fips = f"{state_fips}{county_fips}{tract_num}"
            centroids[tract_fips] = (lat, lon)

        offset += len(features)
        if len(features) < TIGER_PAGE_SIZE:
            break
        if not data.get("exceededTransferLimit", False):
            break

    return centroids


def fetch_tract_centroids(states: list[tuple[str, str]]) -> dict[str, tuple[float, float]]:
    """
    Fetch internal point (centroid) lat/lon for all tracts in the given states.
    Returns a combined dict: tract_fips → (lat, lon)
    """
    print(f"Fetching census tract centroids for {len(states)} states from TIGER...")
    combined: dict[str, tuple[float, float]] = {}
    for i, (state_fips, label) in enumerate(states, 1):
        print(f"  [{i}/{len(states)}] {label}...", end=" ", flush=True)
        state_centroids = fetch_tract_centroids_for_state(state_fips, label)
        print(f"{len(state_centroids)} tracts.")
        combined.update(state_centroids)

    print(f"  Total centroids fetched: {len(combined)}")
    return combined


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
        description=(
            "Ingest Census ACS 5-year demographics for all US census tracts "
            "nationally (~85,000 tracts across 52 states/territories)."
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
        help="Fetch limited data (5 tracts per state); do not write output file.",
    )
    parser.add_argument(
        "--states",
        type=str,
        default=None,
        help="Comma-separated state abbreviations to fetch (e.g. IL,CA,TX). Default: all 52.",
    )
    return parser.parse_args()


def _resolve_states(states_arg: str | None) -> list[tuple[str, str]]:
    """Resolve --states filter to a list of (fips, label) tuples."""
    if not states_arg:
        return ALL_STATES

    abbrevs = [s.strip().upper() for s in states_arg.split(",") if s.strip()]
    result = []
    for abbr in abbrevs:
        fips = _STATE_ABBREV_TO_FIPS.get(abbr)
        if fips:
            label = next((l for f, l in ALL_STATES if f == fips), abbr)
            result.append((fips, label))
        else:
            print(f"  WARN: unknown state abbreviation '{abbr}', skipping.", file=sys.stderr)
    return result


def main() -> None:
    args = parse_args()
    states = _resolve_states(args.states)

    if not states:
        print("ERROR: no valid states to fetch.", file=sys.stderr)
        sys.exit(1)

    print(f"Census ACS national ingest — {len(states)} states")

    try:
        acs_data = fetch_acs_data(states, args.dry_run)
    except Exception as exc:
        print(f"ERROR: Census ACS fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    if not acs_data:
        print("ERROR: no ACS data returned — check API availability.", file=sys.stderr)
        sys.exit(1)

    try:
        centroids = fetch_tract_centroids(states)
    except Exception as exc:
        print(
            f"WARN: TIGER centroid fetch failed — {exc}. Records will have no geom.",
            file=sys.stderr,
        )
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
