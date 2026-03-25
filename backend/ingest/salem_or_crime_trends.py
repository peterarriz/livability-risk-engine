"""
backend/ingest/salem_or_crime_trends.py
task: data-071
lane: data

Salem OR crime trends ingest — STUB (no public API).

Research (2026-03-25):
  Salem, OR does NOT publish crime incident data through any publicly
  accessible ArcGIS FeatureServer, Socrata API, or other open data endpoint.

  Available sources (none are machine-readable):
    - LexisNexis Community Crime Map (view-only, no API): communitycrimemap.com
    - Static PDF crime report: "Crime in Salem: Exploring the Trends 2025"
    - Official records via egov.cityofsalem.net/JusticeWeb (web form only)
    - Oregon State Police UCR annual aggregates (city-level only, no districts)

  The DataSalem portal (data.cityofsalem.net) is ArcGIS Hub with ~200+
  datasets but zero crime/police incident layers. The only police-related
  service is IT_PoliceDistrict (district boundaries, not incidents).
  The ArcGIS org ID uUvqNr0XSi28N3Hj used previously was fabricated.

Output:
  data/raw/salem_or_crime_trends.json — 0-record staging file

Usage:
  python backend/ingest/salem_or_crime_trends.py
  python backend/ingest/salem_or_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/salem_or_crime_trends.json")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "salem_or_crime_trends",
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
        description="Salem OR crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Salem OR: no public crime data API available.")
    print("  data.cityofsalem.net has ~200+ datasets but zero crime layers.")
    print("  Salem PD uses LexisNexis Community Crime Map (no public API).")
    print("  Writing 0-record staging file.")
    write_staging_file([], args.output)


if __name__ == "__main__":
    main()
