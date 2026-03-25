"""
backend/ingest/cape_coral_crime_trends.py
task: data-068
lane: data

Cape Coral crime trends ingest — STUB (no public API).

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

  The org ID qJBnRfhGOvGVBnaX used previously was invalid. The actual
  Cape Coral GIS org ID is MZl3VrkZJOk1VhY4 (on services1.arcgis.com),
  but it has no crime layers.

Output:
  data/raw/cape_coral_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/cape_coral_crime_trends.py
  python backend/ingest/cape_coral_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cape Coral crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Cape Coral crime trends ingest — NO PUBLIC API AVAILABLE")
    print()
    print("Research (2026-03-25) found no publicly accessible crime data API.")
    print("Cape Coral Open Data (capecoral-capegis.opendata.arcgis.com) has")
    print("70+ GIS datasets but no crime/police incident layers.")
    print("Annual PDF reports are available at capecops.com.")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("To add Cape Coral crime data, a public records request or FDLE")
    print("state-level data would be required.")
    sys.exit(0)


if __name__ == "__main__":
    main()
