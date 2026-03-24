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
from typing import Optional

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
        # Fetches Census ACS 5-year demographics for all census tracts in every
        # county containing an active permit city (29 counties, ~25 cities).
        # Stored in neighborhood_quality table (region_type='census_tract').
        # No API key required. Failures are non-fatal.
        "name": "Fetch Census ACS demographics (all active-permit counties)",
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
        # (Phoenix, Columbus, Minneapolis, Charlotte, Denver, Portland).
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
        # Fetches SFPD crime data and calculates 12-month trends by police district.
        # Source: data.sfgov.org (Socrata). Failures are non-fatal.
        "name": "Fetch San Francisco crime trends",
        "cmd": [sys.executable, "backend/ingest/sf_crime_trends.py"],
        "skip_key": "skip_sf_crime",
        "non_fatal": True,
    },
    {
        # Fetches BPD crime data and calculates 12-month trends by district.
        # Source: data.baltimorecity.gov (Socrata). Failures are non-fatal.
        "name": "Fetch Baltimore crime trends",
        "cmd": [sys.executable, "backend/ingest/baltimore_crime_trends.py"],
        "skip_key": "skip_baltimore_crime",
        "non_fatal": True,
    },
    {
        # Fetches Metro Nashville PD crime data and calculates 12-month trends by precinct.
        # Source: data.nashville.gov (Socrata). Failures are non-fatal.
        "name": "Fetch Nashville crime trends",
        "cmd": [sys.executable, "backend/ingest/nashville_crime_trends.py"],
        "skip_key": "skip_nashville_crime",
        "non_fatal": True,
    },
    {
        # Fetches Portland PPB crime data and calculates 12-month trends by precinct.
        # Source: ArcGIS FeatureServer. Failures are non-fatal.
        "name": "Fetch Portland crime trends",
        "cmd": [sys.executable, "backend/ingest/portland_crime_trends.py"],
        "skip_key": "skip_portland_crime",
        "non_fatal": True,
    },
    # -----------------------------------------------------------------
    # data-049: Tier-4 city crime trends (12 new cities)
    # -----------------------------------------------------------------
    {
        "name": "Fetch Washington DC crime trends",
        "cmd": [sys.executable, "backend/ingest/dc_crime_trends.py"],
        "skip_key": "skip_dc_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Oklahoma City crime trends",
        "cmd": [sys.executable, "backend/ingest/oklahoma_city_crime_trends.py"],
        "skip_key": "skip_okc_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch San Antonio crime trends",
        "cmd": [sys.executable, "backend/ingest/san_antonio_crime_trends.py"],
        "skip_key": "skip_san_antonio_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch San Diego crime trends",
        "cmd": [sys.executable, "backend/ingest/san_diego_crime_trends.py"],
        "skip_key": "skip_san_diego_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Memphis crime trends",
        "cmd": [sys.executable, "backend/ingest/memphis_crime_trends.py"],
        "skip_key": "skip_memphis_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Louisville crime trends",
        "cmd": [sys.executable, "backend/ingest/louisville_crime_trends.py"],
        "skip_key": "skip_louisville_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Fresno crime trends",
        "cmd": [sys.executable, "backend/ingest/fresno_crime_trends.py"],
        "skip_key": "skip_fresno_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Sacramento crime trends",
        "cmd": [sys.executable, "backend/ingest/sacramento_crime_trends.py"],
        "skip_key": "skip_sacramento_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Las Vegas crime trends",
        "cmd": [sys.executable, "backend/ingest/las_vegas_crime_trends.py"],
        "skip_key": "skip_las_vegas_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch El Paso crime trends",
        "cmd": [sys.executable, "backend/ingest/el_paso_crime_trends.py"],
        "skip_key": "skip_el_paso_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Tucson crime trends",
        "cmd": [sys.executable, "backend/ingest/tucson_crime_trends.py"],
        "skip_key": "skip_tucson_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Houston crime trends",
        "cmd": [sys.executable, "backend/ingest/houston_crime_trends.py"],
        "skip_key": "skip_houston_crime",
        "non_fatal": True,
    },
    # -----------------------------------------------------------------
    # data-050: Tier-5 city crime trends (10 new cities)
    # -----------------------------------------------------------------
    {
        "name": "Fetch Charlotte crime trends",
        "cmd": [sys.executable, "backend/ingest/charlotte_crime_trends.py"],
        "skip_key": "skip_charlotte_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Columbus crime trends",
        "cmd": [sys.executable, "backend/ingest/columbus_crime_trends.py"],
        "skip_key": "skip_columbus_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Minneapolis crime trends",
        "cmd": [sys.executable, "backend/ingest/minneapolis_crime_trends.py"],
        "skip_key": "skip_minneapolis_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Phoenix crime trends",
        "cmd": [sys.executable, "backend/ingest/phoenix_crime_trends.py"],
        "skip_key": "skip_phoenix_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch San Jose crime trends",
        "cmd": [sys.executable, "backend/ingest/san_jose_crime_trends.py"],
        "skip_key": "skip_san_jose_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Jacksonville crime trends",
        "cmd": [sys.executable, "backend/ingest/jacksonville_crime_trends.py"],
        "skip_key": "skip_jacksonville_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Fort Worth crime trends",
        "cmd": [sys.executable, "backend/ingest/fort_worth_crime_trends.py"],
        "skip_key": "skip_fort_worth_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Indianapolis crime trends",
        "cmd": [sys.executable, "backend/ingest/indianapolis_crime_trends.py"],
        "skip_key": "skip_indianapolis_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Albuquerque crime trends",
        "cmd": [sys.executable, "backend/ingest/albuquerque_crime_trends.py"],
        "skip_key": "skip_albuquerque_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Raleigh crime trends",
        "cmd": [sys.executable, "backend/ingest/raleigh_crime_trends.py"],
        "skip_key": "skip_raleigh_crime",
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
    # -----------------------------------------------------------------
    # data-056: Tier-6 city crime trends (10 new cities)
    # -----------------------------------------------------------------
    {
        "name": "Fetch Philadelphia crime trends",
        "cmd": [sys.executable, "backend/ingest/philadelphia_crime_trends.py"],
        "skip_key": "skip_philadelphia_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch New Orleans crime trends",
        "cmd": [sys.executable, "backend/ingest/new_orleans_crime_trends.py"],
        "skip_key": "skip_new_orleans_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Atlanta crime trends",
        "cmd": [sys.executable, "backend/ingest/atlanta_crime_trends.py"],
        "skip_key": "skip_atlanta_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Detroit crime trends",
        "cmd": [sys.executable, "backend/ingest/detroit_crime_trends.py"],
        "skip_key": "skip_detroit_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Cleveland crime trends",
        "cmd": [sys.executable, "backend/ingest/cleveland_crime_trends.py"],
        "skip_key": "skip_cleveland_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Cincinnati crime trends",
        "cmd": [sys.executable, "backend/ingest/cincinnati_crime_trends.py"],
        "skip_key": "skip_cincinnati_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Buffalo crime trends",
        "cmd": [sys.executable, "backend/ingest/buffalo_crime_trends.py"],
        "skip_key": "skip_buffalo_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Providence crime trends",
        "cmd": [sys.executable, "backend/ingest/providence_crime_trends.py"],
        "skip_key": "skip_providence_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Omaha crime trends",
        "cmd": [sys.executable, "backend/ingest/omaha_crime_trends.py"],
        "skip_key": "skip_omaha_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Pittsburgh crime trends",
        "cmd": [sys.executable, "backend/ingest/pittsburgh_crime_trends.py"],
        "skip_key": "skip_pittsburgh_crime",
        "non_fatal": True,
    },
    # -----------------------------------------------------------------
    # data-057: Tier-7 city crime trends (17 new cities)
    # Socrata-based: Tampa, Miami-Dade, St. Louis, Baton Rouge, Lexington
    # ArcGIS-based: Orlando, Richmond, Des Moines, Tulsa, Wichita,
    #   Colorado Springs, Arlington TX, Virginia Beach, Mesa, Aurora,
    #   Corpus Christi, Greensboro
    # Skipped (no public API): Bakersfield, Anaheim, Santa Ana
    # -----------------------------------------------------------------
    {
        "name": "Fetch Tampa crime trends",
        "cmd": [sys.executable, "backend/ingest/tampa_crime_trends.py"],
        "skip_key": "skip_tampa_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Miami-Dade crime trends",
        "cmd": [sys.executable, "backend/ingest/miami_crime_trends.py"],
        "skip_key": "skip_miami_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch St. Louis crime trends",
        "cmd": [sys.executable, "backend/ingest/st_louis_crime_trends.py"],
        "skip_key": "skip_st_louis_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Baton Rouge crime trends",
        "cmd": [sys.executable, "backend/ingest/baton_rouge_crime_trends.py"],
        "skip_key": "skip_baton_rouge_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Lexington crime trends",
        "cmd": [sys.executable, "backend/ingest/lexington_crime_trends.py"],
        "skip_key": "skip_lexington_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Orlando crime trends",
        "cmd": [sys.executable, "backend/ingest/orlando_crime_trends.py"],
        "skip_key": "skip_orlando_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Richmond crime trends",
        "cmd": [sys.executable, "backend/ingest/richmond_crime_trends.py"],
        "skip_key": "skip_richmond_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Des Moines crime trends",
        "cmd": [sys.executable, "backend/ingest/des_moines_crime_trends.py"],
        "skip_key": "skip_des_moines_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Tulsa crime trends",
        "cmd": [sys.executable, "backend/ingest/tulsa_crime_trends.py"],
        "skip_key": "skip_tulsa_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Wichita crime trends",
        "cmd": [sys.executable, "backend/ingest/wichita_crime_trends.py"],
        "skip_key": "skip_wichita_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Colorado Springs crime trends",
        "cmd": [sys.executable, "backend/ingest/colorado_springs_crime_trends.py"],
        "skip_key": "skip_colorado_springs_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Arlington TX crime trends",
        "cmd": [sys.executable, "backend/ingest/arlington_tx_crime_trends.py"],
        "skip_key": "skip_arlington_tx_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Virginia Beach crime trends",
        "cmd": [sys.executable, "backend/ingest/virginia_beach_crime_trends.py"],
        "skip_key": "skip_virginia_beach_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Mesa crime trends",
        "cmd": [sys.executable, "backend/ingest/mesa_crime_trends.py"],
        "skip_key": "skip_mesa_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Aurora crime trends",
        "cmd": [sys.executable, "backend/ingest/aurora_crime_trends.py"],
        "skip_key": "skip_aurora_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Corpus Christi crime trends",
        "cmd": [sys.executable, "backend/ingest/corpus_christi_crime_trends.py"],
        "skip_key": "skip_corpus_christi_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Greensboro crime trends",
        "cmd": [sys.executable, "backend/ingest/greensboro_crime_trends.py"],
        "skip_key": "skip_greensboro_crime",
        "non_fatal": True,
    },
    # -----------------------------------------------------------------
    # data-058: Tier-8 city crime trends
    # Socrata: Anchorage, Madison, Spokane
    # ArcGIS:  Durham, Chandler, Scottsdale, Gilbert, Glendale AZ, Henderson NV
    # CSV:     St. Louis (rewrite — SLMPD CSV at slmpd.org/stats/)
    # Skipped (no public API): Hialeah FL, Laredo TX, North Las Vegas NV,
    #   Boise ID, Richmond CA, Fremont CA, Irvine CA, San Bernardino CA,
    #   Modesto CA, Fontana CA, Moreno Valley CA, Lubbock TX, Garland TX,
    #   Chesapeake VA
    # -----------------------------------------------------------------
    {
        "name": "Fetch Anchorage crime trends",
        "cmd": [sys.executable, "backend/ingest/anchorage_crime_trends.py"],
        "skip_key": "skip_anchorage_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Madison crime trends",
        "cmd": [sys.executable, "backend/ingest/madison_crime_trends.py"],
        "skip_key": "skip_madison_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Spokane crime trends",
        "cmd": [sys.executable, "backend/ingest/spokane_crime_trends.py"],
        "skip_key": "skip_spokane_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Durham crime trends",
        "cmd": [sys.executable, "backend/ingest/durham_crime_trends.py"],
        "skip_key": "skip_durham_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Chandler crime trends",
        "cmd": [sys.executable, "backend/ingest/chandler_crime_trends.py"],
        "skip_key": "skip_chandler_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Scottsdale crime trends",
        "cmd": [sys.executable, "backend/ingest/scottsdale_crime_trends.py"],
        "skip_key": "skip_scottsdale_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Gilbert crime trends",
        "cmd": [sys.executable, "backend/ingest/gilbert_crime_trends.py"],
        "skip_key": "skip_gilbert_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Glendale AZ crime trends",
        "cmd": [sys.executable, "backend/ingest/glendale_az_crime_trends.py"],
        "skip_key": "skip_glendale_az_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Henderson NV crime trends",
        "cmd": [sys.executable, "backend/ingest/henderson_crime_trends.py"],
        "skip_key": "skip_henderson_crime",
        "non_fatal": True,
    },
    {
        # St. Louis rewritten to use SLMPD CSV files (slmpd.org/stats/).
        # Old Socrata stub (data.stlouis-mo.gov) redirects and is not Socrata.
        "name": "Fetch St. Louis crime trends (SLMPD CSV)",
        "cmd": [sys.executable, "backend/ingest/st_louis_crime_trends.py"],
        "skip_key": "skip_st_louis_crime",
        "non_fatal": True,
    },
    # -----------------------------------------------------------------
    # data-059: Tier-9 city crime trends (5 new cities)
    # ArcGIS: Tacoma, Chattanooga, Grand Rapids, Fayetteville NC
    # OpenDataSoft: Cary NC
    # Skipped (no public API): Akron OH, Knoxville TN, Fort Wayne IN,
    #   Shreveport LA, Tallahassee FL, Huntsville AL, Winston-Salem NC
    # -----------------------------------------------------------------
    {
        "name": "Fetch Tacoma crime trends",
        "cmd": [sys.executable, "backend/ingest/tacoma_crime_trends.py"],
        "skip_key": "skip_tacoma_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Chattanooga crime trends",
        "cmd": [sys.executable, "backend/ingest/chattanooga_crime_trends.py"],
        "skip_key": "skip_chattanooga_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Grand Rapids crime trends",
        "cmd": [sys.executable, "backend/ingest/grand_rapids_crime_trends.py"],
        "skip_key": "skip_grand_rapids_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Fayetteville NC crime trends",
        "cmd": [sys.executable, "backend/ingest/fayetteville_nc_crime_trends.py"],
        "skip_key": "skip_fayetteville_nc_crime",
        "non_fatal": True,
    },
    {
        "name": "Fetch Cary NC crime trends",
        "cmd": [sys.executable, "backend/ingest/cary_crime_trends.py"],
        "skip_key": "skip_cary_crime",
        "non_fatal": True,
    },
    {
        # data-053: Fetches public school locations for all active cities using
        # NCES Common Core of Data via the Urban Institute Education Data API.
        # Free, no API key required. Covers 34 cities (Chicago excluded — CPS
        # data with richer ratings is handled by il_school_ratings.py).
        # school_rating/attainment/growth are null; state report card
        # integration is tracked in data-054.
        "name": "Fetch national school ratings (NCES CCD)",
        "cmd": [sys.executable, "backend/ingest/national_school_ratings.py"],
        "skip_key": "skip_national_school_ratings",
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
    {
        # data-041: Row-count regression check.
        # Alerts if active project count drops >20% vs prior successful run.
        # Non-fatal so the pipeline still exits 0 on transient anomalies;
        # the check prints a clear REGRESSION DETECTED message to stderr
        # which surfaces in GitHub Actions logs.
        "name": "Row-count regression check",
        "cmd": [sys.executable, "backend/ingest/row_count_check.py"],
        "skip_key": "skip_row_count_check",
        "non_fatal": True,
    },
]


# ---------------------------------------------------------------------------
# Ingest run tracking  (data-041)
# Writes to the ingest_runs table so /health/db can report freshness and
# so the regression check can compare current vs prior record counts.
# All DB calls are best-effort — failures are logged but never abort the pipeline.
# ---------------------------------------------------------------------------

def _get_db_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or None


def _record_run_start(db_url: str) -> Optional[int]:
    """Insert a 'running' row into ingest_runs. Returns the new row ID."""
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingest_runs (source, status) VALUES (%s, %s) RETURNING id",
                ("pipeline", "running"),
            )
            row_id = cur.fetchone()[0]
        conn.close()
        return row_id
    except Exception as exc:
        print(f"WARN: could not record ingest run start: {exc}", file=sys.stderr)
        return None


