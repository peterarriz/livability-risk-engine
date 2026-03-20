"""
backend/ingest/geocode_fill.py
task: data-014
lane: data

Geocode-fill pass for staging records that have address text but
are missing latitude/longitude coordinates.

Reads both MVP staging JSON files (building permits and street
closures), geocodes records with a missing lat/lon using the
geocode_address() function from backend/ingest/geocode.py, and
writes the filled records back to the same staging files.

The filled staging files are then picked up by load_projects.py
on the next run, increasing scoring coverage by reducing the
"Skipped (no coords)" count that appears in the load summary.

Usage:
  # Fill both staging files (default paths):
  python backend/ingest/geocode_fill.py

  # Custom paths:
  python backend/ingest/geocode_fill.py \\
      --permits-file data/raw/building_permits.json \\
      --closures-file data/raw/street_closures.json

  # Dry-run: show how many records would be filled without writing:
  python backend/ingest/geocode_fill.py --dry-run

  # Limit geocode calls (useful for testing):
  python backend/ingest/geocode_fill.py --max-fill 50

Acceptance criteria (data-014):
  - Reads both staging JSON files and fills lat/lon for records
    that have an address but no coordinates.
  - Filled records are written back so load_projects.py uses them.
  - Script is idempotent: already-filled records are never re-geocoded.
  - Progress and skip counts are printed clearly.

Notes:
  - Uses geocode_address() from backend/ingest/geocode.py.
  - Respects the Nominatim/Census rate limit with a 0.25s sleep
    between geocoding requests.
  - Records that fail geocoding are left unchanged (lat/lon stays
    None) so the pipeline is not blocked by unresolvable addresses.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.ingest.geocode import geocode_address

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PERMITS_FILE    = Path("data/raw/building_permits.json")
DEFAULT_CLOSURES_FILE   = Path("data/raw/street_closures.json")
DEFAULT_CTA_ALERTS_FILE = Path("data/raw/cta_alerts.json")
DEFAULT_IL_CITIES_DIR   = Path("data/raw")
IL_CITIES_FILE_GLOB     = "il_city_permits_*.json"

# Seconds to sleep between geocoding requests to respect rate limits.
GEOCODE_SLEEP_S = 0.25


# ---------------------------------------------------------------------------
# Address extraction helpers
# ---------------------------------------------------------------------------

def _permit_address(record: dict) -> str | None:
    """
    Build a Chicago address string from raw permit fields.
    Returns None if there is not enough data to form a usable address.
    """
    parts = [
        record.get("street_number", ""),
        record.get("street_direction", ""),
        record.get("street_name", ""),
    ]
    address = " ".join(p.strip() for p in parts if p and str(p).strip())
    if not address:
        return None
    return f"{address}, Chicago, IL"


def _closure_address(record: dict) -> str | None:
    """
    Build a Chicago address string from raw closure fields.
    Returns None if there is not enough data to form a usable address.
    """
    parts = [
        record.get("street_direction", ""),
        record.get("street_name", ""),
    ]
    address = " ".join(p.strip() for p in parts if p and str(p).strip())
    if not address:
        return None
    return f"{address}, Chicago, IL"


def _cta_alert_address(record: dict) -> str | None:
    """
    Return the address string from a CTA alert record.
    The address was built by cta_alerts._resolve_coords() during ingest
    and may be a station address or a bus route street name.
    """
    addr = (record.get("address") or "").strip()
    if not addr or addr == "Chicago, IL":
        return None
    return addr


def _il_city_permit_address(record: dict) -> str | None:
    """
    Build an address string from an IL city permit record.
    These records use 'address' and 'city_il' fields set by
    il_city_permits.normalize_raw_record().
    """
    addr = (record.get("address") or "").strip()
    if not addr:
        return None
    city_il = (record.get("city_il") or "").strip()
    if city_il:
        return f"{addr}, {city_il}"
    return addr


def _has_coords(record: dict) -> bool:
    """Return True if the record already has both lat and lon."""
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is None or lon is None:
        return False
    try:
        float(lat)
        float(lon)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Core fill logic
# ---------------------------------------------------------------------------

def fill_staging_file(
    path: Path,
    address_fn,
    dry_run: bool,
    max_fill: int | None,
) -> dict:
    """
    Read a staging JSON file, geocode records missing coordinates,
    and write the result back to the same file.

    Returns a stats dict with keys:
      total, already_filled, no_address, geocoded, failed, written
    """
    stats = {
        "total": 0,
        "already_filled": 0,
        "no_address": 0,
        "geocoded": 0,
        "failed": 0,
        "written": False,
    }

    if not path.exists():
        print(f"  Staging file not found: {path} — skipping.")
        return stats

    with path.open(encoding="utf-8") as f:
        staging = json.load(f)

    records = staging.get("records", [])
    stats["total"] = len(records)
    print(f"  Read {len(records)} records from {path}")

    to_fill = []
    for record in records:
        if _has_coords(record):
            stats["already_filled"] += 1
            continue
        addr = address_fn(record)
        if not addr:
            stats["no_address"] += 1
            continue
        to_fill.append((record, addr))

    print(
        f"  Already have coordinates: {stats['already_filled']}"
        f"  |  No address text: {stats['no_address']}"
        f"  |  To geocode: {len(to_fill)}"
    )

    if not to_fill:
        print("  Nothing to fill.")
        return stats

    if dry_run:
        print(f"  Dry-run: would geocode up to {len(to_fill)} record(s). Skipping writes.")
        return stats

    if max_fill is not None:
        to_fill = to_fill[:max_fill]
        print(f"  Limiting to {max_fill} geocode calls (--max-fill).")

    for i, (record, addr) in enumerate(to_fill):
        result = geocode_address(addr)
        if result:
            lat, lon = result
            record["latitude"] = str(lat)
            record["longitude"] = str(lon)
            stats["geocoded"] += 1
            if (i + 1) % 10 == 0 or i == len(to_fill) - 1:
                print(f"  Geocoded {stats['geocoded']}/{len(to_fill)} records...")
        else:
            stats["failed"] += 1

        if i < len(to_fill) - 1:
            time.sleep(GEOCODE_SLEEP_S)

    # Write updated records back to the staging file.
    staging["records"] = records
    staging["geocode_fill_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    stats["written"] = True
    print(
        f"  Wrote {len(records)} records back to {path}"
        f" (geocoded: {stats['geocoded']}, failed: {stats['failed']})"
    )
    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing lat/lon in staging JSON files using the geocode_address() function. "
            "Run this after ingesting raw data and before load_projects.py to maximise "
            "scoring coverage."
        )
    )
    parser.add_argument(
        "--permits-file",
        type=Path,
        default=DEFAULT_PERMITS_FILE,
        help=f"Path to building permits staging file (default: {DEFAULT_PERMITS_FILE})",
    )
    parser.add_argument(
        "--closures-file",
        type=Path,
        default=DEFAULT_CLOSURES_FILE,
        help=f"Path to street closures staging file (default: {DEFAULT_CLOSURES_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be geocoded without writing any changes.",
    )
    parser.add_argument(
        "--max-fill",
        type=int,
        default=None,
        metavar="N",
        help="Geocode at most N records per source (useful for testing).",
    )
    parser.add_argument(
        "--cta-alerts-file",
        type=Path,
        default=DEFAULT_CTA_ALERTS_FILE,
        help=f"Path to CTA alerts staging file (default: {DEFAULT_CTA_ALERTS_FILE})",
    )
    parser.add_argument(
        "--il-cities-dir",
        type=Path,
        default=DEFAULT_IL_CITIES_DIR,
        help=(
            f"Directory containing il_city_permits_*.json staging files "
            f"(default: {DEFAULT_IL_CITIES_DIR})."
        ),
    )
    parser.add_argument(
        "--source",
        choices=["permits", "closures", "cta_alerts", "il_cities", "all"],
        default="all",
        help="Which staging file(s) to fill (default: all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("── DRY-RUN MODE: no files will be written ──────────")

    all_stats = []

    if args.source in ("permits", "all"):
        print(f"\nFilling building permits: {args.permits_file}")
        stats = fill_staging_file(
            args.permits_file,
            _permit_address,
            args.dry_run,
            args.max_fill,
        )
        all_stats.append(("Building permits", stats))

    if args.source in ("closures", "all"):
        print(f"\nFilling street closures: {args.closures_file}")
        stats = fill_staging_file(
            args.closures_file,
            _closure_address,
            args.dry_run,
            args.max_fill,
        )
        all_stats.append(("Street closures", stats))

    if args.source in ("cta_alerts", "all"):
        print(f"\nFilling CTA alerts: {args.cta_alerts_file}")
        stats = fill_staging_file(
            args.cta_alerts_file,
            _cta_alert_address,
            args.dry_run,
            args.max_fill,
        )
        all_stats.append(("CTA alerts", stats))

    if args.source in ("il_cities", "all"):
        staging_files = sorted(args.il_cities_dir.glob(IL_CITIES_FILE_GLOB))
        if not staging_files:
            print(f"\nNo IL city permit staging files in {args.il_cities_dir}. Skipping.")
        for sf in staging_files:
            label = sf.stem  # e.g. "il_city_permits_cook_county"
            print(f"\nFilling {label}: {sf}")
            stats = fill_staging_file(
                sf,
                _il_city_permit_address,
                args.dry_run,
                args.max_fill,
            )
            all_stats.append((label, stats))

    print("\n══ GEOCODE-FILL SUMMARY ═════════════════════════════")
    for label, s in all_stats:
        print(
            f"  {label}: {s['geocoded']} filled, {s['failed']} failed,"
            f" {s['no_address']} no-address, {s['already_filled']} already had coords"
            f" (of {s['total']} total)"
        )

    print()


if __name__ == "__main__":
    main()
