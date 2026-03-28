"""
backend/ingest/newark_nj_crime_trends.py
task: data-078
lane: data

Newark NJ crime trends — STUB (no public API available).

Research (2026-03-27):
  Newark NJ — no confirmed public crime API (2026-03-27). Issue #247 suggested
  data.newarkde.gov (which appears to be Newark, Delaware, not NJ). The Newark
  NJ Police Department does not publish incident-level crime data via a public
  REST API. No confirmed Socrata, ArcGIS Hub, or CKAN portal for Newark, NJ
  crime incidents.

  MUST VERIFY: Try curl https://data.newark.gov/api/catalog/v1?q=crime&limit=10
  to check for a city portal.

  Available sources (none confirmed machine-readable):
    - data.newarkde.gov: Newark, Delaware portal — not Newark, NJ
    - Newark NJ PD does not publish incident-level data via any REST API
    - No confirmed Socrata, ArcGIS Hub, or CKAN portal for Newark NJ crime

  To add Newark NJ crime data, verify data.newark.gov for any crime datasets
  or contact the Newark Police Department directly.

Output:
  data/raw/newark_nj_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/newark_nj_crime_trends.py
  python backend/ingest/newark_nj_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/newark_nj_crime_trends.json")

NEWARK_LAT = 40.7357
NEWARK_LON = -74.1724


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "newark_nj_crime_trends",
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
        description="Newark NJ crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Newark NJ does not publish crime incident data through a public API.")
    print("  data.newarkde.gov is Newark, Delaware — no confirmed NJ crime portal found (MUST VERIFY data.newark.gov).")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
