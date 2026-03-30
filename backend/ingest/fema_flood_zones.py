"""
backend/ingest/fema_flood_zones.py
task: data-040
lane: data

Ingests FEMA National Flood Hazard Layer (NFHL) flood zone polygon centroids
for the Chicago metropolitan area (Cook County, IL).

Source:
  FEMA NFHL ArcGIS REST Service — S_Fld_Haz_Ar layer (Layer 28)
  https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query

Flood zone risk classification:
  HIGH:     A, AE, AH, AO, AR, A99, V, VE  (1% annual chance — Special Flood Hazard Areas)
  MODERATE: X500                            (0.2% annual chance / 500-year flood)
  MINIMAL:  X                               (minimal flood hazard)
  UNKNOWN:  D                               (possible but undetermined)

Output:
  data/raw/fema_flood_zones.json — polygon centroids with flood zone designations

Usage:
  python backend/ingest/fema_flood_zones.py
  python backend/ingest/fema_flood_zones.py --dry-run
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

FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)

# County bounding boxes (WGS84: xmin, ymin, xmax, ymax).
# Each bbox is small enough that the FEMA API returns <1000 features,
# or gets sub-tiled into quadrants if it exceeds the limit.
COUNTY_BBOXES: list[tuple[str, tuple[float, float, float, float]]] = [
    ("Cook County, IL",          (-88.26, 41.47, -87.52, 42.16)),
    ("LA County, CA",            (-118.95, 33.70, -117.65, 34.82)),
    ("King County, WA",          (-122.54, 47.07, -121.06, 47.78)),
    ("Travis County, TX",        (-98.17, 30.07, -97.37, 30.63)),
    ("Suffolk County, MA",       (-71.19, 42.23, -70.92, 42.40)),
    ("Franklin County, OH",      (-83.21, 39.86, -82.76, 40.17)),
    ("Maricopa County, AZ",      (-113.33, 33.18, -111.04, 34.05)),
    ("Davidson County, TN",      (-86.97, 36.01, -86.52, 36.41)),
    ("Baltimore City, MD",       (-76.72, 39.20, -76.53, 39.37)),
    ("Mecklenburg County, NC",   (-81.01, 35.01, -80.56, 35.51)),
    ("Hennepin County, MN",      (-93.77, 44.79, -93.18, 45.25)),
    ("SF County, CA",            (-122.52, 37.71, -122.36, 37.83)),
    ("New York County, NY",      (-74.03, 40.68, -73.91, 40.88)),
    ("Kings County, NY",         (-74.06, 40.57, -73.83, 40.74)),
    ("Clark County, NV",         (-115.90, 35.00, -114.63, 36.85)),
    ("Pima County, AZ",          (-112.32, 31.33, -110.45, 32.51)),
    ("Denver County, CO",        (-105.11, 39.61, -104.60, 39.91)),
    ("Wake County, NC",          (-78.97, 35.52, -78.25, 36.07)),
    ("Duval County, FL",         (-81.83, 30.10, -81.31, 30.59)),
    ("Tarrant County, TX",       (-97.55, 32.55, -97.03, 32.99)),
    ("Marion County, IN",        (-86.33, 39.63, -85.94, 39.93)),
    ("Bernalillo County, NM",    (-106.88, 34.95, -106.41, 35.22)),
    ("Jackson County, MO",       (-94.61, 38.84, -94.11, 39.14)),
    ("Milwaukee County, WI",     (-88.07, 42.84, -87.83, 43.20)),
    ("Sacramento County, CA",    (-121.56, 38.24, -121.03, 38.74)),
    ("Santa Clara County, CA",   (-122.20, 37.11, -121.21, 37.48)),
    ("Queens County, NY",        (-73.96, 40.54, -73.70, 40.80)),
    ("Bronx County, NY",         (-73.93, 40.79, -73.75, 40.92)),
    ("Wayne County, MI",         (-83.53, 42.10, -82.74, 42.45)),
]

PAGE_SIZE = 1000
DEFAULT_OUTPUT_PATH = Path("data/raw/fema_flood_zones.json")

# High-risk zone codes — Special Flood Hazard Areas (1% annual chance flood).
_HIGH_RISK_ZONES = frozenset(["A", "AE", "AH", "AO", "AR", "A99", "V", "VE"])


# ---------------------------------------------------------------------------
# Flood zone risk classification
# ---------------------------------------------------------------------------

def classify_flood_risk(fld_zone: str, zone_subty: str | None = None) -> str:
    """Return HIGH / MODERATE / MINIMAL / UNKNOWN risk level for a FEMA zone code."""
    z = (fld_zone or "").strip().upper()
    sub = (zone_subty or "").strip().upper()

    if z in _HIGH_RISK_ZONES or (z.startswith("A") and z not in ("", "X")):
        return "HIGH"
    if z.startswith("V"):
        return "HIGH"
    if z == "X":
        if "500" in sub or "0.2" in sub:
            return "MODERATE"
        return "MINIMAL"
    if z == "D":
        return "UNKNOWN"
    return "MINIMAL"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _ring_centroid(rings: list) -> tuple[float, float] | None:
    """
    Compute approximate centroid from ArcGIS polygon rings.
    Returns (lon, lat) or None if rings are empty/invalid.
    Uses simple average of outer ring vertices — sufficient for KNN proximity lookup.
    """
    if not rings:
        return None
    ring = rings[0]  # outer ring
    if not ring or len(ring) < 3:
        return None
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY_S = 5


def _fetch_bbox(
    session: requests.Session,
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    """
    Fetch FEMA features for a single bounding box (no pagination — single page).
    Returns raw feature dicts or empty list on failure.
    """
    xmin, ymin, xmax, ymax = bbox
    bbox_str = f"{xmin},{ymin},{xmax},{ymax}"
    params = {
        "geometry": bbox_str,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_AR_ID,OBJECTID,FLD_ZONE,ZONE_SUBTY",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": "0.001",  # ~100m simplification to reduce payload
        "resultRecordCount": PAGE_SIZE,
        "f": "json",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(FEMA_NFHL_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", str(data["error"])))
            return data.get("features", [])
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                print(f" FAIL({exc})", end="", flush=True)
                return []
    return []


def _split_bbox(bbox: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]:
    """Split a bounding box into 4 quadrants."""
    xmin, ymin, xmax, ymax = bbox
    xmid = (xmin + xmax) / 2
    ymid = (ymin + ymax) / 2
    return [
        (xmin, ymin, xmid, ymid),  # SW
        (xmid, ymin, xmax, ymid),  # SE
        (xmin, ymid, xmid, ymax),  # NW
        (xmid, ymid, xmax, ymax),  # NE
    ]


def _features_to_records(features: list[dict], seen_ids: set[str]) -> list[dict]:
    """Convert raw FEMA features to deduplicated records."""
    records = []
    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        rings = geom.get("rings", [])

        centroid = _ring_centroid(rings)
        if centroid is None:
            continue

        lon, lat = centroid
        fld_zone = (attrs.get("FLD_ZONE") or "").strip()
        zone_subty = (attrs.get("ZONE_SUBTY") or "").strip()

        fld_ar_id = attrs.get("FLD_AR_ID") or attrs.get("OBJECTID")
        region_id = f"fema_{fld_ar_id}" if fld_ar_id else None
        if not region_id or region_id in seen_ids:
            continue
        seen_ids.add(region_id)

        records.append({
            "region_type": "flood_zone",
            "region_id": region_id,
            "fema_flood_zone": fld_zone or None,
            "zone_subty": zone_subty or None,
            "flood_risk": classify_flood_risk(fld_zone, zone_subty),
            "latitude": lat,
            "longitude": lon,
        })
    return records


def _fetch_bbox_recursive(
    session: requests.Session,
    bbox: tuple[float, float, float, float],
    seen_ids: set[str],
    depth: int = 0,
) -> list[dict]:
    """
    Fetch FEMA features for a bbox. If the result hits PAGE_SIZE (1000),
    split into 4 quadrants and recurse. Max depth 3 (~64 tiles).
    """
    features = _fetch_bbox(session, bbox)
    if len(features) < PAGE_SIZE or depth >= 3:
        return _features_to_records(features, seen_ids)

    # Hit the 1000-feature cap — split into quadrants
    records = []
    for quad in _split_bbox(bbox):
        records.extend(_fetch_bbox_recursive(session, quad, seen_ids, depth + 1))
    return records


def fetch_flood_zones(dry_run: bool) -> list[dict]:
    """
    Fetch FEMA NFHL flood zone data for all counties in COUNTY_BBOXES.
    Uses county-level bounding boxes with quadrant tiling when a bbox
    returns the 1000-feature cap.
    """
    session = requests.Session()
    all_records: list[dict] = []
    seen_ids: set[str] = set()

    print(f"Fetching FEMA NFHL flood zones for {len(COUNTY_BBOXES)} counties...")

    for i, (label, bbox) in enumerate(COUNTY_BBOXES, 1):
        print(f"  [{i}/{len(COUNTY_BBOXES)}] {label}...", end=" ", flush=True)
        county_records = _fetch_bbox_recursive(session, bbox, seen_ids)
        all_records.extend(county_records)
        print(f"{len(county_records)} zones.")

        if dry_run and i >= 3:
            print("  Dry-run: stopping after 3 counties.")
            break

    return all_records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "fema_flood_zones",
        "source_url": FEMA_NFHL_URL,
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
        description="Ingest FEMA NFHL flood zone designations for all active-permit counties."
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
        help="Fetch one page only; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        records = fetch_flood_zones(args.dry_run)
    except Exception as exc:
        print(f"ERROR: fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nTotal flood zone records fetched: {len(records)}")
    if records:
        zone_counts: dict[str, int] = {}
        for r in records:
            z = r.get("fema_flood_zone") or "UNKNOWN"
            zone_counts[z] = zone_counts.get(z, 0) + 1
        print("  Flood zone breakdown:")
        for zone, count in sorted(zone_counts.items(), key=lambda x: -x[1]):
            print(f"    {zone}: {count}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
