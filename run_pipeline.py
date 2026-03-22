"""
run_pipeline.py
task: data-017
lane: data

Full end-to-end ingest pipeline orchestrator for the Chicago MVP.

Runs all ingest steps in order:
  1. Fetch building permits from Chicago Socrata API       → data/raw/building_permits.json
  2. Fetch street closures from Chicago Socrata API        → data/raw/street_closures.json
  3. Fetch IDOT road construction from ArcGIS REST API     → data/raw/idot_road_projects.json
  4. Fetch IL city permits (Cook County + IL cities)       → data/raw/il_city_permits_*.json
  5. Fill missing lat/lon via geocoding                    → updates staging files in place
  6. Load normalized records into the DB                   → upserts into `projects` table

Usage:
  # Full pipeline (requires DATABASE_URL or POSTGRES_* env vars)
  python run_pipeline.py

  # Skip geocoding fill (faster; use only if staging files already have coords)
  python run_pipeline.py --skip-geocode

  # Dry-run: fetch data but do not write to DB
  python run_pipeline.py --dry-run

  # Prune completed records older than 90 days after loading
  python run_pipeline.py --prune-days 90

Environment variables:
  DATABASE_URL             — Full Postgres connection string (Railway/Heroku standard)
                             If set, takes precedence over POSTGRES_* vars.
  POSTGRES_HOST            — (default: localhost)
  POSTGRES_PORT            — (default: 5432)
  POSTGRES_DB              — (default: livability)
  POSTGRES_USER            — (default: postgres)
  POSTGRES_PASSWORD        — (required if DATABASE_URL not set)
  CHICAGO_SOCRATA_APP_TOKEN — Optional; increases Socrata API rate limits

Prerequisites:
  pip install -r backend/requirements.txt
  # Database schema must already be applied:
  # psql $DATABASE_URL -f db/schema.sql
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure the project root is on PYTHONPATH so subprocesses can resolve
# package imports like ``from backend.ingest.geocode import ...``.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
_ENV = {**os.environ, "PYTHONPATH": _PROJECT_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

STEPS = [
    {
        "name": "Fetch Chicago building permits",
        "cmd": [sys.executable, "backend/ingest/building_permits.py"],
    },
    {
        "name": "Fetch Chicago street closures",
        "cmd": [sys.executable, "backend/ingest/street_closures.py"],
    },
    {
        "name": "Fetch IDOT road construction (all districts)",
        "cmd": [sys.executable, "backend/ingest/idot_road_projects.py"],
        "skip_key": "skip_statewide",
    },
    # Cook County permits are handled by il_city_permits.py (dataset 6yjf-dfxs).
    # The standalone cook_county_permits.py has an incorrect dataset ID and is
    # skipped to avoid pipeline failures. Remove this comment when the
    # standalone script is fixed or deleted.
    {
        # Fetches Cook County + IL city permits from their Socrata portals.
        # Individual city failures are logged as warnings but do not abort
        # the pipeline — the step exits 0 as long as at least one city succeeds.
        "name": "Fetch IL city permits (Cook County + cities)",
        "cmd": [sys.executable, "backend/ingest/il_city_permits.py"],
        "skip_key": "skip_il_cities",
    },
    {
        # Fetches building permits and street closures for the top 10 US cities
        # (NYC, LA, Houston, Phoenix, Philadelphia, San Antonio, San Diego,
        # Dallas, Austin) from their Socrata open data portals.
        # Individual city failures are non-fatal — pipeline continues.
        "name": "Fetch US city permits (top 10 cities)",
        "cmd": [sys.executable, "backend/ingest/us_city_permits.py"],
        "skip_key": "skip_us_cities",
        "non_fatal": True,
    },
    {
        # Fetches CTA planned service alerts (track work, station closures,
        # construction-related reroutes). No API key required.
        "name": "Fetch CTA planned service alerts",
        "cmd": [sys.executable, "backend/ingest/cta_alerts.py"],
        "skip_key": "skip_cta",
    },
    {
        # Fetches recent Chicago traffic crashes (last 30 days).
        # Recent crash scenes are disruption signals. Dataset: 85ca-t3if.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago traffic crashes",
        "cmd": [sys.executable, "backend/ingest/chicago_traffic_crashes.py"],
        "skip_key": "skip_traffic_crashes",
        "non_fatal": True,
    },
    {
        # Fetches Divvy bike station closures via GBFS API.
        # Out-of-service stations are LOW-severity disruption signals.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Divvy bike station closures",
        "cmd": [sys.executable, "backend/ingest/chicago_divvy_stations.py"],
        "skip_key": "skip_divvy",
        "non_fatal": True,
    },
    {
        # Fetches Chicago 311 infrastructure service requests:
        # potholes, water main breaks, cave-ins, tree emergencies.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago 311 infrastructure requests",
        "cmd": [sys.executable, "backend/ingest/chicago_311_requests.py"],
        "skip_key": "skip_311",
        "non_fatal": True,
    },
    {
        # Fetches Chicago Film Permits (DCASE).
        # Film shoots cause street closures and parking restrictions.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago film permits",
        "cmd": [sys.executable, "backend/ingest/chicago_film_permits.py"],
        "skip_key": "skip_film",
        "non_fatal": True,
    },
    {
        # Fetches Chicago Special Events Permits (DCASE).
        # Festivals, parades, and marathons cause major traffic disruption.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago special events permits",
        "cmd": [sys.executable, "backend/ingest/chicago_special_events.py"],
        "skip_key": "skip_events",
        "non_fatal": True,
    },
    {
        # Fetches FEMA NFHL flood zone polygon centroids for Chicago metro.
        # Stored in neighborhood_quality table (region_type='flood_zone').
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch FEMA flood zones (Chicago metro)",
        "cmd": [sys.executable, "backend/ingest/fema_flood_zones.py"],
        "skip_key": "skip_fema",
        "non_fatal": True,
    },
    {
        # Fetches Chicago crime counts by community area, calculates 12-month trends.
        # Stored in neighborhood_quality table (region_type='community_area').
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago crime trends (community area)",
        "cmd": [sys.executable, "backend/ingest/chicago_crime_trends.py"],
        "skip_key": "skip_crime_trends",
        "non_fatal": True,
    },
    {
        # Fetches Census ACS 5-year demographics for Cook County census tracts.
        # Stored in neighborhood_quality table (region_type='census_tract').
        # No API key required. Failures are non-fatal.
        "name": "Fetch Census ACS demographics (Cook County tracts)",
        "cmd": [sys.executable, "backend/ingest/census_acs.py"],
        "skip_key": "skip_census_acs",
        "non_fatal": True,
    },
    {
        # Fetches Austin APD crime data and calculates 12-month trends by sector.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Austin crime trends",
        "cmd": [sys.executable, "backend/ingest/austin_crime_trends.py"],
        "skip_key": "skip_austin_crime",
        "non_fatal": True,
    },
    {
        # Fetches Seattle SPD crime data and calculates 12-month trends by precinct.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Seattle crime trends",
        "cmd": [sys.executable, "backend/ingest/seattle_crime_trends.py"],
        "skip_key": "skip_seattle_crime",
        "non_fatal": True,
    },
    {
        # Fetches NYC NYPD complaint data and calculates 12-month trends by precinct.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch NYC crime trends",
        "cmd": [sys.executable, "backend/ingest/nyc_crime_trends.py"],
        "skip_key": "skip_nyc_crime",
        "non_fatal": True,
    },
    {
        # Fetches Kansas City KCPD crime data and calculates 12-month trends by division.
        # Source: data.kcmo.org (Socrata). Failures are non-fatal.
        "name": "Fetch Kansas City crime trends",
        "cmd": [sys.executable, "backend/ingest/kansas_city_crime_trends.py"],
        "skip_key": "skip_kc_crime",
        "non_fatal": True,
    },
    {
        # Fetches Denver DPD crime data and calculates 12-month trends by district.
        # Source: data.denvergov.org (Socrata-compatible). Failures are non-fatal.
        "name": "Fetch Denver crime trends",
        "cmd": [sys.executable, "backend/ingest/denver_crime_trends.py"],
        "skip_key": "skip_denver_crime",
        "non_fatal": True,
    },
    {
        # Fetches Boston BPD crime data and calculates 12-month trends by district.
        # Source: data.boston.gov (CKAN). Failures are non-fatal.
        "name": "Fetch Boston crime trends",
        "cmd": [sys.executable, "backend/ingest/boston_crime_trends.py"],
        "skip_key": "skip_boston_crime",
        "non_fatal": True,
    },
    {
        # Fetches Milwaukee MPS crime data and calculates 12-month trends by district.
        # Source: data.milwaukee.gov (CKAN). Failures are non-fatal.
        "name": "Fetch Milwaukee crime trends",
        "cmd": [sys.executable, "backend/ingest/milwaukee_crime_trends.py"],
        "skip_key": "skip_milwaukee_crime",
        "non_fatal": True,
    },
    {
        # Fetches building permits from CKAN-based city open data portals
        # (Boston, Milwaukee, and other non-Socrata cities).
        # Individual city failures are non-fatal — pipeline continues.
        "name": "Fetch US city permits (CKAN cities)",
        "cmd": [sys.executable, "backend/ingest/us_city_permits_ckan.py"],
        "skip_key": "skip_ckan_cities",
        "non_fatal": True,
    },
    {
        # Fetches building permits from ArcGIS FeatureServer portals
        # (Phoenix, Columbus, Minneapolis, Charlotte, Jacksonville).
        # NOTE: Service URLs require verification before first production run.
        #   Run: python backend/ingest/us_city_permits_arcgis.py --discover
        #   or visit each city's open data portal to confirm the FeatureServer URL.
        # Individual city failures are non-fatal — pipeline continues.
        "name": "Fetch US city permits (ArcGIS cities)",
        "cmd": [sys.executable, "backend/ingest/us_city_permits_arcgis.py"],
        "skip_key": "skip_arcgis_cities",
        "non_fatal": True,
    },
    {
        # Fetches CPS school performance ratings (SY2425 progress reports)
        # joined with school coordinates from the SY2324 profile dataset.
        # Stored in neighborhood_quality table (region_type='school').
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch IL school ratings (CPS)",
        "cmd": [sys.executable, "backend/ingest/il_school_ratings.py"],
        "skip_key": "skip_school_ratings",
        "non_fatal": True,
    },
    {
        "name": "Fill missing geocoordinates",
        "cmd": [sys.executable, "backend/ingest/geocode_fill.py"],
        "skip_key": "skip_geocode",
    },
    {
        "name": "Load projects into DB",
        "cmd": [sys.executable, "backend/ingest/load_projects.py", "--prune-days", "90"],
        "prune_args": True,
    },
    {
        # Loads neighborhood quality staging files (FEMA, crime, Census ACS)
        # into the neighborhood_quality table. Non-fatal: fails gracefully if
        # staging files are missing or DB table not yet created.
        "name": "Load neighborhood quality into DB",
        "cmd": [sys.executable, "backend/ingest/load_neighborhood_quality.py"],
        "skip_key": "skip_neighborhood_quality",
        "non_fatal": True,
        "dry_run_passthrough": True,
    },
]


def run_step(step: dict, args: argparse.Namespace) -> bool:
    """Run a single pipeline step. Returns True on success."""
    if step.get("skip_key") and getattr(args, step["skip_key"], False):
        print(f"\n── SKIP: {step['name']} ──────────────────────────────")
        return True

    cmd = list(step["cmd"])

    # Inject --prune-days into the load step if requested
    if step.get("prune_args") and args.prune_days is not None:
        # Replace the default --prune-days value
        try:
            idx = cmd.index("--prune-days")
            cmd[idx + 1] = str(args.prune_days)
        except ValueError:
            cmd += ["--prune-days", str(args.prune_days)]
    elif step.get("prune_args"):
        # Remove --prune-days if not requested
        try:
            idx = cmd.index("--prune-days")
            cmd.pop(idx)
            cmd.pop(idx)
        except ValueError:
            pass

    if args.dry_run and (step.get("prune_args") or step.get("dry_run_passthrough")):
        cmd.append("--dry-run")

    print(f"\n── {step['name']} ──────────────────────────────")
    print(f"   $ {' '.join(cmd)}")

    result = subprocess.run(cmd, check=False, env=_ENV)
    if result.returncode != 0:
        if step.get("non_fatal"):
            print(
                f"\nWARN: step '{step['name']}' failed with exit code {result.returncode}. "
                f"This step is non-fatal — continuing pipeline.",
                file=sys.stderr,
            )
            return True  # non-fatal: don't abort pipeline
        print(f"\nERROR: step '{step['name']}' failed with exit code {result.returncode}",
              file=sys.stderr)
        return False

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full LRE ingest pipeline against the live database."
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip the geocode_fill step (use if staging files already have coordinates).",
    )
    parser.add_argument(
        "--skip-il-cities",
        action="store_true",
        help="Skip the IL city permits fetch step (Cook County + cities).",
    )
    parser.add_argument(
        "--skip-us-cities",
        action="store_true",
        help="Skip the US city permits fetch step (top 10 US cities).",
    )
    parser.add_argument(
        "--skip-cta",
        action="store_true",
        help="Skip the CTA planned service alerts fetch step.",
    )
    parser.add_argument(
        "--skip-traffic-crashes",
        action="store_true",
        help="Skip the Chicago traffic crashes fetch step.",
    )
    parser.add_argument(
        "--skip-divvy",
        action="store_true",
        help="Skip the Divvy bike station closures fetch step.",
    )
    parser.add_argument(
        "--skip-311",
        action="store_true",
        help="Skip the Chicago 311 infrastructure requests fetch step.",
    )
    parser.add_argument(
        "--skip-film",
        action="store_true",
        help="Skip the Chicago film permits fetch step.",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="Skip the Chicago special events permits fetch step.",
    )
    parser.add_argument(
        "--skip-fema",
        action="store_true",
        help="Skip the FEMA flood zones fetch step.",
    )
    parser.add_argument(
        "--skip-crime-trends",
        action="store_true",
        help="Skip the Chicago crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-census-acs",
        action="store_true",
        help="Skip the Census ACS demographics fetch step.",
    )
    parser.add_argument(
        "--skip-austin-crime",
        action="store_true",
        help="Skip the Austin crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-seattle-crime",
        action="store_true",
        help="Skip the Seattle crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-nyc-crime",
        action="store_true",
        help="Skip the NYC crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-kc-crime",
        action="store_true",
        help="Skip the Kansas City crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-denver-crime",
        action="store_true",
        help="Skip the Denver crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-boston-crime",
        action="store_true",
        help="Skip the Boston crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-milwaukee-crime",
        action="store_true",
        help="Skip the Milwaukee crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-ckan-cities",
        action="store_true",
        help="Skip the CKAN city permits fetch step (Boston, Milwaukee, etc.).",
    )
    parser.add_argument(
        "--skip-arcgis-cities",
        action="store_true",
        help="Skip the ArcGIS city permits fetch step (Phoenix, Columbus, Minneapolis, Charlotte, Jacksonville).",
    )
    parser.add_argument(
        "--skip-school-ratings",
        action="store_true",
        help="Skip the IL school ratings fetch step (CPS).",
    )
    parser.add_argument(
        "--skip-neighborhood-quality",
        action="store_true",
        help="Skip the neighborhood quality DB load step.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data from APIs but do not write to the database.",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=90,
        metavar="N",
        help="Prune completed projects older than N days after loading (default: 90).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("══ DRY-RUN MODE: data will be fetched but not written to DB ══")

    print("══ LRE INGEST PIPELINE ═══════════════════════════════════════")

    failed: list[str] = []
    for step in STEPS:
        ok = run_step(step, args)
        if not ok:
            failed.append(step["name"])
            # Stop on failure — later steps depend on earlier outputs.
            print(f"\nPipeline aborted at step: {step['name']}", file=sys.stderr)
            break

    print("\n══ PIPELINE SUMMARY ══════════════════════════════════════════")
    if not failed:
        print("All steps completed successfully.")
        print("\nNext: verify live scoring at http://localhost:8000/score?address=<address>")
        print("      or check /health to confirm db_connection=true")
    else:
        print(f"Pipeline FAILED at: {failed[0]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
