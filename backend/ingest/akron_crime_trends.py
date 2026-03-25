"""
backend/ingest/akron_crime_trends.py
task: data-074
lane: data

Akron Police Department (APD) crime trends — STUB (no public API).

Source:
  Researched multiple times (data-068, data-071, data-074).
  data.akronohio.gov exists but APD uses a web-only public portal for
  incident reports with no REST API. No queryable crime incident API
  confirmed as of 2026-03-25.

To fix (if a public API becomes available):
  1. Visit https://data.akronohio.gov
  2. Search for "crime incidents" or "police incidents" dataset
  3. If found, replace this stub with a live ingest script

Output:
  data/raw/akron_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/akron_crime_trends.py
  python backend/ingest/akron_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/akron_crime_trends.json")

AKRON_LAT = 41.0814
AKRON_LON = -81.5190


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "akron_crime_trends",
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
        description="Akron APD crime trends — stub (no public API)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Akron crime trends — no public API (APD web-only portal; no REST endpoint confirmed).")
    if args.dry_run:
        print("Dry-run: would write 0-record stub.")
        return
    write_staging_file([], args.output)
    print("Done.")


if __name__ == "__main__":
    main()
