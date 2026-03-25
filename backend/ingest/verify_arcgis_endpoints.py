"""
backend/ingest/verify_arcgis_endpoints.py
task: data-066, data-067
lane: data

Verifies all AZ city ArcGIS org IDs and FeatureServer endpoints.
Run this script locally (with network access) to confirm org IDs are valid
and to discover correct service names and field names.

Usage:
  python backend/ingest/verify_arcgis_endpoints.py
  python backend/ingest/verify_arcgis_endpoints.py --city gilbert
  python backend/ingest/verify_arcgis_endpoints.py --discover --city tempe
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# AZ city org IDs to verify — update these after confirmation.
# ---------------------------------------------------------------------------
AZ_CITIES: list[dict[str, Any]] = [
    {
        "city": "gilbert",
        "org_id": "UNKNOWN",  # K1VMQDQNLVxLvLqs confirmed INVALID (data-065)
        "crime_service": "GPD_Crime_Incidents",  # MUST VERIFY
        "permit_service": "Building_Permits",     # MUST VERIFY
        "date_field": "IncidentDate",             # MUST VERIFY
        "group_field": "District",                # MUST VERIFY
        "portal": "https://data.gilbertaz.gov",
        "note": (
            "Org ID K1VMQDQNLVxLvLqs confirmed INVALID (400 Invalid URL). "
            "Visit data.gilbertaz.gov → find crime dataset → click API → "
            "extract org ID from FeatureServer URL."
        ),
    },
    {
        "city": "tempe",
        "org_id": "e5BBQV9bLnUqzr4V",
        "crime_service": "TPD_Crime_Incidents",
        "permit_service": "Building_Permits",
        "date_field": "IncidentDate",
        "group_field": "District",
        "portal": "https://data.tempe.gov",
        "note": "MUST VERIFY — added in data-065 without live confirmation.",
    },
    {
        "city": "peoria_az",
        "org_id": "ZNh2Q3xZvn5AJFGZ",
        "crime_service": "PPD_Crime_Incidents",
        "permit_service": "Building_Permits",
        "date_field": "IncidentDate",
        "group_field": "District",
        "portal": "https://data.peoriaaz.gov",
        "note": "MUST VERIFY — added in data-065 without live confirmation.",
    },
    {
        "city": "surprise_az",
        "org_id": "QJfxWS1GiDHgQMwH",
        "crime_service": "SPD_Crime_Incidents",
        "permit_service": "Building_Permits",
        "date_field": "IncidentDate",
        "group_field": "District",
        "portal": "https://data.surpriseaz.gov",
        "note": "MUST VERIFY — added in data-065 without live confirmation.",
    },
    {
        "city": "goodyear_az",
        "org_id": "aMqXhGKtSoqR5lNw",
        "crime_service": "GoPD_Crime_Incidents",
        "permit_service": "Building_Permits",
        "date_field": "IncidentDate",
        "group_field": "District",
        "portal": "https://data.goodyearaz.gov",
        "note": "MUST VERIFY — added in data-065 without live confirmation.",
    },
]


def check_org(org_id: str, timeout: int = 15) -> dict[str, Any]:
    """Return info about an ArcGIS org ID. Returns error dict if invalid."""
    if org_id == "UNKNOWN":
        return {"error": {"code": -1, "message": "Org ID is UNKNOWN — manual lookup required"}}
    url = f"https://services.arcgis.com/{org_id}/arcgis/rest/services?f=json"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def check_featureserver(org_id: str, service: str, timeout: int = 15) -> dict[str, Any]:
    """Check if a FeatureServer/0 endpoint exists and returns layer info."""
    url = (
        f"https://services.arcgis.com/{org_id}/arcgis/rest/services"
        f"/{service}/FeatureServer/0?f=json"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def discover_services(org_id: str, timeout: int = 15) -> list[str]:
    """Return list of service names for an org."""
    data = check_org(org_id, timeout)
    if "error" in data:
        return []
    return [s["name"] for s in data.get("services", [])]


def verify_city(city_cfg: dict[str, Any], discover: bool = False) -> None:
    """Run all checks for a city config and print results."""
    city = city_cfg["city"]
    org_id = city_cfg["org_id"]

    print(f"\n{'='*60}")
    print(f"City: {city}  Org: {org_id}")
    if city_cfg.get("note"):
        print(f"Note: {city_cfg['note']}")
    print(f"Portal: {city_cfg['portal']}")

    # 1. Check org validity
    print(f"\n[1] Org check: services.arcgis.com/{org_id}/arcgis/rest/services")
    try:
        org_data = check_org(org_id)
        if "error" in org_data:
            print(f"    FAIL — {org_data['error']}")
            print(f"    ACTION: Visit {city_cfg['portal']} to find correct org ID.")
            return
        svc_names = [s["name"] for s in org_data.get("services", [])]
        print(f"    OK — {len(svc_names)} services found")
        if discover:
            for name in svc_names:
                print(f"      • {name}")
    except Exception as exc:
        print(f"    ERROR — {exc}")
        return

    # 2. Check crime FeatureServer
    crime_svc = city_cfg["crime_service"]
    print(f"\n[2] Crime service: {crime_svc}/FeatureServer/0")
    try:
        fs_data = check_featureserver(org_id, crime_svc)
        if "error" in fs_data:
            print(f"    FAIL — {fs_data['error']}")
            matching = [s for s in svc_names if "crime" in s.lower() or "incident" in s.lower()]
            if matching:
                print(f"    HINT: Possible services: {matching}")
        else:
            layer_name = fs_data.get("name", "?")
            fields = [f["name"] for f in fs_data.get("fields", [])]
            print(f"    OK — layer: {layer_name}")
            date_f = city_cfg["date_field"]
            group_f = city_cfg["group_field"]
            date_ok = date_f in fields
            group_ok = group_f in fields
            print(f"    date_field  '{date_f}': {'FOUND' if date_ok else 'MISSING — check fields below'}")
            print(f"    group_field '{group_f}': {'FOUND' if group_ok else 'MISSING — check fields below'}")
            if not date_ok or not group_ok:
                date_candidates = [f for f in fields if "date" in f.lower() or "time" in f.lower()]
                geo_candidates = [f for f in fields if any(
                    k in f.lower() for k in ("district", "precinct", "beat", "zone", "area", "division")
                )]
                print(f"    Date-like fields: {date_candidates}")
                print(f"    Geo-like fields:  {geo_candidates}")
    except Exception as exc:
        print(f"    ERROR — {exc}")

    # 3. Check permit FeatureServer
    permit_svc = city_cfg["permit_service"]
    print(f"\n[3] Permit service: {permit_svc}/FeatureServer/0")
    try:
        fs_data = check_featureserver(org_id, permit_svc)
        if "error" in fs_data:
            print(f"    FAIL — {fs_data['error']}")
            matching = [s for s in svc_names if "permit" in s.lower() or "build" in s.lower()]
            if matching:
                print(f"    HINT: Possible services: {matching}")
        else:
            layer_name = fs_data.get("name", "?")
            fields = [f["name"] for f in fs_data.get("fields", [])]
            print(f"    OK — layer: {layer_name}")
            permit_fields = ["PERMIT_NUM", "PERMIT_TYPE", "DESCRIPTION", "ISSUED_DATE", "ADDRESS"]
            for pf in permit_fields:
                found = pf in fields
                print(f"    field '{pf}': {'FOUND' if found else 'MISSING'}")
    except Exception as exc:
        print(f"    ERROR — {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify AZ city ArcGIS endpoints. Run locally with network access."
    )
    parser.add_argument(
        "--city",
        choices=[c["city"] for c in AZ_CITIES] + ["all"],
        default="all",
        help="Which city to verify (default: all)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="List all services for each org (slow — one request per city)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    cities = AZ_CITIES if args.city == "all" else [
        c for c in AZ_CITIES if c["city"] == args.city
    ]

    print("AZ City ArcGIS Endpoint Verification")
    print("Run locally with network access. CI network is restricted.")

    results: dict[str, str] = {}
    for cfg in cities:
        verify_city(cfg, discover=args.discover)
        results[cfg["city"]] = cfg["org_id"]

    print(f"\n{'='*60}")
    print("Summary:")
    for city, org_id in results.items():
        status = "UNKNOWN" if org_id == "UNKNOWN" else "unverified"
        print(f"  {city}: org={org_id} ({status})")

    print("\nNext steps:")
    print("  1. For any FAIL results, visit the portal URL and find the correct FeatureServer URL.")
    print("  2. Update FEATURESERVER_URL in the crime script.")
    print("  3. Update service_url in us_city_permits_arcgis.py.")
    print("  4. Update SKILL.md ArcGIS-Based table.")
    print("  5. Re-run this script to confirm.")


if __name__ == "__main__":
    main()
