"""
backend/ingest/gilbert_crime_trends.py
task: data-058, data-059, data-066, data-072
lane: data

Gilbert Police Department (GPD) crime trends — STUB (endpoint blocked).

Source:
  ArcGIS FeatureServer — Gilbert AZ Open Data
  Portal: https://data.gilbertaz.gov
  Org ID K1VMQDQNLVxLvLqs is CONFIRMED INVALID (returns HTTP 400 "Invalid URL").
  A public FeatureServer likely exists under a different org ID but cannot be
  determined without live network access.

To fix (when correct org ID is known):
  1. Visit https://data.gilbertaz.gov
  2. Search for "Police Incidents" or "Crime" dataset
  3. Click "I want to use this" → "API" to get the FeatureServer URL
  4. Extract the org ID (alphanumeric segment after services.arcgis.com/)
  5. Update FEATURESERVER_URL in this file and service_url in
     us_city_permits_arcgis.py for the gilbert entry
  6. Verify DATE_FIELD and GROUP_FIELD match actual layer fields
  7. Re-run: python backend/ingest/gilbert_crime_trends.py --dry-run

Output:
  data/raw/gilbert_crime_trends.json — 0 records (stub; no working endpoint)

Usage:
  python backend/ingest/gilbert_crime_trends.py
  python backend/ingest/gilbert_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path("data/raw/gilbert_crime_trends.json")

GILBERT_LAT = 33.3528
GILBERT_LON = -111.7890


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "gilbert_crime_trends",
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
        description="Gilbert GPD crime trends — stub (org ID K1VMQDQNLVxLvLqs invalid)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Gilbert crime trends — no working endpoint (org ID K1VMQDQNLVxLvLqs is invalid).")
    print("Visit https://data.gilbertaz.gov to find the correct FeatureServer URL.")
    if args.dry_run:
        print("Dry-run: would write 0-record stub.")
        return
    write_staging_file([], args.output)
    print("Done.")


if __name__ == "__main__":
    main()
