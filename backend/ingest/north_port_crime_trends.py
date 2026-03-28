"""
backend/ingest/north_port_crime_trends.py
task: data-078
lane: data

North Port FL crime trends — STUB (no public API available).

Research (2026-03-27):
  North Port FL — no independent city crime API (2026-03-27). North Port is in
  Sarasota County; the North Port Police Department does not publish
  incident-level crime data via any public REST API. Sarasota County Sheriff
  covers some areas. No Socrata, ArcGIS Hub, or CKAN portal found.

  Available sources (none are machine-readable):
    - North Port PD does not publish incident-level data via any REST API
    - Sarasota County Sheriff does not provide a public crime incident API
    - No open data portal with crime incident datasets found

  To add North Port crime data, a public records request to the North Port
  Police Department or Sarasota County Sheriff's Office would be required.

Output:
  data/raw/north_port_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/north_port_crime_trends.py
  python backend/ingest/north_port_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/north_port_crime_trends.json")

NORTH_PORT_LAT = 27.0447
NORTH_PORT_LON = -82.1362


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "north_port_crime_trends",
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
        description="North Port crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: North Port does not publish crime incident data through a public API.")
    print("  North Port PD and Sarasota County Sheriff have no public crime incident REST API.")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
