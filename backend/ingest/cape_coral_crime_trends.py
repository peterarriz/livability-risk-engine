"""
backend/ingest/cape_coral_crime_trends.py
task: data-068, data-073
lane: data

Cape Coral crime trends — STUB (no public API available).

Research (2026-03-25):
  Cape Coral does NOT publish crime incident data through any publicly
  accessible ArcGIS FeatureServer, Socrata API, or other open data endpoint.

  Available sources (none are machine-readable):
    - Annual PDF reports on capecops.com (IA, PSB, PAO reports)
    - CityProtect page exists but returns zero incidents
    - Cape Coral Open Data (capecoral-capegis.opendata.arcgis.com) has 70+
      datasets (parks, zoning, utilities) but zero crime/police datasets
    - The PD folder on capeims.capecoral.gov/arcgis is empty/restricted
    - Public records requests: call 239-574-3223

  The actual Cape Coral GIS org ID is MZl3VrkZJOk1VhY4 (on services1.arcgis.com),
  but it has no crime layers. The org ID qJBnRfhGOvGVBnaX used in earlier
  research was invalid.

  To add Cape Coral crime data, a public records request or FDLE
  state-level data would be required.

Output:
  data/raw/cape_coral_crime_trends.json — 0 records (stub; no public API)

Usage:
  python backend/ingest/cape_coral_crime_trends.py
  python backend/ingest/cape_coral_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/cape_coral_crime_trends.json")

CAPE_CORAL_LAT = 26.5629
CAPE_CORAL_LON = -81.9495


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "cape_coral_crime_trends",
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
        description="Cape Coral crime trends — stub (no public API available)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Cape Coral crime trends — no public API available.")
    print("Research (2026-03-25): Cape Coral Open Data has 70+ GIS datasets")
    print("but no crime/police incident layers. See capecoral-capegis.opendata.arcgis.com")
    if args.dry_run:
        print("Dry-run: would write 0-record stub.")
        return
    write_staging_file([], args.output)
    print("Done.")


if __name__ == "__main__":
    main()
