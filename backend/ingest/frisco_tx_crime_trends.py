"""
backend/ingest/frisco_tx_crime_trends.py
task: data-078
lane: data

Frisco TX crime trends ingest — STUB (no public API).

Research (2026-03-27):
  No public crime API. Org GE4Z4z1cnF58LL3C returns 0 services.
  All ArcGIS Online org IDs and self-hosted GIS servers checked.

Output:
  data/raw/frisco_tx_crime_trends.json — 0-record staging file

Usage:
  python backend/ingest/frisco_tx_crime_trends.py
  python backend/ingest/frisco_tx_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/frisco_tx_crime_trends.json")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "frisco_tx_crime_trends",
        "source_url": "N/A — no public API",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Frisco TX crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Frisco TX: no public crime data API available.")
    print("  No public crime API. Org GE4Z4z1cnF58LL3C returns 0 services.")
    print("  Writing 0-record staging file.")
    write_staging_file([], args.output)


if __name__ == "__main__":
    main()
