"""
backend/ingest/eugene_crime_trends.py
task: data-070
lane: data

Eugene crime trends ingest — STUB (no public API).

Research (2026-03-25):
  Eugene does NOT publish crime incident data through any publicly
  accessible ArcGIS FeatureServer, Socrata API, or other open data endpoint.

  Available sources (none are machine-readable):
    - Annual PDF crime statistics: eugene-or.gov/542/Crime-Statistics
    - EPD Dispatch Log (2-hour delay, no API): coeapps.eugene-or.gov/epddispatchlog
    - CrimeMapping.com/map/or/eugene (proprietary, no public API)
    - FBI Crime Data Explorer (annual aggregates, lags 1-2 years)

  The domain data.eugene-or.gov does not exist. The city's ArcGIS org
  (Eugene-PWE on services1.arcgis.com) contains only public works data.
  The EPD GIS folder (gis.eugene-or.gov) has only patrol beat boundaries,
  not crime incidents.

Output:
  data/raw/eugene_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/eugene_crime_trends.py
  python backend/ingest/eugene_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eugene crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Eugene crime trends ingest — NO PUBLIC API AVAILABLE")
    print()
    print("Research (2026-03-25) found no publicly accessible crime data API.")
    print("Eugene PD publishes crime stats only as annual PDF reports at:")
    print("  https://www.eugene-or.gov/542/Crime-Statistics")
    print("The EPD Dispatch Log (coeapps.eugene-or.gov/epddispatchlog) is")
    print("real-time only with no historical API.")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("To add Eugene crime data, manual extraction from annual PDF")
    print("reports or a FBI Crime Data Explorer integration would be required.")
    sys.exit(0)


if __name__ == "__main__":
    main()
