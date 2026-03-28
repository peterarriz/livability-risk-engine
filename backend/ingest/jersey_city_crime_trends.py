"""
backend/ingest/jersey_city_crime_trends.py
task: data-078
lane: data

Jersey City NJ crime trends — STUB (no public API available).

Research (2026-03-27):
  Jersey City NJ — no confirmed public crime API (2026-03-27). The Jersey City
  Police Department does not publish incident-level crime data via a public
  REST API. data.jerseycitynj.gov has limited datasets (parking, 311) but no
  crime incident API. Hudson County covers some law enforcement; no
  county-wide public crime dataset found.

  MUST VERIFY: check data.jerseycitynj.gov for updated datasets or contact
  JCPD directly.

  Available sources (none are machine-readable):
    - data.jerseycitynj.gov: parking and 311 data only, no crime incidents
    - Jersey City PD does not publish incident-level data via any REST API
    - Hudson County has no county-wide public crime dataset

  To add Jersey City crime data, check data.jerseycitynj.gov for updated
  datasets or contact the Jersey City Police Department directly.

Output:
  data/raw/jersey_city_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/jersey_city_crime_trends.py
  python backend/ingest/jersey_city_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/jersey_city_crime_trends.json")

JERSEY_CITY_LAT = 40.7178
JERSEY_CITY_LON = -74.0431


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "jersey_city_crime_trends",
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
        description="Jersey City NJ crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Jersey City does not publish crime incident data through a public API.")
    print("  data.jerseycitynj.gov has parking/311 data only; JCPD has no incident-level REST API.")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
