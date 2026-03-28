"""
backend/ingest/garland_tx_crime_trends.py
task: data-078
lane: data

Garland TX crime trends — STUB (no public API available).

Research (2026-03-27):
  Garland TX — confirmed no public API (data-058, data-071, 2026-03-27). GPD
  no public incident-level API found (re-confirmed multiple times). No Socrata,
  ArcGIS Hub, or CKAN crime incident dataset. Garland is a Dallas metro
  suburban city; no dedicated open data portal.

  Available sources (none are machine-readable):
    - Garland PD does not publish incident-level data via any REST API
    - No dedicated open data portal for Garland TX
    - No Socrata, ArcGIS Hub, or CKAN crime incident dataset found

  To add Garland crime data, a public records request to the Garland Police
  Department would be required.

Output:
  data/raw/garland_tx_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/garland_tx_crime_trends.py
  python backend/ingest/garland_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/garland_tx_crime_trends.json")

GARLAND_LAT = 32.9126
GARLAND_LON = -96.6389


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "garland_tx_crime_trends",
        "source_url": None,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Garland TX crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Garland does not publish crime incident data through a public API.")
    print("  GPD has no public incident-level API; no open data portal found (re-confirmed data-058, data-071).")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
