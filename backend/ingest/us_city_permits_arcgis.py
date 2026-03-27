"""
backend/ingest/us_city_permits_arcgis.py
task: data-046, data-047, data-048
lane: data

ArcGIS REST FeatureServer ingest for building permits in cities that publish
open data via ArcGIS Hub or ArcGIS Server (not Socrata or CKAN).

Supported cities:
  - Phoenix     (maps.phoenix.gov — ArcGIS MapServer)
  - Columbus    (opendata.columbus.gov — ArcGIS Hub)
  - Minneapolis (opendata.minneapolismn.gov — ArcGIS Hub)
  - Charlotte   (meckgis.mecklenburgcountync.gov — ArcGIS FeatureServer)
  - Denver      (opendata-geospatialdenver.hub.arcgis.com — ArcGIS Hub) [data-047]
  - Portland    (gis.portlandoregon.gov — ArcGIS Hub) [data-047]
  - Baltimore   (egisdata.baltimorecity.gov — ArcGIS Server) [data-048]
  - Nashville   (services2.arcgis.com — ArcGIS Hub) [data-048]

ArcGIS REST FeatureServer query pattern:
  GET {service_url}/query
      ?where=<SQL_WHERE>&outFields=*&f=json
      &resultOffset=<N>&resultRecordCount=<page_size>

  Response format (f=json):
    {
      "features": [
        {
          "attributes": { "permit_number": "...", "issue_date": ... },
          "geometry": { "x": <lon>, "y": <lat> }
        }
      ],
      "exceededTransferLimit": true|false
    }

  Geometry uses the service's spatial reference; most ArcGIS Hub services
  support outSR=4326 to request WGS-84 (lat/lon) directly.

NOTE ON SERVICE URLS:
  Service URLs below are researched estimates as of 2026-03-22.
  ArcGIS Hub service URLs can be verified by:
  1. Visit the city's open data portal (listed in CITY_CONFIGS).
  2. Search "building permits" and open the dataset page.
  3. Click "API" or "View API" to get the FeatureServer URL.
  4. Or run: python backend/ingest/us_city_permits_arcgis.py --city <city> --discover
     (queries ArcGIS Hub REST API for datasets matching "building permits")

  If a service_url returns HTTP 400 or 404:
  1. Visit the city's open data portal
  2. Search for "building permits" or "construction permits"
  3. Open the dataset and click "I want to use this" → "API Explorer"
  4. Copy the FeatureServer endpoint and update service_url below.

  If the service returns 0 records but no error, verify:
  - The where clause date field name matches the service's actual field name.
  - Run --dry-run to see the raw response and field names.

Usage:
  # Ingest all configured cities
  python backend/ingest/us_city_permits_arcgis.py

  # Ingest a single city
  python backend/ingest/us_city_permits_arcgis.py --city phoenix
  python backend/ingest/us_city_permits_arcgis.py --city columbus

  # Dry-run (fetch one page only; do not write output files)
  python backend/ingest/us_city_permits_arcgis.py --dry-run
  python backend/ingest/us_city_permits_arcgis.py --city phoenix --dry-run

  # Discover ArcGIS Hub datasets for a city (queries ArcGIS Hub REST API)
  python backend/ingest/us_city_permits_arcgis.py --city phoenix --discover

  # List configured cities
  python backend/ingest/us_city_permits_arcgis.py --list

Acceptance criteria (data-046):
  - Records are fetched from each ArcGIS FeatureServer.
  - Raw records are written to data/raw/us_city_permits_<source_key>.json.
  - Output schema matches Socrata/CKAN scripts for downstream compatibility.
  - Individual city failures are non-fatal; other cities continue.
  - --dry-run mode fetches one page per city and reports without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# City configurations
# ---------------------------------------------------------------------------
# Each entry describes one ArcGIS FeatureServer source.
#
# Fields:
#   city_name       : Human-readable city label
#   source_key      : Snake-case identifier used in output filename
#   service_url     : ArcGIS FeatureServer layer URL (ending in /FeatureServer/0)
#   portal_url      : Open data portal homepage (for humans verifying endpoints)
#   id_field        : Field name for unique permit ID in the attributes dict
#   type_field      : Field name for permit type / work class
#   desc_field      : Field name for work description
#   issue_date_field: Field name for permit issue date (used for date filter)
#   exp_date_field  : Field name for expiration date (None if unavailable)
#   addr_field      : Field name for address string
#   city_state      : City + state for context
#   date_filter_sql : SQL WHERE snippet for date filtering (None = use default)
#                     Set to None to use the default epoch-ms filter on issue_date_field.
#   skip_date_filter: If True, no date WHERE clause is applied (use max_records cap).
#   max_records     : Cap on records fetched (used when skip_date_filter=True).

CITY_CONFIGS: list[dict] = [
    {
        # Phoenix, AZ — Planning Permits.
        # Server: maps.phoenix.gov (MapServer — supports same query API as FeatureServer)
        # Verified 2026-03-22 via direct query.
        # Note: phoenixopendata.com redirects to ArcGIS Hub but the actual
        # permit layer is on maps.phoenix.gov, NOT gismaps.phoenix.gov.
        "city_name":        "Phoenix",
        "source_key":       "phoenix",
        "service_url":      (
            "https://maps.phoenix.gov/pub/rest/services"
            "/Public/Planning_Permit/MapServer/1"
        ),
        "portal_url":       "https://www.phoenixopendata.com",
        "id_field":         "PER_NUM",
        "type_field":       "PER_TYPE_DESC",
        "desc_field":       "SCOPE_DESC",
        "issue_date_field": "PER_ISSUE_DATE",
        "exp_date_field":   "PER_EXPIRE_DATE",
        "addr_field":       "STREET_FULL_NAME",
        "city_state":       "Phoenix, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Columbus, OH — Building Permits.
        # Portal: https://opendata.columbus.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Columbus",
        "source_key":       "columbus",
        "service_url":      (
            "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.columbus.gov",
        "id_field":         "B1_ALT_ID",
        "type_field":       "B1_PER_TYPE",
        "desc_field":       "B1_PER_SUB_TYPE",
        "issue_date_field": "ISSUED_DT",
        "exp_date_field":   None,
        "addr_field":       "SITE_ADDRESS",
        "city_state":       "Columbus, OH",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Minneapolis, MN — CCS Permits.
        # Portal: https://opendata.minneapolismn.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Minneapolis",
        "source_key":       "minneapolis",
        "service_url":      (
            "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services"
            "/CCS_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.minneapolismn.gov",
        "id_field":         "permitNumber",
        "type_field":       "permitType",
        "desc_field":       "comments",
        "issue_date_field": "issueDate",
        "exp_date_field":   None,
        "addr_field":       "Display",
        "city_state":       "Minneapolis, MN",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Charlotte, NC (Mecklenburg County) — Building Permits.
        # Server: meckgis.mecklenburgcountync.gov
        # FeatureServer verified 2026-03-22.
        "city_name":        "Charlotte",
        "source_key":       "charlotte",
        "service_url":      (
            "https://meckgis.mecklenburgcountync.gov/server/rest/services"
            "/BuildingPermits/FeatureServer/0"
        ),
        "portal_url":       "https://data.charlottenc.gov",
        "id_field":         "permitnum",
        "type_field":       "permittype",
        "desc_field":       "workdesc",
        "issue_date_field": "issuedate",
        "exp_date_field":   None,
        "addr_field":       "projadd",
        "city_state":       "Charlotte, NC",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Denver, CO — Residential Construction Permits (verified 2026-03-25).
        # Portal: https://opendata-geospatialdenver.hub.arcgis.com
        # Org zdB7qR0BtYrg0Xpl — service ODC_DEV_RESIDENTIALCONSTPERMIT_P, layer 316.
        # 77,484 records. Also available: ODC_DEV_COMMERCIALCONSTPERMIT_P (commercial),
        # ODC_DEV_DEMOLITIONPERMIT_P (demolition).
        "city_name":        "Denver",
        "source_key":       "denver",
        "service_url":      (
            "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services"
            "/ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316"
        ),
        "portal_url":       "https://opendata-geospatialdenver.hub.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "CLASS",
        "desc_field":       "CLASS",
        "issue_date_field": "DATE_ISSUED",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Denver, CO",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Portland, OR — Building Permits.
        # Portland, OR — BDS Construction Permit Metrics (verified 2026-03-25).
        # Org quVN97tn06YNGj9s — service BDS_Construction_Permit_Metric, layer 0.
        # 49,091 records. Note: no street address field — PORTLAND_MAPS_URL used as placeholder.
        "city_name":        "Portland",
        "source_key":       "portland",
        "service_url":      (
            "https://services.arcgis.com/quVN97tn06YNGj9s/arcgis/rest/services"
            "/BDS_Construction_Permit_Metric/FeatureServer/0"
        ),
        "portal_url":       "https://gis.portlandoregon.gov",
        "id_field":         "FOLDER_RSN",
        "type_field":       "FOLDER_TYPE",
        "desc_field":       "WORK_TYPE",
        "issue_date_field": "APPROVED_TO_ISSUE_DATE",
        "exp_date_field":   None,
        "addr_field":       "PORTLAND_MAPS_URL",
        "city_state":       "Portland, OR",
        "skip_date_filter": True,  # date fields return 0 with TIMESTAMP filter
        "max_records":      None,
    },
    {
        # Baltimore, MD — Building Permits (DHCD Open Baltimore Datasets).
        # Server: egisdata.baltimorecity.gov (ArcGIS Server)
        # Verified 2026-03-23 via direct query (276k records).
        # Note: data.baltimorecity.gov now redirects to ArcGIS Hub.
        # Native SR is Maryland State Plane (WKID 2248); use outSR=4326.
        "city_name":        "Baltimore",
        "source_key":       "baltimore",
        "service_url":      (
            "https://egisdata.baltimorecity.gov/egis/rest/services"
            "/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer/3"
        ),
        "portal_url":       "https://data.baltimorecity.gov",
        "id_field":         "CaseNumber",
        "type_field":       "Description",
        "desc_field":       "Description",
        "issue_date_field": "IssuedDate",
        "exp_date_field":   "ExpirationDate",
        "addr_field":       "Address",
        "city_state":       "Baltimore, MD",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Nashville, TN — Building Permits Issued.
        # Server: services2.arcgis.com (ArcGIS Online hosted)
        # Verified 2026-03-23 via direct query (29k records).
        # Note: data.nashville.gov now redirects to ArcGIS Hub.
        "city_name":        "Nashville",
        "source_key":       "nashville",
        "service_url":      (
            "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services"
            "/Building_Permits_Issued_2/FeatureServer/0"
        ),
        "portal_url":       "https://data.nashville.gov",
        "id_field":         "Permit__",
        "type_field":       "Permit_Type_Description",
        "desc_field":       "Purpose",
        "issue_date_field": "Date_Issued",
        "exp_date_field":   None,
        "addr_field":       "Address",
        "city_state":       "Nashville, TN",
        "skip_date_filter": False,
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # REMOVED — Las Vegas (2026-03-27):
    #   Org VIkzGEMZbaSsMGLk returns 0 services on all subdomains.
    #   gis.lasvegasnevada.gov does not resolve. ArcGIS Hub portal
    #   search returns no permit datasets. No public permit API found.
    # REMOVED — El Paso (2026-03-27):
    #   Real data exists at gis.elpasotexas.gov Planning/NewResidential
    #   (42,472 records, MapServer/1) but the server blocks python-requests
    #   User-Agent with HTTP 403 (Cloudflare/WAF). FeatureServer also 403.
    #   curl works but automated ingest is not possible without UA spoofing.
    # -----------------------------------------------------------------
    {
        # Tucson, AZ — Residential Permits (verified 2026-03-25).
        # Self-hosted ArcGIS Server at gis.tucsonaz.gov (NOT gisdata.tucsonaz.gov which is Hub).
        # Service: PDSD/pdsdMain_General5/MapServer, layer 49 (Residential Permits).
        # 1,003 records. Also available: layer 48 (Commercial), layer 58 (Demolition).
        "city_name":        "Tucson",
        "source_key":       "tucson",
        "service_url":      (
            "https://gis.tucsonaz.gov/arcgis/rest/services"
            "/PDSD/pdsdMain_General5/MapServer/49"
        ),
        "portal_url":       "https://gisdata.tucsonaz.gov",
        "id_field":         "NUMBER",
        "type_field":       "TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "DATEISSUED",
        "exp_date_field":   "DATEEXPIRED",
        "addr_field":       "ADDRESSFULL",
        "city_state":       "Tucson, AZ",
        "skip_date_filter": True,  # MapServer date fields return 0 with TIMESTAMP filter
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # REMOVED — Jacksonville (verified 2026-03-22):
    #   maps.coj.net and gis.coj.net both return 404. No building permit
    #   FeatureServer found on ArcGIS Online either.
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — San Jose (2026-03-25):
    #   Org p8Tul9YqBFRRdPqD returns 0 services on all subdomains
    #   (services, services1-6). No public permit FeatureServer found.
    # REMOVED — Fort Worth (2026-03-25):
    #   Org AHCzmZstRKFEQEqv returns 0 services on all subdomains.
    #   No public permit FeatureServer found.
    # REMOVED — Albuquerque (2026-03-25):
    #   Org 3HnGBxB8VqLCXhUn returns 0 services on all subdomains.
    #   No public permit FeatureServer found.
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — data-057 tier-7 cities (2026-03-27, data-076):
    #   All 12 configs returned HTTP 400 "Invalid URL" in every pipeline run.
    #   Service names were guessed placeholders ("Building_Permits/FeatureServer/0")
    #   that do not match the actual ArcGIS service names for these orgs.
    #   Org IDs may be valid (same orgs used in crime-trends scripts) but
    #   real service names require live verification with network access.
    #
    #   To re-enable a city:
    #     1. curl https://services{N}.arcgis.com/{ORG}/arcgis/rest/services?f=json \
    #            | python3 -c "import sys,json; [print(s['name']) for s in json.load(sys.stdin).get('services',[])]"
    #     2. Find the permit-related service name from the output
    #     3. Add a config entry with the correct service_url
    #     4. Run: python backend/ingest/us_city_permits_arcgis.py --city <key> --dry-run
    #
    #   City reference (org IDs + portals):
    #     orlando:          services1.arcgis.com/ySBMu4XsNZMHPCce  portal: data-cityoforlando.opendata.arcgis.com
    #     richmond:         services1.arcgis.com/k3vhq11XkBNeeOfM  portal: data-rvagis.opendata.arcgis.com
    #     des_moines:       services.arcgis.com/eSi6C3K7GxWJJFTG   portal: data.dsm.city
    #     tulsa:            services.arcgis.com/vL1HzBwQf4fxjZTy   portal: opendata-maptulsa.opendata.arcgis.com
    #     wichita:          services.arcgis.com/sJ7GWBy3GCkiIsY7   portal: opendata.wichita.gov
    #     colorado_springs: services3.arcgis.com/oR4yfmG5eJFhSqy7  portal: data-cospatial.opendata.arcgis.com
    #     arlington_tx:     services.arcgis.com/v400IkDOw1ad7Yad   portal: data-cityofarlington.opendata.arcgis.com
    #     virginia_beach:   services1.arcgis.com/DqA6wR9XSVCoCbVN  portal: gis.data.vbgov.com
    #     mesa:             services2.arcgis.com/T3Rrfm3Dqq8Eepqn  portal: data-mesagis.opendata.arcgis.com
    #     aurora:           services1.arcgis.com/IJdEUGKefCEk4KsP  portal: data-auroragis.opendata.arcgis.com
    #     corpus_christi:   services.arcgis.com/5eqOE8IxIoFkEeGd   portal: data-cctexas.opendata.arcgis.com
    #     greensboro:       services.arcgis.com/CZ8GsPy9zJAnUBMD   portal: data-greensboroncgov.opendata.arcgis.com
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SKIPPED — No public open data portal found (data-057):
    #   Bakersfield, CA — no Socrata, ArcGIS, or CKAN portal.
    #     Uses Accela internally; crime data only via CrimeMapping.com.
    #   Anaheim, CA — no open data portal found.
    #     Uses Accela internally; crime data via CrimeMapping.com (no API).
    #   Santa Ana, CA — no open data portal found.
    #     Same Orange County limitation; no independent city API.
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — data-058 tier-8 cities (2026-03-27, data-076):
    #   All 6 configs returned HTTP 400 "Invalid URL" in every pipeline run.
    #   Service name "Building_Permits/FeatureServer/0" was a guessed placeholder.
    #   gilbert org K1VMQDQNLVxLvLqs is CONFIRMED INVALID (returns 400).
    #   Other orgs may be valid; real service names require live verification.
    #
    #   City reference (org IDs + portals):
    #     durham:      services.arcgis.com/QLwOtBvdB5bFqPNF   portal: data-durhamnc.opendata.arcgis.com
    #     chandler:    services.arcgis.com/SVsGn6WnqbDYPUgf   portal: data.chandleraz.gov
    #     scottsdale:  services.arcgis.com/4sF4h3aBrdOGHDuF   portal: data.scottsdaleaz.gov
    #     gilbert:     org K1VMQDQNLVxLvLqs CONFIRMED INVALID — visit data.gilbertaz.gov to find correct org
    #     glendale_az: services.arcgis.com/s0YYoMkpLLkb2IPC   portal: data.glendaleaz.gov
    #     henderson:   services.arcgis.com/pGfbNXXgj2WN9j5V   portal: hendersonnv.gov/opendata
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SKIPPED — No public open data portal found (data-058):
    #   Hialeah, FL — no separate city portal; Miami-Dade County coverage
    #     (miami_crime_trends.py) already includes Hialeah area.
    #   Laredo, TX — LPD publishes PDF reports only; no queryable API.
    #   North Las Vegas, NV — NLVPD has no public incident-level API.
    #   Boise, ID — limited open data; no permit or crime API found.
    #   Richmond, CA — RPCA no public API; small city, limited open data.
    #   Fremont, CA — FPD no public crime API; no Socrata/ArcGIS portal.
    #   Irvine, CA — IPD no public crime API; uses OCSD, no city API.
    #   San Bernardino, CA — SBPD no public crime API.
    #   Modesto, CA — MPD no public crime API.
    #   Fontana, CA — SBSO covers area; no city open data portal.
    #   Moreno Valley, CA — RCSO covers area; no city open data portal.
    #   Lubbock, TX — LPD publishes quarterly PDF reports only; no API.
    #   Garland, TX — GPD no public incident-level API found.
    #   Chesapeake, VA — CPD no public incident-level API found.
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — data-065 tier-10 cities (2026-03-27, data-076):
    #   All 4 Maricopa County AZ configs returned HTTP 400 in every pipeline run.
    #   Service name "Building_Permits/FeatureServer/0" was a guessed placeholder.
    #
    #   City reference (org IDs + portals):
    #     tempe:       services.arcgis.com/e5BBQV9bLnUqzr4V   portal: data.tempe.gov
    #     peoria_az:   services.arcgis.com/ZNh2Q3xZvn5AJFGZ   portal: data.peoriaaz.gov
    #     surprise_az: services.arcgis.com/QJfxWS1GiDHgQMwH   portal: data.surpriseaz.gov
    #     goodyear_az: services.arcgis.com/aMqXhGKtSoqR5lNw   portal: data.goodyearaz.gov
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SKIPPED — No public open data portal found (data-065):
    #   Montgomery, AL — no Socrata/ArcGIS/CKAN open data portal.
    #   Little Rock, AR — no public crime or permit API found.
    #   Jackson, MS — no open data portal.
    #   Columbus, GA (Muscogee County) — consolidated govt; no open data API.
    #   Savannah, GA — no public crime incident API found.
    #   Augusta, GA (Richmond County) — consolidated govt; no open data API.
    #   Kansas City, KS — Unified Government of Wyandotte County/KCK;
    #     no separate open data from UG (distinct from Kansas City, MO).
    #   Spokane Valley, WA — SVPD standalone; no public open data portal.
    #   Bakersfield, CA — already skipped in data-057; Accela/CrimeMapping only.
    #   Elk Grove, CA — Sacramento suburb; no open data portal found.
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — data-068 tier-11 cities (2026-03-27, data-076):
    #   All 3 configs returned HTTP 400 in every pipeline run.
    #   cape_coral org qJBnRfhGOvGVBnaX noted as invalid (SKILL.md data-075).
    #   fort_wayne crime script is a stub (no public crime API); permit endpoint unknown.
    #
    #   City reference (org IDs + portals):
    #     fort_wayne: services.arcgis.com/8Wez4BJD3neYYnDt  portal: data.fortwayne.com
    #     boise:      services.arcgis.com/r1QnEiQlTiHHMlou  portal: opendata.cityofboise.org
    #     cape_coral: org qJBnRfhGOvGVBnaX LIKELY INVALID   portal: data.capecoral.gov
    #                 (capecoral-capegis.opendata.arcgis.com has 70+ datasets; check for permits)
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # REMOVED — data-070 + data-071 tier-12/13 cities (2026-03-27, data-076):
    #   All 6 configs returned HTTP 400 in every pipeline run.
    #   sioux_falls crime uses self-hosted gis.siouxfalls.gov; permit org Nf5qHqEDvuX5aNFd unverified.
    #
    #   City reference (org IDs + portals):
    #     eugene:         services1.arcgis.com/VZLb8iHnAWdlSeZ3  portal: data.eugene-or.gov
    #     springfield_mo: services6.arcgis.com/bdLPgVQpKkp3xrEm  portal: data.springfieldmo.gov
    #     sioux_falls:    services.arcgis.com/Nf5qHqEDvuX5aNFd   portal: siouxfalls.org/departments/information-technology/gis
    #                     (also try self-hosted: gis.siouxfalls.gov/arcgis/rest/services)
    #     omaha:          services.arcgis.com/q4kU3NFQX1XtcMeJ   portal: opendata.cityofomaha.org
    #     lincoln:        services.arcgis.com/ZPeUDkbFEf7WXNID   portal: opendata.lincoln.ne.gov
    #     salem_or:       services.arcgis.com/uUvqNr0XSi28N3Hj   portal: data.cityofsalem.net
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SKIPPED — No public open data portal found (data-071):
    #   Green Bay, WI — data.greenbaywi.gov does not resolve to open data portal;
    #     GBPD publishes PDF reports only; no ArcGIS/Socrata crime or permit API.
    #   Rockford, IL — cityofrockford.org no open data API; data.illinois.gov
    #     has no RPD crime data; no queryable permit data confirmed.
    #   Springfield, OR — small city (~60k); no open data portal found;
    #     adjacent Eugene also has no confirmed API (stub).
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SKIPPED — No public open data portal found (data-068):
    #   Akron, OH — data.akronohio.gov exists but no crime incident API;
    #     APD uses web-only portal for public reports. Re-checked 2026-03-25.
    #   Knoxville, TN — knoxvilletn.gov open data portal exists but KPD
    #     crime incident data is request-only ($10/report). Re-checked 2026-03-25.
    #   Shreveport, LA — data.shreveportla.gov exists but SPD provides only
    #     aggregate street-level offense counts; no incident-level API.
    #   Huntsville, AL — hsvcity.com has limited open data; HPD crime data
    #     via JustFOIA portal only; no queryable REST API found.
    #   Winston-Salem, NC — data.cityofws.org exists but WSPD has no public
    #     crime data services on ArcGIS or Socrata. Re-checked 2026-03-25.
    #   Montgomery, AL — MPDAL no open data portal; re-confirmed 2026-03-25.
    #   Little Rock, AR — LRPD no public incident API; re-confirmed 2026-03-25.
    #   Jackson, MS — JPD no open data portal; re-confirmed 2026-03-25.
    #   Columbus, GA (Muscogee County) — consolidated govt; re-confirmed 2026-03-25.
    #   Savannah, GA — SCMPD no public crime incident API; re-confirmed 2026-03-25.
    #   Augusta, GA (Richmond County) — consolidated govt; re-confirmed 2026-03-25.
    #   Kansas City, KS — UG of Wyandotte County/KCK; re-confirmed 2026-03-25.
    #   Laredo, TX — LPD PDF reports only; re-confirmed 2026-03-25.
    #   Garland, TX — GPD no public incident-level API; re-confirmed 2026-03-25.
    #   Lubbock, TX — LPD quarterly PDF stats only; re-confirmed 2026-03-25.
    #   Chesapeake, VA — CPD no public incident-level API; re-confirmed 2026-03-25.
    #   North Las Vegas, NV — NLVPD separate from LVMPD; no public API found.
    #   Fremont, CA — FPD no public crime API; no Socrata/ArcGIS portal found.
    #   Irvine, CA — uses OCSD coverage; no city-level incident API.
    #   Elk Grove, CA — Sacramento County suburb; no independent portal found.
    #   Spokane Valley, WA — SVPD standalone; no public open data portal.
    # SKIPPED — No public open data portal found (data-070, 2026-03-25):
    #   Overland Park, KS — opkansas.org is infrastructure/GIS data only;
    #     OPPD uses Motorola PremierOne, no public crime or permit API found.
    #   Amarillo, TX — APD no public open data crime API; CrimeMapping.com
    #     view-only; no ArcGIS Hub or Socrata portal for permits found.
    #   Oxnard, CA — OPD no public crime API; no Socrata/ArcGIS portal found.
    #   Salinas, CA — SPD no public crime API; no open data portal found.
    #   Fayetteville, AR — data.fayetteville-ar.gov limited; no crime
    #     incident API or queryable permit data confirmed as of 2026-03-25.
    # -----------------------------------------------------------------
]

# Index by source_key for fast lookup.
CITY_CONFIG_BY_KEY: dict[str, dict] = {c["source_key"]: c for c in CITY_CONFIGS}

# ---------------------------------------------------------------------------
# Disabled source keys — data-076
# ---------------------------------------------------------------------------
# All 31 placeholder configs (data-057 through data-071) were removed from
# CITY_CONFIGS on 2026-03-27 (data-076). They all returned HTTP 400 "Invalid
# URL" because the service names were guessed placeholders ("Building_Permits")
# that did not match any real ArcGIS service name.
#
# The org IDs are preserved in REMOVED comment blocks in CITY_CONFIGS above.
# To re-add a city: query its org's service listing, find the permit service
# name, then add a config entry and run --dry-run to verify.
#
# DISABLED_SOURCE_KEYS is kept empty — no active city configs are disabled.
DISABLED_SOURCE_KEYS: frozenset[str] = frozenset()

# Special notes for removed cities (preserved for reference).
DISABLED_NOTES: dict[str, str] = {
    # gilbert: org K1VMQDQNLVxLvLqs CONFIRMED INVALID (HTTP 400). Config removed.
    # las_vegas: org VIkzGEMZbaSsMGLk returns 0 services; gis.lasvegasnevada.gov unreachable.
    # el_paso: real data at gis.elpasotexas.gov but server blocks python-requests with 403.
    # san_jose, fort_worth, albuquerque: orgs return 0 services on all subdomains.
    # cape_coral: org qJBnRfhGOvGVBnaX noted as invalid; capecoral-capegis.opendata.arcgis.com
    #   has 70+ datasets but no permit FeatureServer confirmed.
}

# Records per page (ArcGIS default max varies by server; 1000 is safe).
PAGE_SIZE = 1000

# How many days back to filter permits.
DAYS_BACK = 90

# Base output directory for staging files.
DEFAULT_OUTPUT_DIR = Path("data/raw")


# ---------------------------------------------------------------------------
# ArcGIS REST API helpers
# ---------------------------------------------------------------------------

def _build_date_where(config: dict, cutoff_epoch_ms: int) -> str | None:
    """
    Build a SQL WHERE clause for date filtering.

    Uses TIMESTAMP literal format which is widely supported across ArcGIS
    Server and ArcGIS Online hosted FeatureServer/MapServer endpoints.
    Raw epoch ms comparison (field >= 123456789) is NOT supported by most
    servers despite being accepted in some documentation.
    """
    if config.get("skip_date_filter"):
        return None
    date_field = config["issue_date_field"]
    # Convert epoch ms to TIMESTAMP literal
    cutoff_dt = datetime.fromtimestamp(cutoff_epoch_ms / 1000, tz=timezone.utc)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"{date_field} >= TIMESTAMP '{cutoff_str}'"


def fetch_page(
    session: requests.Session,
    config: dict,
    offset: int,
    limit: int,
    where_clause: str,
) -> tuple[list[dict], bool]:
    """
    Fetch one page of ArcGIS FeatureServer records.

    Returns (records, exceeded_transfer_limit).
    Each record is the raw attributes dict from the ArcGIS JSON response,
    augmented with _geometry_x and _geometry_y from the feature geometry.
    """
    url = f"{config['service_url']}/query"
    params: dict[str, Any] = {
        "where":             where_clause,
        "outFields":         "*",
        "returnGeometry":    "true",
        "outSR":             "4326",   # request WGS-84 lat/lon
        "resultOffset":      offset,
        "resultRecordCount": limit,
        "f":                 "json",
    }

    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    # ArcGIS returns {"error": {...}} on query failure.
    if "error" in data:
        err = data["error"]
        raise RuntimeError(
            f"ArcGIS error {err.get('code', '?')}: {err.get('message', data)}"
        )

    features = data.get("features", [])
    exceeded = data.get("exceededTransferLimit", False)

    records = []
    for feat in features:
        attrs = dict(feat.get("attributes") or {})
        geom = feat.get("geometry") or {}

        # Inject geometry as private fields for lat/lon extraction.
        attrs["_geometry_x"] = geom.get("x")
        attrs["_geometry_y"] = geom.get("y")

        records.append(attrs)

    return records, exceeded


def fetch_city_permits(
    config: dict,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through an ArcGIS FeatureServer and return all permit records
    within the lookback window.

    Pagination strategy:
      - Use resultOffset / resultRecordCount for page-based pagination.
      - Stop when a page returns fewer records than the page size OR
        when exceededTransferLimit is False.

    Date filter strategy:
      - Try epoch-ms date filter first.
      - If the response has 0 records and no error, retry without a date filter
        (may indicate the date field name is wrong).
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_epoch_ms = int(cutoff.timestamp() * 1000)

    where_clause = _build_date_where(config, cutoff_epoch_ms) or "1=1"

    all_records: list[dict] = []
    offset = 0

    print(
        f"\nFetching {config['city_name']} permits "
        f"(url={config['service_url']})..."
    )
    print(f"  WHERE: {where_clause}")

    tried_date_filter = (where_clause != "1=1")

    try:
        while True:
            print(f"  Fetching at offset {offset}...", end=" ", flush=True)
            records, exceeded = fetch_page(
                session, config, offset, PAGE_SIZE, where_clause
            )
            print(f"{len(records)} records (exceededTransferLimit={exceeded}).")

            if not records:
                # If we got 0 records with a date filter, try without.
                if tried_date_filter and offset == 0:
                    print(
                        "  WARN: 0 records with date filter — retrying without "
                        "date filter to verify connectivity.",
                        file=sys.stderr,
                    )
                    print(
                        f"  NOTE: Verify '{config['issue_date_field']}' is the "
                        f"correct date field name for {config['city_name']}.",
                        file=sys.stderr,
                    )
                    where_clause = "1=1"
                    tried_date_filter = False

                    records, exceeded = fetch_page(
                        session, config, 0, PAGE_SIZE, where_clause
                    )
                    print(
                        f"  Retry without date filter: {len(records)} records "
                        f"(exceededTransferLimit={exceeded})."
                    )
                    if records:
                        all_records.extend(records)
                        offset = PAGE_SIZE
                        if dry_run or not exceeded:
                            break
                        continue

                break  # genuinely 0 records

            all_records.extend(records)
            offset += len(records)

            if dry_run:
                print("  Dry-run: stopping after first page.")
                break

            if not exceeded and len(records) < PAGE_SIZE:
                break  # last page

            # Some servers don't set exceededTransferLimit. Keep paginating.

            max_records = config.get("max_records")
            if max_records and len(all_records) >= max_records:
                print(f"  Reached max_records cap ({max_records}). Stopping.")
                break

    except requests.exceptions.Timeout:
        print(
            f"\n  ERROR [{config['city_name']}]: Request timed out.",
            file=sys.stderr,
        )
        print(
            f"  Verify service_url: {config['service_url']}\n"
            f"  Or run: python backend/ingest/us_city_permits_arcgis.py "
            f"--city {config['source_key']} --discover",
            file=sys.stderr,
        )
        return []
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(
            f"\n  ERROR [{config['city_name']}]: HTTP {status}. Skipping.",
            file=sys.stderr,
        )
        print(
            f"  Verify service_url: {config['service_url']}\n"
            f"  Portal: {config['portal_url']}\n"
            f"  Or run: python backend/ingest/us_city_permits_arcgis.py "
            f"--city {config['source_key']} --discover",
            file=sys.stderr,
        )
        return []
    except RuntimeError as exc:
        print(
            f"\n  ERROR [{config['city_name']}]: {exc}. Skipping.",
            file=sys.stderr,
        )
        return []

    return all_records


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_lat_lon(
    record: dict,
    config: dict,
) -> tuple[str | None, str | None]:
    """
    Extract lat/lon from an ArcGIS record.

    Checks _geometry_y/_geometry_x (injected from feature.geometry) first,
    then falls back to explicit lat/lon attribute fields if configured.
    """
    lat: str | None = None
    lon: str | None = None

    # Primary: geometry fields injected by fetch_page()
    raw_y = record.get("_geometry_y")
    raw_x = record.get("_geometry_x")

    if raw_y is not None:
        try:
            lat = str(float(raw_y))
        except (TypeError, ValueError):
            pass

    if raw_x is not None:
        try:
            lon = str(float(raw_x))
        except (TypeError, ValueError):
            pass

    return lat, lon


def _extract_source_id(record: dict, config: dict) -> str:
    """
    Extract a stable source ID from a raw ArcGIS record.

    Falls back to SHA-1 hash of key fields when the configured id_field
    is absent.
    """
    id_field = config["id_field"]
    raw_id = str(record.get(id_field) or "").strip()
    if raw_id and raw_id.lower() not in ("none", "null"):
        return raw_id

    parts = [
        str(record.get(config["issue_date_field"], "") or ""),
        str(record.get(config["addr_field"], "") or ""),
        str(record.get(config.get("desc_field", ""), "") or ""),
    ]
    key = "|".join(parts)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _ms_epoch_to_iso(value: Any) -> str:
    """
    Convert an ArcGIS epoch-millisecond timestamp to an ISO 8601 string.
    Returns the original string representation if conversion fails.
    """
    if value is None:
        return ""
    try:
        ms = int(value)
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(value)


def normalize_raw_record(record: dict, config: dict) -> dict:
    """
    Map a raw ArcGIS permit attributes dict to the standard internal field set.

    Output schema matches Socrata and CKAN scripts so downstream loaders
    can treat all permit sources identically.
    """
    lat, lon = _extract_lat_lon(record, config)

    # ArcGIS timestamps are epoch-ms integers; convert to ISO dates.
    raw_issue = record.get(config["issue_date_field"])
    issue_date = _ms_epoch_to_iso(raw_issue) if isinstance(raw_issue, (int, float)) else str(raw_issue or "")

    raw_exp = record.get(config.get("exp_date_field") or "") if config.get("exp_date_field") else None
    exp_date = _ms_epoch_to_iso(raw_exp) if isinstance(raw_exp, (int, float)) else str(raw_exp or "")

    return {
        "source_key":      config["source_key"],
        "city_name":       config["city_name"],
        "city_state":      config["city_state"],
        "source_id":       _extract_source_id(record, config),
        "permit_type":     str(record.get(config["type_field"], "") or ""),
        "description":     str(record.get(config["desc_field"], "") or ""),
        "issue_date":      issue_date,
        "expiration_date": exp_date,
        "address":         str(record.get(config["addr_field"], "") or ""),
        "latitude":        lat,
        "longitude":       lon,
    }


# ---------------------------------------------------------------------------
# Discovery mode
# ---------------------------------------------------------------------------

def discover_service(config: dict) -> None:
    """
    Query the ArcGIS Hub REST API to find building permit datasets for a city.

    Prints dataset titles, IDs, and FeatureServer URLs to help the user
    identify and verify the correct service_url to configure above.
    """
    city_name = config["city_name"]
    print(f"\nDiscovering ArcGIS Hub datasets for {city_name}...")

    # ArcGIS Hub REST API: search for datasets by keyword + bounding box.
    # Docs: https://hub.arcgis.com/api/v3/
    hub_url = "https://hub.arcgis.com/api/v3/datasets"
    params = {
        "q":           f"building permits {city_name}",
        "fields[datasets]": "title,url,access,layer,extent,searchDescription",
        "page[size]":  10,
    }

    try:
        resp = requests.get(hub_url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  ERROR querying ArcGIS Hub: {exc}", file=sys.stderr)
        print(
            f"\n  Manual search:\n"
            f"  1. Visit {config['portal_url']}\n"
            f"  2. Search 'building permits'\n"
            f"  3. Open the dataset and click 'API' to get the FeatureServer URL\n"
            f"  4. Update service_url in CITY_CONFIGS for {config['source_key']}"
        )
        return

    datasets = data.get("data", [])
    if not datasets:
        print(f"  No datasets found for '{city_name}' on ArcGIS Hub.")
        print(
            f"\n  Try manually:\n"
            f"  1. Visit {config['portal_url']}\n"
            f"  2. Search 'building permits'\n"
            f"  3. Open the dataset and copy the FeatureServer/0 URL."
        )
        return

    print(f"  Found {len(datasets)} dataset(s):\n")
    for ds in datasets:
        attrs = ds.get("attributes", {})
        title = attrs.get("title", "?")
        url = attrs.get("url", "")
        print(f"  Title: {title}")
        print(f"  URL:   {url}")
        if url and "FeatureServer" in url:
            service_layer = url.rstrip("/") + "/0" if not url.endswith("/0") else url
            print(f"  → Set service_url = '{service_layer}/query' base: '{url}/0'")
        print()

    print(
        f"  Hint: update service_url in CITY_CONFIGS['{config['source_key']}'] "
        f"to the FeatureServer/0 URL above."
    )

    # Also print a direct sample query to test the current service_url.
    print(
        f"\n  Test current service_url with:\n"
        f"  curl '{config['service_url']}/query"
        f"?where=1%3D1&outFields=*&resultRecordCount=1&f=json'"
    )


# ---------------------------------------------------------------------------
# Staging file writer
# ---------------------------------------------------------------------------

def write_staging_file(
    records: list[dict],
    config: dict,
    output_dir: Path,
) -> Path:
    """Write normalized permit records to a JSON staging file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"us_city_permits_{config['source_key']}.json"

    staging = {
        "source":       f"us_city_permits_{config['source_key']}",
        "city_name":    config["city_name"],
        "source_url":   config["service_url"],
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records":      records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"  Wrote {len(records)} records to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Per-city orchestration
# ---------------------------------------------------------------------------

def ingest_city(
    config: dict,
    days_back: int,
    dry_run: bool,
    output_dir: Path,
    discover: bool,
) -> int:
    """
    Fetch and stage permits for one city.

    Returns the number of records written (0 on failure or dry-run).
    """
    if discover:
        discover_service(config)
        return 0

    # Skip configs whose org IDs have not been live-verified (data-074).
    if config["source_key"] in DISABLED_SOURCE_KEYS:
        note = DISABLED_NOTES.get(
            config["source_key"],
            f"unverified org ID — returns HTTP 400. "
            f"Fix: run --city {config['source_key']} --discover "
            f"or visit {config['portal_url']}",
        )
        print(f"  SKIP [{config['city_name']}]: {note}", file=sys.stderr)
        return 0

    raw_records = fetch_city_permits(config, days_back, dry_run)

    if not raw_records:
        print(f"  No records returned for {config['city_name']}.")
        return 0

    # Strip internal geometry fields before normalization.
    normalized = [normalize_raw_record(r, config) for r in raw_records]
    print(f"  Normalized {len(normalized)} records.")

    if dry_run:
        print("  Dry-run: skipping file write.")
        if normalized:
            print(f"  Sample:\n{json.dumps(normalized[0], indent=4)}")
        return 0

    write_staging_file(normalized, config, output_dir)
    return len(normalized)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest US city building permits from ArcGIS REST FeatureServer.\n\n"
            "Cities: Phoenix, Columbus, Minneapolis, Charlotte, Jacksonville.\n\n"
            "NOTE: Service URLs require verification before production use.\n"
            "Run --discover or visit each city's open data portal to confirm."
        )
    )
    parser.add_argument(
        "--city",
        choices=list(CITY_CONFIG_BY_KEY.keys()) + ["all"],
        default="all",
        help="Which city to ingest (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for output staging files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=DAYS_BACK,
        help=f"Number of days back to filter permits (default: {DAYS_BACK}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page per city only; do not write output files.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help=(
            "Query ArcGIS Hub REST API to find building permit datasets — "
            "useful for verifying or finding the correct service_url."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List configured cities and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Configured ArcGIS city sources:")
        for cfg in CITY_CONFIGS:
            print(
                f"  {cfg['source_key']:20s} → {cfg['city_name']} "
                f"({cfg['service_url'][:60]}...)"
            )
        return

    configs = (
        CITY_CONFIGS
        if args.city == "all"
        else [CITY_CONFIG_BY_KEY[args.city]]
    )

    total = 0
    failed: list[str] = []

    for config in configs:
        try:
            count = ingest_city(
                config,
                args.days_back,
                args.dry_run,
                args.output_dir,
                args.discover,
            )
            total += count
        except Exception as exc:
            print(f"  ERROR [{config['city_name']}]: {exc}", file=sys.stderr)
            failed.append(config["city_name"])

    if not args.discover:
        print(f"\n── Summary ──────────────────────────────────────")
        print(f"  Cities attempted: {len(configs)}")
        print(
            f"  Cities failed:    {len(failed)}"
            + (f" ({', '.join(failed)})" if failed else "")
        )
        print(f"  Total records:    {total}")

        if args.dry_run:
            print("  Dry-run mode: no files written.")

        if failed and len(failed) == len(configs):
            sys.exit(1)


if __name__ == "__main__":
    main()
