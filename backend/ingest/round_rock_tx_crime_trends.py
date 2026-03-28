"""
backend/ingest/round_rock_tx_crime_trends.py
task: data-078
lane: data

Round Rock TX crime trends — STUB (no public API available).

Research (2026-03-27):
  Round Rock TX — Austin suburb (2026-03-27). Round Rock Police Department
  does not publish incident-level crime data via a public REST API.
  data.roundrocktexas.gov is a document portal, not an open data API. No
  Socrata, ArcGIS Hub, or CKAN crime incident dataset found. City is served
  by RRPD independently from APD.

  Available sources (none are machine-readable):
    - data.roundrocktexas.gov: document portal only, no queryable crime API
    - Round Rock PD does not publish incident-level data via any REST API
    - No Socrata, ArcGIS Hub, or CKAN crime incident dataset found

  To add Round Rock crime data, a public records request to the Round Rock
  Police Department would be required.

Output:
  data/raw/round_rock_tx_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/round_rock_tx_crime_trends.py
  python backend/ingest/round_rock_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/round_rock_tx_crime_trends.json")

ROUND_ROCK_LAT = 30.5083
ROUND_ROCK_LON = -97.6789


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "round_rock_tx_crime_trends",
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
        description="Round Rock TX crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("SKIPPED: Round Rock does not publish crime incident data through a public API.")
    print("  data.roundrocktexas.gov is a document portal; RRPD has no incident-level REST API.")
    print("  Exiting cleanly with 0 records.")
    if args.dry_run:
        return
    write_staging_file([], DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
