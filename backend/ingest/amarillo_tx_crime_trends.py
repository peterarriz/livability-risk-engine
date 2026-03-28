"""
backend/ingest/amarillo_tx_crime_trends.py
task: data-078
lane: data

Amarillo TX crime trends — STUB (no public API available).

Research (2026-03-27):
  Amarillo TX — confirmed no public API (data-070, data-071, 2026-03-27). APD
  no public open data crime API. CrimeMapping.com provides view-only map. No
  ArcGIS Hub or Socrata portal with permit data confirmed. Re-confirmed
  2026-03-25.

  Available sources (none are machine-readable):
    - CrimeMapping.com: view-only map, no API
    - APD does not publish incident-level data via any public REST API
    - No ArcGIS Hub or Socrata portal with crime incident data confirmed

  To add Amarillo crime data, a public records request to the Amarillo Police
  Department would be required.

Output:
  data/raw/amarillo_tx_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/amarillo_tx_crime_trends.py
  python backend/ingest/amarillo_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/amarillo_tx_crime_trends.json")

AMARILLO_LAT = 35.2220
AMARILLO_LON = -101.8313


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "amarillo_tx_crime_trends",
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
        description="Amarillo TX crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Amarillo does not publish crime incident data through a public API.")
    print("  APD has no public open data API; CrimeMapping.com is view-only (re-confirmed data-070, data-071).")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
