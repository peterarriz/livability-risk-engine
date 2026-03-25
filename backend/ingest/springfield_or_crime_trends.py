"""
backend/ingest/springfield_or_crime_trends.py
task: data-071
lane: data

Springfield OR crime trends ingest — STUB (no confirmed public API).

NOTE: This is Springfield, Oregon (Lane County), not Springfield, MO
(which is covered by springfield_mo_crime_trends.py).

Research (2026-03-25):
  Springfield PD does not publish crime incident data through any confirmed
  publicly accessible ArcGIS FeatureServer, Socrata, or CKAN open data endpoint.

  Portals investigated:
    - ArcGIS Hub search for "Springfield Oregon crime" — no verified public org found
    - springfield-or.gov — city website; no open data portal found
    - Lane County GIS — no Springfield PD crime incident data published
    - Eugene (adjacent city) already confirmed no public crime API (eugene_crime_trends.py stub)

  Available sources (none are machine-readable incident APIs):
    - Annual PDF crime statistics: springfield-or.gov/police
    - CrimeMapping.com/map/or/springfield (proprietary, no public API)
    - FBI Crime Data Explorer (annual aggregates, lags 1-2 years)

  Springfield is a small city (~60k pop) adjacent to Eugene in Lane County.
  Neither Springfield nor Lane County appears to publish police incident data
  via any open data API as of 2026-03-25.

Output:
  data/raw/springfield_or_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/springfield_or_crime_trends.py
  python backend/ingest/springfield_or_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Springfield OR crime trends — STUB (no confirmed public API)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Springfield OR crime trends ingest — NO CONFIRMED PUBLIC API")
    print()
    print("Research (2026-03-25) found no confirmed publicly accessible crime data API.")
    print("Springfield PD publishes crime stats only as PDF reports at:")
    print("  https://www.springfield-or.gov/police/")
    print("Lane County GIS has no Springfield PD crime incident data published.")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("If a portal becomes available, implement using the ArcGIS or Socrata pattern.")
    sys.exit(0)


if __name__ == "__main__":
    main()
