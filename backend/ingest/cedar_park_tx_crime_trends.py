"""
backend/ingest/cedar_park_tx_crime_trends.py
task: data-078
lane: data

Cedar Park TX crime trends — STUB (no public API available).

Research (2026-03-27):
  Cedar Park TX — Austin suburb (2026-03-27). Cedar Park Police Department
  does not publish incident-level crime data via any public REST API. City
  size (~100k) does not support a dedicated open data portal. No Socrata,
  ArcGIS Hub, or CKAN crime incident dataset found.

  Available sources (none are machine-readable):
    - Cedar Park PD does not publish incident-level data via any REST API
    - No dedicated open data portal for a city of ~100k residents
    - No Socrata, ArcGIS Hub, or CKAN crime incident dataset found

  To add Cedar Park crime data, a public records request to the Cedar Park
  Police Department would be required.

Output:
  data/raw/cedar_park_tx_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/cedar_park_tx_crime_trends.py
  python backend/ingest/cedar_park_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/cedar_park_tx_crime_trends.json")

CEDAR_PARK_LAT = 30.5052
CEDAR_PARK_LON = -97.8203


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "cedar_park_tx_crime_trends",
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
        description="Cedar Park TX crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Cedar Park does not publish crime incident data through a public API.")
    print("  City size (~100k) does not support a dedicated open data portal; no CKAN/Socrata/ArcGIS crime dataset found.")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