def _check_regression_and_finish(
    db_url: str, run_id: Optional[int], failed_step: Optional[str]
) -> None:
    """
    Query active project count, compare against the previous successful run,
    then write the final status to ingest_runs.

    Exits with code 1 if:
      - a pipeline step already failed (failed_step is set), OR
      - active project count dropped >20% compared to the prior run.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            current_count: int = cur.fetchone()[0]

            # Last *finished* successful run (the current run is still 'running')
            cur.execute(
                """SELECT record_count FROM ingest_runs
                   WHERE status = 'success' AND record_count IS NOT NULL
                   ORDER BY finished_at DESC LIMIT 1"""
            )
            prior_row = cur.fetchone()

        regression_error: Optional[str] = None
        if prior_row is not None:
            prior_count: int = prior_row[0]
            if prior_count > 0:
                drop_pct = (prior_count - current_count) / prior_count * 100
                if drop_pct > 20:
                    regression_error = (
                        f"Active project count dropped {drop_pct:.1f}% "
                        f"(was {prior_count}, now {current_count}). "
                        f">20% regression threshold exceeded."
                    )
                    print(f"ERROR: {regression_error}", file=sys.stderr)
                elif drop_pct > 0:
                    print(
                        f"Row count: {current_count} active projects "
                        f"(down {drop_pct:.1f}% from {prior_count} — within 20% threshold)."
                    )
                else:
                    print(
                        f"Row count: {current_count} active projects "
                        f"(up from {prior_count})."
                    )
            else:
                print(f"Row count: {current_count} active projects.")
        else:
            print(f"Row count: {current_count} active projects (no prior run to compare).")

        # Determine final status
        if failed_step:
            final_status = "failed"
            error_msg = f"Pipeline aborted at step: {failed_step}"
        elif regression_error:
            final_status = "failed"
            error_msg = regression_error
        else:
            final_status = "success"
            error_msg = None

        # Write final row
        with conn.cursor() as cur:
            if run_id is not None:
                cur.execute(
                    """UPDATE ingest_runs
                       SET finished_at = now(), status = %s, record_count = %s, error_msg = %s
                       WHERE id = %s""",
                    (final_status, current_count, error_msg, run_id),
                )
            else:
                cur.execute(
                    """INSERT INTO ingest_runs (source, finished_at, status, record_count, error_msg)
                       VALUES (%s, now(), %s, %s, %s)""",
                    ("pipeline", final_status, current_count, error_msg),
                )
        conn.close()

        if final_status == "failed":
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"WARN: could not record ingest run finish: {exc}", file=sys.stderr)
        # Still exit 1 if a step failed
        if failed_step:
            sys.exit(1)


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
        help="Skip the ArcGIS city permits fetch step (Phoenix, Columbus, Minneapolis, Charlotte, Denver, Portland).",
    )
    parser.add_argument(
        "--skip-sf-crime",
        action="store_true",
        help="Skip the San Francisco crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-baltimore-crime",
        action="store_true",
        help="Skip the Baltimore crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-nashville-crime",
        action="store_true",
        help="Skip the Nashville crime trends fetch step.",
    )
    parser.add_argument(
        "--skip-portland-crime",
        action="store_true",
        help="Skip the Portland crime trends fetch step.",
    )
    # data-049: Tier-4 city crime trends skip flags
    parser.add_argument("--skip-dc-crime", action="store_true", help="Skip the DC crime trends fetch step.")
    parser.add_argument("--skip-okc-crime", action="store_true", help="Skip the Oklahoma City crime trends fetch step.")
    parser.add_argument("--skip-san-antonio-crime", action="store_true", help="Skip the San Antonio crime trends fetch step.")
    parser.add_argument("--skip-san-diego-crime", action="store_true", help="Skip the San Diego crime trends fetch step.")
    parser.add_argument("--skip-memphis-crime", action="store_true", help="Skip the Memphis crime trends fetch step.")
    parser.add_argument("--skip-louisville-crime", action="store_true", help="Skip the Louisville crime trends fetch step.")
    parser.add_argument("--skip-fresno-crime", action="store_true", help="Skip the Fresno crime trends fetch step.")
    parser.add_argument("--skip-sacramento-crime", action="store_true", help="Skip the Sacramento crime trends fetch step.")
    parser.add_argument("--skip-las-vegas-crime", action="store_true", help="Skip the Las Vegas crime trends fetch step.")
    parser.add_argument("--skip-el-paso-crime", action="store_true", help="Skip the El Paso crime trends fetch step.")
    parser.add_argument("--skip-tucson-crime", action="store_true", help="Skip the Tucson crime trends fetch step.")
    parser.add_argument("--skip-houston-crime", action="store_true", help="Skip the Houston crime trends fetch step.")
    # data-050: Tier-5 city crime trends skip flags
    parser.add_argument("--skip-charlotte-crime", action="store_true", help="Skip the Charlotte crime trends fetch step.")
    parser.add_argument("--skip-columbus-crime", action="store_true", help="Skip the Columbus crime trends fetch step.")
    parser.add_argument("--skip-minneapolis-crime", action="store_true", help="Skip the Minneapolis crime trends fetch step.")
    parser.add_argument("--skip-phoenix-crime", action="store_true", help="Skip the Phoenix crime trends fetch step.")
    parser.add_argument("--skip-san-jose-crime", action="store_true", help="Skip the San Jose crime trends fetch step.")
    parser.add_argument("--skip-jacksonville-crime", action="store_true", help="Skip the Jacksonville crime trends fetch step.")
    parser.add_argument("--skip-fort-worth-crime", action="store_true", help="Skip the Fort Worth crime trends fetch step.")
    parser.add_argument("--skip-indianapolis-crime", action="store_true", help="Skip the Indianapolis crime trends fetch step.")
    parser.add_argument("--skip-albuquerque-crime", action="store_true", help="Skip the Albuquerque crime trends fetch step.")
    parser.add_argument("--skip-raleigh-crime", action="store_true", help="Skip the Raleigh crime trends fetch step.")
    # data-056: Tier-6 city crime trends skip flags
    parser.add_argument("--skip-philadelphia-crime", action="store_true", help="Skip the Philadelphia crime trends fetch step.")
    parser.add_argument("--skip-new-orleans-crime", action="store_true", help="Skip the New Orleans crime trends fetch step.")
    parser.add_argument("--skip-atlanta-crime", action="store_true", help="Skip the Atlanta crime trends fetch step.")
    parser.add_argument("--skip-detroit-crime", action="store_true", help="Skip the Detroit crime trends fetch step.")
    parser.add_argument("--skip-cleveland-crime", action="store_true", help="Skip the Cleveland crime trends fetch step.")
    parser.add_argument("--skip-cincinnati-crime", action="store_true", help="Skip the Cincinnati crime trends fetch step.")
    parser.add_argument("--skip-buffalo-crime", action="store_true", help="Skip the Buffalo crime trends fetch step.")
    parser.add_argument("--skip-providence-crime", action="store_true", help="Skip the Providence crime trends fetch step.")
    parser.add_argument("--skip-omaha-crime", action="store_true", help="Skip the Omaha crime trends fetch step.")
    parser.add_argument("--skip-pittsburgh-crime", action="store_true", help="Skip the Pittsburgh crime trends fetch step.")
    # data-057: Tier-7 city crime trends skip flags
    parser.add_argument("--skip-tampa-crime", action="store_true", help="Skip the Tampa crime trends fetch step.")
    parser.add_argument("--skip-miami-crime", action="store_true", help="Skip the Miami-Dade crime trends fetch step.")
    parser.add_argument("--skip-st-louis-crime", action="store_true", help="Skip the St. Louis crime trends fetch step.")
    parser.add_argument("--skip-baton-rouge-crime", action="store_true", help="Skip the Baton Rouge crime trends fetch step.")
    parser.add_argument("--skip-lexington-crime", action="store_true", help="Skip the Lexington crime trends fetch step.")
    parser.add_argument("--skip-orlando-crime", action="store_true", help="Skip the Orlando crime trends fetch step.")
    parser.add_argument("--skip-richmond-crime", action="store_true", help="Skip the Richmond crime trends fetch step.")
    parser.add_argument("--skip-des-moines-crime", action="store_true", help="Skip the Des Moines crime trends fetch step.")
    parser.add_argument("--skip-tulsa-crime", action="store_true", help="Skip the Tulsa crime trends fetch step.")
    parser.add_argument("--skip-wichita-crime", action="store_true", help="Skip the Wichita crime trends fetch step.")
    parser.add_argument("--skip-colorado-springs-crime", action="store_true", help="Skip the Colorado Springs crime trends fetch step.")
    parser.add_argument("--skip-arlington-tx-crime", action="store_true", help="Skip the Arlington TX crime trends fetch step.")
    parser.add_argument("--skip-virginia-beach-crime", action="store_true", help="Skip the Virginia Beach crime trends fetch step.")
    parser.add_argument("--skip-mesa-crime", action="store_true", help="Skip the Mesa crime trends fetch step.")
    parser.add_argument("--skip-aurora-crime", action="store_true", help="Skip the Aurora crime trends fetch step.")
    parser.add_argument("--skip-corpus-christi-crime", action="store_true", help="Skip the Corpus Christi crime trends fetch step.")
    parser.add_argument("--skip-greensboro-crime", action="store_true", help="Skip the Greensboro crime trends fetch step.")
    # data-058: tier-8 cities
    parser.add_argument("--skip-anchorage-crime", action="store_true", help="Skip the Anchorage crime trends fetch step.")
    parser.add_argument("--skip-madison-crime", action="store_true", help="Skip the Madison crime trends fetch step.")
    parser.add_argument("--skip-spokane-crime", action="store_true", help="Skip the Spokane crime trends fetch step.")
    parser.add_argument("--skip-durham-crime", action="store_true", help="Skip the Durham crime trends fetch step.")
    parser.add_argument("--skip-chandler-crime", action="store_true", help="Skip the Chandler crime trends fetch step.")
    parser.add_argument("--skip-scottsdale-crime", action="store_true", help="Skip the Scottsdale crime trends fetch step.")
    parser.add_argument("--skip-gilbert-crime", action="store_true", help="Skip the Gilbert crime trends fetch step.")
    parser.add_argument("--skip-glendale-az-crime", action="store_true", help="Skip the Glendale AZ crime trends fetch step.")
    parser.add_argument("--skip-henderson-crime", action="store_true", help="Skip the Henderson crime trends fetch step.")
    # data-059: tier-9 cities
    parser.add_argument("--skip-tacoma-crime", action="store_true", help="Skip the Tacoma crime trends fetch step.")
    parser.add_argument("--skip-chattanooga-crime", action="store_true", help="Skip the Chattanooga crime trends fetch step.")
    parser.add_argument("--skip-grand-rapids-crime", action="store_true", help="Skip the Grand Rapids crime trends fetch step.")
    parser.add_argument("--skip-fayetteville-nc-crime", action="store_true", help="Skip the Fayetteville NC crime trends fetch step.")
    parser.add_argument("--skip-cary-crime", action="store_true", help="Skip the Cary NC crime trends fetch step.")
    parser.add_argument(
        "--skip-school-ratings",
        action="store_true",
        help="Skip the IL school ratings fetch step (CPS).",
    )
    parser.add_argument(
        "--skip-national-school-ratings",
        action="store_true",
        help="Skip the national school ratings fetch step (NCES CCD via Urban Institute API).",
    )
    parser.add_argument(
        "--skip-neighborhood-quality",
        action="store_true",
        help="Skip the neighborhood quality DB load step.",
    )
    parser.add_argument(
        "--skip-row-count-check",
        action="store_true",
        help="Skip the post-ingest row-count regression check.",
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

    # Record pipeline start in ingest_runs (best-effort; skipped on dry-run)
    db_url = _get_db_url()
    run_id: Optional[int] = None
    if db_url and not args.dry_run:
        run_id = _record_run_start(db_url)

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

    # Record final status + regression check (best-effort; skipped on dry-run)
    if db_url and not args.dry_run:
        _check_regression_and_finish(
            db_url,
            run_id,
            failed_step=failed[0] if failed else None,
        )
    elif failed:
        print(f"Pipeline FAILED at: {failed[0]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
