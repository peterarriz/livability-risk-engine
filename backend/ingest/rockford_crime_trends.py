"""
backend/ingest/rockford_crime_trends.py
task: data-071
lane: data

Rockford crime trends ingest — STUB (no confirmed public API).

Research (2026-03-25):
  Rockford PD does not publish crime incident data through any confirmed
  publicly accessible ArcGIS FeatureServer, Socrata, or CKAN open data endpoint.

  Portals investigated:
    - data.illinois.gov — state Socrata portal; no Rockford PD crime dataset found
    - cityofrockford.org — city website only; no open data section with crime API
    - ArcGIS Hub search for "Rockford crime" — no verified public org ID found
    - Winnebago County GIS — no crime incident data published

  Available sources (none are machine-readable incident APIs):
    - Annual PDF crime statistics: rockfordil.gov/rpd
    - CrimeMapping.com/map/il/rockford (proprietary, no public API)
    - FBI Crime Data Explorer (annual aggregates, lags 1-2 years)
    - data.illinois.gov has traffic crash data for the state but not city-level crime

Output:
  data/raw/rockford_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/rockford_crime_trends.py
  python backend/ingest/rockford_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rockford crime trends — STUB (no confirmed public API)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Rockford crime trends ingest — NO CONFIRMED PUBLIC API")
    print()
    print("Research (2026-03-25) found no confirmed publicly accessible crime data API.")
    print("Rockford PD publishes crime stats only as PDF reports at:")
    print("  https://www.rockfordil.gov/government/departments/police-department/")
    print("data.illinois.gov does not include city-level RPD incident data.")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("If a portal becomes available, implement using the ArcGIS or Socrata pattern.")
    sys.exit(0)


if __name__ == "__main__":
    main()
