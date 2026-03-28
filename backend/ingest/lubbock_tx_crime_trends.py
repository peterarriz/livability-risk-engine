"""
backend/ingest/lubbock_tx_crime_trends.py
task: data-078
lane: data

Lubbock TX crime trends — STUB (no public API available).

Research (2026-03-27):
  Lubbock TX — confirmed no public API (data-058, data-071, 2026-03-27). LPD
  publishes quarterly PDF statistics only; no queryable incident-level API.
  Re-confirmed multiple times. No Socrata, ArcGIS Hub, or CKAN portal found.

  Available sources (none are machine-readable):
    - LPD publishes quarterly PDF statistics only
    - No queryable incident-level API of any kind
    - No Socrata, ArcGIS Hub, or CKAN portal found

  To add Lubbock crime data, a public records request to the Lubbock Police
  Department would be required.

Output:
  data/raw/lubbock_tx_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/lubbock_tx_crime_trends.py
  python backend/ingest/lubbock_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/lubbock_tx_crime_trends.json")

LUBBOCK_LAT = 33.5779
LUBBOCK_LON = -101.8552


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "lubbock_tx_crime_trends",
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
        description="Lubbock TX crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Lubbock does not publish crime incident data through a public API.")
    print("  LPD publishes quarterly PDF statistics only; no incident-level API (re-confirmed data-058, data-071).")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
