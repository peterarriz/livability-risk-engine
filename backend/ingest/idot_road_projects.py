"""
backend/ingest/idot_road_projects.py
task: data-014
lane: data

Ingests IDOT Road Construction data from the ArcGIS REST API and writes
raw records to a local JSON staging file.

Source:
  https://gis-idot.opendata.arcgis.com/datasets/IDOT::road-construction
  ArcGIS FeatureServer:
    https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/Road_Construction_Public/FeatureServer/2

Usage:
  python backend/ingest/idot_road_projects.py
  python backend/ingest/idot_road_projects.py --output data/raw/idot_road_projects.json
  python backend/ingest/idot_road_projects.py --district 1 --dry-run

Notes:
  - The ArcGIS API is public; no authentication is required.
  - District 1 corresponds to the Chicago metro area.
  - Date fields are returned as epoch milliseconds and converted to ISO 8601.

Acceptance criteria (data-014):
  - Records are fetched from the ArcGIS FeatureServer (not Socrata).
  - Fields are normalized to internal names used by the rest of the pipeline.
  - Polyline geometry is preserved for future PostGIS loading.
  - Script is idempotent: re-running overwrites the output file cleanly.

Notes for next agent:
  This dataset is live/active construction only (small record count, ~10-20).
  For planned/upcoming projects, consider also ingesting the Annual Highway
  Improvement Program at FeatureServer layer 2 under
  Annual_Highway_Improvement_Program service.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARCGIS_BASE_URL = (
    "https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services"
    "/Road_Construction_Public/FeatureServer/2/query"
)

# Mapping from ArcGIS field names to internal field names used by the
# rest of the pipeline (load_projects, normalize, scoring).
ARCGIS_TO_INTERNAL = {
    "OBJECTID":              "row_id",
    "ContractNumber":        "contract_number",
    "Contractor":            "contractor",
    "ContractValue":         "contract_value",
    "District":              "district",
    "County":                "county",
    "NearTown":              "near_town",
    "Route":                 "route",
    "ConstructionType":      "construction_type",
    "StartDate":             "start_date",
    "EndDate":               "end_date",
    "Location":              "location",
    "LanesRampsClosed":      "lanes_ramps_closed",
    "DetourRoute":           "detour_route",
    "ImpactOnTravel":        "impact_on_travel",
    "Status":                "status",
    "PermanentRestriction":  "permanent_restriction",
    "MaxWidth_In":           "max_width_in",
    "MaxHeight_In":          "max_height_in",
    "MaxLength_In":          "max_length_in",
    "MaxWeight":             "max_weight",
}

# ArcGIS returns dates as epoch milliseconds — these fields need conversion.
EPOCH_MS_FIELDS = {"StartDate", "EndDate"}

PAGE_SIZE = 1000
DEFAULT_OUTPUT_PATH = "data/raw/idot_road_projects.json"


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def build_params(offset: int, limit: int, district: str | None) -> dict:
    """Build ArcGIS REST API query params for one page of results."""
    where = f"District='{district}'" if district else "1=1"

    return {
        "where": where,
        "outFields": "*",
        "outSR": "4326",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": limit,
    }


def fetch_page(
    session: requests.Session,
    offset: int,
    limit: int,
    district: str | None,
) -> tuple[list[dict], bool]:
    """
    Fetch one page of road construction records from the ArcGIS FeatureServer.

    Returns (features, exceeded_transfer_limit).
    """
    params = build_params(offset, limit, district)

    try:
        response = session.get(ARCGIS_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"  ERROR: Request timed out at offset {offset}.", file=sys.stderr)
        raise
    except requests.exceptions.HTTPError as exc:
        print(
            f"  ERROR: HTTP {exc.response.status_code} at offset {offset}: "
            f"{exc.response.text[:200]}",
            file=sys.stderr,
        )
        raise

    data = response.json()

    if "error" in data:
        err = data["error"]
        print(
            f"  ERROR: ArcGIS error {err.get('code')}: {err.get('message')}",
            file=sys.stderr,
        )
        raise RuntimeError(f"ArcGIS API error: {err}")

    features = data.get("features", [])
    exceeded = data.get("exceededTransferLimit", False)

    return features, exceeded


def fetch_all_projects(district: str | None, dry_run: bool) -> list[dict]:
    """
    Paginate through the ArcGIS API and return all raw road construction
    features (attributes + geometry).
    """
    session = requests.Session()
    all_features: list[dict] = []
    offset = 0

    district_label = f"District {district}" if district else "all districts"
    print(f"Fetching IDOT road construction projects ({district_label})...")

    while True:
        print(f"  Fetching page at offset {offset}...", end=" ", flush=True)
        features, exceeded = fetch_page(session, offset, PAGE_SIZE, district)
        print(f"{len(features)} features.")

        if not features:
            break

        all_features.extend(features)
        offset += len(features)

        if dry_run:
            print("  Dry-run: stopping after first page.")
            break

        if not exceeded:
            break

    return all_features


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def epoch_ms_to_iso(value: int | None) -> str | None:
    """Convert an epoch-millisecond timestamp to an ISO 8601 string."""
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def normalize_feature(feature: dict) -> dict:
    """
    Convert an ArcGIS feature into a normalized internal record.

    - Remaps field names via ARCGIS_TO_INTERNAL.
    - Converts epoch-ms dates to ISO 8601.
    - Extracts centroid lat/lng from polyline geometry for geocoding fallback.
    - Preserves full geometry paths for future PostGIS loading.
    """
    attrs = feature.get("attributes", {})
    geometry = feature.get("geometry", {})

    record: dict = {}

    for arcgis_key, internal_key in ARCGIS_TO_INTERNAL.items():
        value = attrs.get(arcgis_key)
        if arcgis_key in EPOCH_MS_FIELDS and isinstance(value, (int, float)):
            value = epoch_ms_to_iso(int(value))
        record[internal_key] = value

    # Extract centroid from polyline paths for simple lat/lng geocoding.
    paths = geometry.get("paths", [])
    if paths:
        all_points = [pt for path in paths for pt in path]
        if all_points:
            avg_lng = sum(p[0] for p in all_points) / len(all_points)
            avg_lat = sum(p[1] for p in all_points) / len(all_points)
            record["longitude"] = round(avg_lng, 6)
            record["latitude"] = round(avg_lat, 6)

    # Preserve raw geometry for PostGIS.
    record["geometry_paths"] = paths

    record["source"] = "idot_road_construction"

    return record


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write normalized road construction records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source": "idot_road_construction",
        "source_url": ARCGIS_BASE_URL.replace("/query", ""),
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest IDOT road construction data from the ArcGIS REST API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_PATH),
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--district",
        type=str,
        default=None,
        help="Filter to a specific IDOT district (e.g. 1 for Chicago). Default: all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page only; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    features = fetch_all_projects(args.district, args.dry_run)
    records = [normalize_feature(f) for f in features]

    print(f"\nTotal records fetched: {len(records)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
