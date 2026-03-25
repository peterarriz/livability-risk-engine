"""
backend/ingest/springfield_mo_crime_trends.py
task: data-070
lane: data

Springfield MO crime trends ingest — STUB (no public API).

Research (2026-03-25):
  Springfield, MO does NOT publish crime incident data through any publicly
  accessible ArcGIS FeatureServer, Socrata API, or other open data endpoint.

  Available sources (none are machine-readable):
    - LexisNexis Community Crime Map (view-only, no API): communitycrimemap.com
    - Missouri TOPS crime reporting (no REST API): showmecrime.mo.gov
    - Springfield PD tracked data (PDF/document downloads): springfieldmo.gov/856/Police-Data
    - FBI UCR/NIBRS annual aggregates (too coarse for trend analysis)

  The city GIS portal (gisdata-cosmo.opendata.arcgis.com) has 49 datasets
  (zoning, parcels, parks, sewers) but zero crime/incident datasets.
  Law_Enforcement_Zones provides patrol zone boundaries only, not incidents.
  The Open_Data FeatureServer on maps.springfieldmo.gov requires authentication.

Output:
  data/raw/springfield_mo_crime_trends.json — NOT GENERATED (no data source)

Usage:
  python backend/ingest/springfield_mo_crime_trends.py
  python backend/ingest/springfield_mo_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Springfield MO crime trends — STUB (no public API available)."
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Springfield MO crime trends ingest — NO PUBLIC API AVAILABLE")
    print()
    print("Research (2026-03-25) found no publicly accessible crime data API.")
    print("Springfield PD crime data is only available via:")
    print("  - LexisNexis Community Crime Map (view-only, no API)")
    print("  - Missouri TOPS (showmecrime.mo.gov, no REST API)")
    print("  - PDF reports at springfieldmo.gov/856/Police-Data")
    print()
    print("This script is a stub. No data will be fetched or written.")
    print("To add Springfield MO crime data, scraping TOPS or a public")
    print("records request would be required.")
    sys.exit(0)


if __name__ == "__main__":
    main()
