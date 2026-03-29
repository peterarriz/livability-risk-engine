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

# Chicago metropolitan area bounding box (WGS84, decimal degrees)
# Covers Cook County and immediate surroundings.
CHICAGO_BBOX_STR = "-88.0,41.6,-87.5,42.1"

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

def fetch_flood_zones(dry_run: bool) -> list[dict]:
    """
    Paginate the FEMA NFHL REST API and return flood zone centroid records
    for the Chicago metro area bounding box.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print("Fetching FEMA NFHL flood zones for Chicago metro (Cook County)...")
    print(f"  Bounding box: {CHICAGO_BBOX_STR}")

    MAX_RETRIES = 3
    RETRY_DELAY_S = 5

    while True:
        params = {
            "geometry": CHICAGO_BBOX_STR,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_AR_ID,OBJECTID,FLD_ZONE,ZONE_SUBTY",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
            "f": "json",
        }

        print(f"  Fetching page at offset {offset}...", end=" ", flush=True)

        data = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = session.get(FEMA_NFHL_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    err = data["error"]
                    msg = err.get("message", str(err))
                    raise RuntimeError(f"FEMA API error: {msg}")

                break  # success
            except (requests.exceptions.RequestException, RuntimeError) as exc:
                if attempt < MAX_RETRIES:
                    print(f"\n    WARN: attempt {attempt}/{MAX_RETRIES} failed ({exc}). Retrying in {RETRY_DELAY_S}s...", flush=True)
                    time.sleep(RETRY_DELAY_S)
                    print(f"  Retrying offset {offset}...", end=" ", flush=True)
                else:
                    print(f"\n  ERROR: All {MAX_RETRIES} attempts failed at offset {offset}. Writing {len(all_records)} records fetched so far.", file=sys.stderr)
                    return all_records  # return what we have instead of losing everything

        if data is None:
            return all_records

        features = data.get("features", [])
        print(f"{len(features)} features.")

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

            # Use FLD_AR_ID (flood area ID) for stable deduplication, fall back to OBJECTID.
            fld_ar_id = attrs.get("FLD_AR_ID") or attrs.get("OBJECTID")
            region_id = f"fema_{fld_ar_id}" if fld_ar_id else f"fema_offset_{offset + len(all_records)}"

            all_records.append({
                "region_type": "flood_zone",
                "region_id": region_id,
                "fema_flood_zone": fld_zone or None,
                "zone_subty": zone_subty or None,
                "flood_risk": classify_flood_risk(fld_zone, zone_subty),
                "latitude": lat,
                "longitude": lon,
            })

        offset += len(features)

        if dry_run and offset >= PAGE_SIZE:
            print("  Dry-run: stopping after first page.")
            break

        if len(features) < PAGE_SIZE:
            break

        # ArcGIS sets exceededTransferLimit when there are more results to fetch.
        if not data.get("exceededTransferLimit", False):
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
        description="Ingest FEMA NFHL flood zone designations for Chicago metro area."
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
