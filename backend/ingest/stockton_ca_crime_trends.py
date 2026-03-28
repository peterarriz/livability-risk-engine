"""
backend/ingest/stockton_ca_crime_trends.py
task: data-078
lane: data

Stockton CA crime trends — STUB (no public API available).

Research (2026-03-27):
  Stockton CA — no confirmed public crime API (2026-03-27). data.stocktonca.gov
  does not appear to have a queryable crime incident dataset. The Stockton
  Police Department has no confirmed Socrata, ArcGIS Hub, or CKAN open data
  portal with incident-level crime data.

  MUST VERIFY: Try curl https://data.stocktonca.gov/api/catalog/v1?q=crime&limit=10
  to confirm. If found, update this script to use the Socrata endpoint.

  Available sources (none confirmed machine-readable):
    - data.stocktonca.gov: no queryable crime incident dataset confirmed
    - Stockton PD has no confirmed Socrata, ArcGIS Hub, or CKAN portal
    - No incident-level crime data found via public REST API

  To add Stockton crime data, verify data.stocktonca.gov for any updated
  crime datasets or contact the Stockton Police Department directly.

Output:
  data/raw/stockton_ca_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/stockton_ca_crime_trends.py
  python backend/ingest/stockton_ca_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/stockton_ca_crime_trends.json")

STOCKTON_LAT = 37.9577
STOCKTON_LON = -121.2908


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "stockton_ca_crime_trends",
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
        description="Stockton CA crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Stockton does not publish crime incident data through a public API.")
    print("  data.stocktonca.gov has no confirmed queryable crime incident dataset (MUST VERIFY).")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
