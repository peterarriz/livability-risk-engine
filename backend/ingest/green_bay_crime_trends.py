"""
backend/ingest/green_bay_crime_trends.py
task: data-071
lane: data

Green Bay crime trends ingest — STUB (no confirmed public API).

Research (2026-03-25):
  Green Bay PD does not publish crime incident data through any confirmed
  publicly accessible ArcGIS FeatureServer, Socrata, or CKAN open data endpoint.

  Portals investigated:
    - data.greenbaywi.gov — does not resolve to an open data portal
    - greenbaywi.gov — city website only; no open data section found
    - ArcGIS Hub search for "Green Bay crime" — no verified public org found
    - Brown County (greenbay.maps.arcgis.com) — no crime incident dataset confirmed

  Available sources (none are machine-readable incident APIs):
    - Annual PDF crime reports: greenbaywi.gov/gbpd
    - CrimeMapping.com/map/wi/green-bay (proprietary, no public API)
    - FBI Crime Data Explorer (annual aggregates, lags 1-2 years)

Output:
  data/raw/green_bay_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/green_bay_crime_trends.py
  python backend/ingest/green_bay_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Green Bay crime trends — STUB (no confirmed public API)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Green Bay crime trends ingest — NO CONFIRMED PUBLIC API")
    print()
    print("Research (2026-03-25) found no confirmed publicly accessible crime data API.")
    print("Green Bay PD publishes crime stats only as annual PDF reports at:")
    print("  https://greenbaywi.gov/gbpd")
    print("data.greenbaywi.gov does not resolve to an open data portal.")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("If a portal becomes available, implement using the ArcGIS or Socrata pattern.")
    sys.exit(0)


if __name__ == "__main__":
    main()
