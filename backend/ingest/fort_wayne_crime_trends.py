"""
backend/ingest/fort_wayne_crime_trends.py
task: data-068, data-073
lane: data

Fort Wayne crime trends — STUB (no public API available).

Research (2026-03-25):
  Fort Wayne does NOT publish crime incident data through any publicly
  accessible ArcGIS FeatureServer, Socrata API, or other open data endpoint.

  Available sources (none are machine-readable):
    - Monthly PDF/HTML statistical reports: cityoffortwayne.in.gov/699/Crime-Stats
    - LexisNexis Community Crime Map (view-only, no API)
    - FOIA requests via NextRequest: cityoffortwayne.nextrequest.com
    - FBI UCR/NIBRS annual aggregates (too coarse for trend analysis)

  The city GIS portal (maps.cityoffortwayne.org) has zoning, parks, and
  utilities layers but no crime data layers.

  To add Fort Wayne crime data, a FOIA request or manual CSV extraction
  from the monthly reports would be required.

Output:
  data/raw/fort_wayne_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/fort_wayne_crime_trends.py
  python backend/ingest/fort_wayne_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/fort_wayne_crime_trends.json")

FORT_WAYNE_LAT = 41.0793
FORT_WAYNE_LON = -85.1394


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "fort_wayne_crime_trends",
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
        description="Fort Wayne crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Fort Wayne crime trends — no public API available.")
    print("Research (2026-03-25) found only monthly PDF reports at:")
    print("  https://www.cityoffortwayne.in.gov/699/Crime-Stats")
    if args.dry_run:
        print("Dry-run: would write 0-record stub.")
        return
    write_staging_file([], args.output)
    print("Done.")


if __name__ == "__main__":
    main()
