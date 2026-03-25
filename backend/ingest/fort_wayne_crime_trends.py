"""
backend/ingest/fort_wayne_crime_trends.py
task: data-068
lane: data

Fort Wayne crime trends ingest — STUB (no public API).

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

Output:
  data/raw/fort_wayne_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/fort_wayne_crime_trends.py
  python backend/ingest/fort_wayne_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fort Wayne crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Fort Wayne crime trends ingest — NO PUBLIC API AVAILABLE")
    print()
    print("Research (2026-03-25) found no publicly accessible crime data API.")
    print("Fort Wayne publishes crime stats only as monthly PDF reports at:")
    print("  https://www.cityoffortwayne.in.gov/699/Crime-Stats")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("To add Fort Wayne crime data, a FOIA request or manual CSV")
    print("extraction from the monthly reports would be required.")
    sys.exit(0)


if __name__ == "__main__":
    main()
