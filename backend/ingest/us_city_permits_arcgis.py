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
        # Denver, CO — Building Permits.
        # Portal: https://opendata-geospatialdenver.hub.arcgis.com
        # ArcGIS Hub org: services1.arcgis.com/zdB7qR0BtYrg0Xpl (Denver's org ID)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city denver --discover
        #   Or visit: https://opendata-geospatialdenver.hub.arcgis.com
        #   Search "building permits" and copy the FeatureServer/0 URL.
        # Note: data.denvergov.org redirects to ArcGIS Hub (not Socrata/CKAN).
        "city_name":        "Denver",
        "source_key":       "denver",
        "service_url":      (
            "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services"
            "/ODC_BUILDING_PERMITS_P/FeatureServer/0"
        ),
        "portal_url":       "https://opendata-geospatialdenver.hub.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "WORK_DESC",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   "EXPIRATION_DATE",
        "addr_field":       "ADDRESS",
        "city_state":       "Denver, CO",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Portland, OR — Building Permits.
        # Portal: https://gis.portlandoregon.gov  (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city portland --discover
        #   Or visit: https://gis.portlandoregon.gov
        #   Search "building permits" and copy the FeatureServer/0 URL.
        "city_name":        "Portland",
        "source_key":       "portland",
        "service_url":      (
            "https://services.arcgis.com/quVN97tn06YNGj9s/arcgis/rest/services"
            "/BDS_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://gis.portlandoregon.gov",
        "id_field":         "PERMIT_NBR",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "WORK_DESC",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "SITE_ADDRESS",
        "city_state":       "Portland, OR",
        "skip_date_filter": False,
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
    {
        # Las Vegas, NV — Building Permits.
        # Portal: https://opendataportal-lasvegas.opendata.arcgis.com
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city las_vegas --discover
        "city_name":        "Las Vegas",
        "source_key":       "las_vegas",
        "service_url":      (
            "https://services.arcgis.com/VIkzGEMZbaSsMGLk/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendataportal-lasvegas.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Las Vegas, NV",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # El Paso, TX — Building Permits.
        # Portal: https://data.elpasotexas.gov
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city el_paso --discover
        "city_name":        "El Paso",
        "source_key":       "el_paso",
        "service_url":      (
            "https://services.arcgis.com/YGBqHTHNMoJPJOav/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.elpasotexas.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "El Paso, TX",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Tucson, AZ — Building Permits.
        # Portal: https://gisdata.tucsonaz.gov
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city tucson --discover
        "city_name":        "Tucson",
        "source_key":       "tucson",
        "service_url":      (
            "https://gisdata.tucsonaz.gov/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://gisdata.tucsonaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Tucson, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # REMOVED — Jacksonville (verified 2026-03-22):
    #   maps.coj.net and gis.coj.net both return 404. No building permit
    #   FeatureServer found on ArcGIS Online either.
    # -----------------------------------------------------------------
    {
        # San Jose, CA — Building Permits.
        # Portal: https://gis.sanjoseca.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city san_jose --discover
        #   Or visit: https://gis.sanjoseca.gov and search "building permits"
        # data-050: added 2026-03-23
        "city_name":        "San Jose",
        "source_key":       "san_jose",
        "service_url":      (
            "https://services.arcgis.com/p8Tul9YqBFRRdPqD/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://gis.sanjoseca.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "San Jose, CA",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Fort Worth, TX — Building Permits.
        # Portal: https://data.fortworthtexas.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city fort_worth --discover
        #   Or visit: https://data.fortworthtexas.gov and search "building permits"
        # data-050: added 2026-03-23
        "city_name":        "Fort Worth",
        "source_key":       "fort_worth",
        "service_url":      (
            "https://services.arcgis.com/AHCzmZstRKFEQEqv/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.fortworthtexas.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Fort Worth, TX",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Albuquerque, NM — Building Permits.
        # Portal: https://cabq.gov/abqdata (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city albuquerque --discover
        #   Or visit: https://cabq.gov/abqdata and search "building permits"
        #   Or search: https://abq.maps.arcgis.com
        # data-050: added 2026-03-23
        "city_name":        "Albuquerque",
        "source_key":       "albuquerque",
        "service_url":      (
            "https://services.arcgis.com/3HnGBxB8VqLCXhUn/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://cabq.gov/abqdata",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Albuquerque, NM",
        "skip_date_filter": False,
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # data-057: Tier-7 city permits (2026-03-24)
    # -----------------------------------------------------------------
    {
        # Orlando, FL — Building Permits.
        # Portal: https://data-cityoforlando.opendata.arcgis.com (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city orlando --discover
        #   Or visit: https://data-cityoforlando.opendata.arcgis.com and search "permits"
        "city_name":        "Orlando",
        "source_key":       "orlando",
        "service_url":      (
            "https://services1.arcgis.com/ySBMu4XsNZMHPCce/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-cityoforlando.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Orlando, FL",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Richmond, VA — Building Permits.
        # Portal: https://data-rvagis.opendata.arcgis.com (Richmond GIS)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city richmond --discover
        "city_name":        "Richmond",
        "source_key":       "richmond",
        "service_url":      (
            "https://services1.arcgis.com/k3vhq11XkBNeeOfM/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-rvagis.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Richmond, VA",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Des Moines, IA — Building Permits.
        # Portal: https://data.dsm.city (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city des_moines --discover
        "city_name":        "Des Moines",
        "source_key":       "des_moines",
        "service_url":      (
            "https://services.arcgis.com/eSi6C3K7GxWJJFTG/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.dsm.city",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Des Moines, IA",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Tulsa, OK — Building Permits.
        # Portal: https://opendata-maptulsa.opendata.arcgis.com (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city tulsa --discover
        "city_name":        "Tulsa",
        "source_key":       "tulsa",
        "service_url":      (
            "https://services.arcgis.com/vL1HzBwQf4fxjZTy/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata-maptulsa.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Tulsa, OK",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Wichita, KS — Building Permits.
        # Portal: https://opendata.wichita.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city wichita --discover
        "city_name":        "Wichita",
        "source_key":       "wichita",
        "service_url":      (
            "https://services.arcgis.com/sJ7GWBy3GCkiIsY7/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.wichita.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Wichita, KS",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Colorado Springs, CO — Building Permits.
        # Portal: https://data-cospatial.opendata.arcgis.com (City of Colorado Springs GIS)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city colorado_springs --discover
        "city_name":        "Colorado Springs",
        "source_key":       "colorado_springs",
        "service_url":      (
            "https://services3.arcgis.com/oR4yfmG5eJFhSqy7/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-cospatial.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Colorado Springs, CO",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Arlington, TX — Building Permits.
        # Portal: https://data-cityofarlington.opendata.arcgis.com (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city arlington_tx --discover
        "city_name":        "Arlington TX",
        "source_key":       "arlington_tx",
        "service_url":      (
            "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-cityofarlington.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Arlington, TX",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Virginia Beach, VA — Building Permits.
        # Portal: https://gis.data.vbgov.com (Virginia Beach GIS)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city virginia_beach --discover
        "city_name":        "Virginia Beach",
        "source_key":       "virginia_beach",
        "service_url":      (
            "https://services1.arcgis.com/DqA6wR9XSVCoCbVN/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://gis.data.vbgov.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Virginia Beach, VA",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Mesa, AZ — Building Permits.
        # Portal: https://data-mesagis.opendata.arcgis.com (Mesa GIS)
        # Note: Mesa is separate from Phoenix/Maricopa — covered by separate scripts.
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city mesa --discover
        "city_name":        "Mesa",
        "source_key":       "mesa",
        "service_url":      (
            "https://services2.arcgis.com/T3Rrfm3Dqq8Eepqn/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-mesagis.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Mesa, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Aurora, CO — Building Permits.
        # Portal: https://data-auroragis.opendata.arcgis.com (Aurora GIS)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city aurora --discover
        "city_name":        "Aurora",
        "source_key":       "aurora",
        "service_url":      (
            "https://services1.arcgis.com/IJdEUGKefCEk4KsP/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-auroragis.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Aurora, CO",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Corpus Christi, TX — Building Permits.
        # Portal: https://data-cctexas.opendata.arcgis.com (City of Corpus Christi)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city corpus_christi --discover
        "city_name":        "Corpus Christi",
        "source_key":       "corpus_christi",
        "service_url":      (
            "https://services.arcgis.com/5eqOE8IxIoFkEeGd/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-cctexas.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Corpus Christi, TX",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Greensboro, NC — Building Permits.
        # Portal: https://data-greensboroncgov.opendata.arcgis.com (City of Greensboro)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city greensboro --discover
        "city_name":        "Greensboro",
        "source_key":       "greensboro",
        "service_url":      (
            "https://services.arcgis.com/CZ8GsPy9zJAnUBMD/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-greensboroncgov.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Greensboro, NC",
        "skip_date_filter": False,
        "max_records":      None,
    },
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
    # data-058: tier-8 city permits (ArcGIS Hub)
    # -----------------------------------------------------------------
    {
        # Durham, NC — Building Permits.
        # Portal: https://data-durhamnc.opendata.arcgis.com (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city durham --discover
        # data-058: added 2026-03-24
        "city_name":        "Durham",
        "source_key":       "durham",
        "service_url":      (
            "https://services.arcgis.com/QLwOtBvdB5bFqPNF/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data-durhamnc.opendata.arcgis.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Durham, NC",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Chandler, AZ — Building Permits.
        # Portal: https://data.chandleraz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city chandler --discover
        # data-058: added 2026-03-24
        "city_name":        "Chandler",
        "source_key":       "chandler",
        "service_url":      (
            "https://services.arcgis.com/SVsGn6WnqbDYPUgf/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.chandleraz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Chandler, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Scottsdale, AZ — Building Permits.
        # Portal: https://data.scottsdaleaz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city scottsdale --discover
        # data-058: added 2026-03-24
        "city_name":        "Scottsdale",
        "source_key":       "scottsdale",
        "service_url":      (
            "https://services.arcgis.com/4sF4h3aBrdOGHDuF/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.scottsdaleaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Scottsdale, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Gilbert, AZ — Building Permits.
        # Portal: https://data.gilbertaz.gov (ArcGIS Hub)
        # BLOCKED: org ID K1VMQDQNLVxLvLqs is INVALID (returns 400 "Invalid URL").
        # Fix: visit https://data.gilbertaz.gov, find Building Permits dataset,
        #      extract org ID from FeatureServer URL, update service_url below.
        # Helper: python backend/ingest/verify_arcgis_endpoints.py --city gilbert --discover
        # data-058: added 2026-03-24; data-066: blocked — needs org ID fix
        "city_name":        "Gilbert",
        "source_key":       "gilbert",
        "service_url":      (
            "https://services.arcgis.com/K1VMQDQNLVxLvLqs/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"  # INVALID — see comment above
        ),
        "portal_url":       "https://data.gilbertaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Gilbert, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Glendale, AZ — Building Permits.
        # NOTE: This is Glendale, AZ (Maricopa County), not Glendale, CA.
        # Portal: https://data.glendaleaz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city glendale_az --discover
        # data-058: added 2026-03-24
        "city_name":        "Glendale AZ",
        "source_key":       "glendale_az",
        "service_url":      (
            "https://services.arcgis.com/s0YYoMkpLLkb2IPC/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.glendaleaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Glendale, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Henderson, NV — Building Permits.
        # Henderson has its own city portal (separate from Las Vegas).
        # Portal: https://hendersonnv.gov/opendata (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city henderson --discover
        # data-058: added 2026-03-24
        "city_name":        "Henderson",
        "source_key":       "henderson",
        "service_url":      (
            "https://services.arcgis.com/pGfbNXXgj2WN9j5V/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://hendersonnv.gov/opendata",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Henderson, NV",
        "skip_date_filter": False,
        "max_records":      None,
    },
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
    # data-065: tier-10 city permits (ArcGIS Hub) — Maricopa County AZ
    # -----------------------------------------------------------------
    {
        # Tempe, AZ — Building Permits.
        # Portal: https://data.tempe.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city tempe --discover
        #   Or visit: https://data.tempe.gov and search "building permits"
        # data-065: added 2026-03-24
        "city_name":        "Tempe",
        "source_key":       "tempe",
        "service_url":      (
            "https://services.arcgis.com/e5BBQV9bLnUqzr4V/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.tempe.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Tempe, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Peoria, AZ — Building Permits.
        # NOTE: This is Peoria, AZ (Maricopa County), not Peoria, IL.
        # Portal: https://data.peoriaaz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city peoria_az --discover
        # data-065: added 2026-03-24
        "city_name":        "Peoria AZ",
        "source_key":       "peoria_az",
        "service_url":      (
            "https://services.arcgis.com/ZNh2Q3xZvn5AJFGZ/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.peoriaaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Peoria, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Surprise, AZ — Building Permits.
        # Portal: https://data.surpriseaz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city surprise_az --discover
        # data-065: added 2026-03-24
        "city_name":        "Surprise AZ",
        "source_key":       "surprise_az",
        "service_url":      (
            "https://services.arcgis.com/QJfxWS1GiDHgQMwH/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.surpriseaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Surprise, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Goodyear, AZ — Building Permits.
        # Portal: https://data.goodyearaz.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city goodyear_az --discover
        # data-065: added 2026-03-24
        "city_name":        "Goodyear AZ",
        "source_key":       "goodyear_az",
        "service_url":      (
            "https://services.arcgis.com/aMqXhGKtSoqR5lNw/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.goodyearaz.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Goodyear, AZ",
        "skip_date_filter": False,
        "max_records":      None,
    },
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
    # data-068: tier-11 city permits (ArcGIS Hub) — new cities
    # -----------------------------------------------------------------
    {
        # Fort Wayne, IN — Building Permits.
        # Portal: https://data.fortwayne.com (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city fort_wayne --discover
        #   Or visit: https://data.fortwayne.com and search "building permits"
        # data-068: added 2026-03-25
        "city_name":        "Fort Wayne",
        "source_key":       "fort_wayne",
        "service_url":      (
            "https://services.arcgis.com/8Wez4BJD3neYYnDt/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.fortwayne.com",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Fort Wayne, IN",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Boise, ID — Building Permits.
        # Portal: https://opendata.cityofboise.org (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city boise --discover
        #   Or visit: https://opendata.cityofboise.org and search "building permits"
        # data-068: added 2026-03-25
        "city_name":        "Boise",
        "source_key":       "boise",
        "service_url":      (
            "https://services.arcgis.com/r1QnEiQlTiHHMlou/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://opendata.cityofboise.org",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Boise, ID",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Cape Coral, FL — Building Permits.
        # Portal: https://data.capecoral.gov (ArcGIS Hub — confirmed to exist; data-065)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city cape_coral --discover
        #   Or visit: https://data.capecoral.gov and search "building permits"
        # data-068: added 2026-03-25
        "city_name":        "Cape Coral",
        "source_key":       "cape_coral",
        "service_url":      (
            "https://services.arcgis.com/qJBnRfhGOvGVBnaX/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.capecoral.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Cape Coral, FL",
        "skip_date_filter": False,
        "max_records":      None,
    },
    # -----------------------------------------------------------------
    # data-070: tier-12 city permits (ArcGIS portals)
    # -----------------------------------------------------------------
    {
        # Eugene, OR — Building Permits.
        # Portal: https://data.eugene-or.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city eugene --discover
        #   Or visit: https://data.eugene-or.gov and search "building permits"
        # data-070: added 2026-03-25
        "city_name":        "Eugene",
        "source_key":       "eugene",
        "service_url":      (
            "https://services1.arcgis.com/VZLb8iHnAWdlSeZ3/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.eugene-or.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Eugene, OR",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Springfield, MO — Building Permits.
        # Portal: https://data.springfieldmo.gov (ArcGIS Hub)
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city springfield_mo --discover
        #   Or visit: https://data.springfieldmo.gov and search "building permits"
        # data-070: added 2026-03-25
        "city_name":        "Springfield MO",
        "source_key":       "springfield_mo",
        "service_url":      (
            "https://services6.arcgis.com/bdLPgVQpKkp3xrEm/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://data.springfieldmo.gov",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Springfield, MO",
        "skip_date_filter": False,
        "max_records":      None,
    },
    {
        # Sioux Falls, SD — Building Permits.
        # Portal: ArcGIS Hub (search "Sioux Falls building permits")
        # MUST VERIFY service_url before production:
        #   python backend/ingest/us_city_permits_arcgis.py --city sioux_falls --discover
        #   Or search ArcGIS Hub for "Sioux Falls building permits"
        # data-070: added 2026-03-25
        "city_name":        "Sioux Falls",
        "source_key":       "sioux_falls",
        "service_url":      (
            "https://services.arcgis.com/Nf5qHqEDvuX5aNFd/arcgis/rest/services"
            "/Building_Permits/FeatureServer/0"
        ),
        "portal_url":       "https://www.siouxfalls.org/departments/information-technology/gis",
        "id_field":         "PERMIT_NUM",
        "type_field":       "PERMIT_TYPE",
        "desc_field":       "DESCRIPTION",
        "issue_date_field": "ISSUED_DATE",
        "exp_date_field":   None,
        "addr_field":       "ADDRESS",
        "city_state":       "Sioux Falls, SD",
        "skip_date_filter": False,
        "max_records":      None,
    },
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
