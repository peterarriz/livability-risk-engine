"""
backend/ingest/cta_alerts.py
task: data-034
lane: data

Ingests CTA planned service alerts (construction, track work, station closures)
from the transitchicago.com Alerts API and writes raw records to a local JSON
staging file.

Source:
  https://www.transitchicago.com/developers/alerts/
  API: https://lapi.transitchicago.com/api/1.0/alerts.aspx?outputType=JSON&planned=1

No API key is required — the CTA Alerts API is public.

The ?planned=1 parameter returns upcoming / planned service changes only
(track work, station closures for renovation, reroutes due to construction,
etc.). Omit --all to keep the default planned-only filter, which avoids
flooding the pipeline with active weather delays or incident alerts.

Location comes from ImpactedService.Service[].ServiceLocation (e.g.
"Howard-95th/Dan Ryan" for rail, route number for bus). These strings are
passed through geocode_fill.py for coordinate lookup. Records that still have
no coordinates after geocoding are dropped by load_projects.py.

Usage:
  # Fetch planned alerts only (default)
  python backend/ingest/cta_alerts.py

  # Fetch all alerts (planned + active)
  python backend/ingest/cta_alerts.py --all

  # Dry-run (fetch but do not write file)
  python backend/ingest/cta_alerts.py --dry-run

  # Custom output path
  python backend/ingest/cta_alerts.py --output data/raw/cta_alerts.json

Acceptance criteria (data-034):
  - Alerts are fetched from the CTA Alerts REST API.
  - Raw alert records are normalized to a consistent internal schema.
  - Output is written to data/raw/cta_alerts.json.
  - Script is idempotent: re-running overwrites the output file.
  - --dry-run mode fetches and reports without writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CTA_ALERTS_URL = "https://lapi.transitchicago.com/api/1.0/alerts.aspx"
DEFAULT_OUTPUT_PATH = Path("data/raw/cta_alerts.json")

# CTA service type codes (returned in ImpactedService.Service[].ServiceType).
SERVICE_TYPE_RAIL = "T"
SERVICE_TYPE_BUS  = "B"

# ---------------------------------------------------------------------------
# CTA station / line coordinate lookup
# ---------------------------------------------------------------------------
# Built from Chicago Data Portal "CTA - System Information - List of 'L' Stops"
# (dataset 8pix-ypme). Station names map to representative coordinates.
# For stations with multiple platforms, a single representative point is used.

CTA_STATION_COORDS: dict[str, tuple[float, float]] = {
    "18th":                     (41.857908, -87.669147),
    "35th-Bronzeville-IIT":     (41.831677, -87.625826),
    "35th/Archer":              (41.829353, -87.680622),
    "43rd":                     (41.816462, -87.619021),
    "47th":                     (41.809209, -87.618826),
    "51st":                     (41.802090, -87.618487),
    "54th/Cermak":              (41.851773, -87.756692),
    "63rd":                     (41.780536, -87.630952),
    "69th":                     (41.768367, -87.625724),
    "79th":                     (41.750419, -87.625112),
    "87th":                     (41.735372, -87.624717),
    "95th/Dan Ryan":            (41.722377, -87.624342),
    "Adams/Wabash":             (41.879507, -87.626037),
    "Addison":                  (41.947028, -87.674642),
    "Argyle":                   (41.973453, -87.658530),
    "Armitage":                 (41.918217, -87.652644),
    "Ashland":                  (41.885269, -87.666969),
    "Ashland/63rd":             (41.778860, -87.663766),
    "Austin":                   (41.870851, -87.776812),
    "Belmont":                  (41.938132, -87.712359),
    "Berwyn":                   (41.977984, -87.658668),
    "Bryn Mawr":                (41.983504, -87.658840),
    "California":               (41.884220, -87.696234),
    "Central":                  (41.887389, -87.765650),
    "Central Park":             (41.853839, -87.714842),
    "Cermak-Chinatown":         (41.853206, -87.630968),
    "Cermak-McCormick Place":   (41.853115, -87.626402),
    "Chicago":                  (41.896810, -87.635924),
    "Cicero":                   (41.886519, -87.744698),
    "Clark/Division":           (41.903920, -87.631412),
    "Clark/Lake":               (41.885737, -87.630886),
    "Clinton":                  (41.885678, -87.641782),
    "Conservatory":             (41.884904, -87.716523),
    "Cottage Grove":            (41.780309, -87.605857),
    "Cumberland":               (41.984246, -87.838028),
    "Damen":                    (41.884974, -87.676891),
    "Davis":                    (42.047710, -87.683543),
    "Dempster":                 (42.041655, -87.681602),
    "Dempster-Skokie":          (42.038951, -87.751919),
    "Division":                 (41.903355, -87.666496),
    "Diversey":                 (41.932732, -87.653131),
    "Forest Park":              (41.874257, -87.817318),
    "Foster":                   (41.976258, -87.659551),
    "Francisco":                (41.966046, -87.701644),
    "Fullerton":                (41.925051, -87.652866),
    "Garfield":                 (41.795420, -87.631157),
    "Grand":                    (41.891665, -87.628021),
    "Granville":                (41.993664, -87.659202),
    "Halsted":                  (41.778943, -87.644244),
    "Harlem/Lake":              (41.886848, -87.803176),
    "Harlem":                   (41.886848, -87.803176),
    "Harrison":                 (41.874039, -87.627479),
    "Howard":                   (42.019063, -87.672892),
    "Illinois Medical District":(41.875706, -87.673932),
    "Indiana":                  (41.821732, -87.621371),
    "Irving Park":              (41.952925, -87.729229),
    "Jackson":                  (41.878183, -87.629296),
    "Jarvis":                   (42.015876, -87.669092),
    "Jefferson Park":           (41.970634, -87.760892),
    "Kedzie":                   (41.804236, -87.704406),
    "Kimball":                  (41.967901, -87.713065),
    "King Drive":               (41.780130, -87.615546),
    "Kostner":                  (41.853751, -87.733258),
    "Lake":                     (41.884809, -87.627813),
    "Laramie":                  (41.887163, -87.754986),
    "LaSalle":                  (41.876800, -87.631739),
    "LaSalle/Van Buren":        (41.876800, -87.631739),
    "Lawrence":                 (41.969139, -87.658493),
    "Linden":                   (42.073153, -87.690730),
    "Logan Square":             (41.929728, -87.708541),
    "Loyola":                   (42.001073, -87.661061),
    "Main":                     (42.033456, -87.679538),
    "Merchandise Mart":         (41.888969, -87.633924),
    "Midway":                   (41.786610, -87.737875),
    "Monroe":                   (41.880745, -87.627696),
    "Montrose":                 (41.961539, -87.743574),
    "Morgan":                   (41.885586, -87.652193),
    "Morse":                    (42.008362, -87.665909),
    "North/Clybourn":           (41.910655, -87.649177),
    "Noyes":                    (42.058282, -87.683337),
    "O'Hare":                   (41.977665, -87.904223),
    "Oak Park":                 (41.886988, -87.793783),
    "Oakton-Skokie":            (42.026243, -87.747221),
    "Paulina":                  (41.943623, -87.670907),
    "Polk":                     (41.871551, -87.669530),
    "Pulaski":                  (41.885412, -87.725404),
    "Quincy/Wells":             (41.878723, -87.633740),
    "Racine":                   (41.875920, -87.659458),
    "Ridgeland":                (41.887159, -87.783661),
    "Roosevelt":                (41.867368, -87.627402),
    "Rosemont":                 (41.983507, -87.859388),
    "Sedgwick":                 (41.910409, -87.639302),
    "Sheridan":                 (41.953775, -87.654929),
    "South Boulevard":          (42.027612, -87.678329),
    "Southport":                (41.943744, -87.663619),
    "State/Lake":               (41.885740, -87.627835),
    "Thorndale":                (41.990259, -87.659076),
    "UIC-Halsted":              (41.875474, -87.649707),
    "Washington":               (41.883164, -87.629440),
    "Washington/Wabash":        (41.882695, -87.633780),
    "Washington/Wells":         (41.882695, -87.633780),
    "Wellington":               (41.936033, -87.653266),
    "Western":                  (41.966163, -87.688502),
    "Wilson":                   (41.964273, -87.657588),
}

# Line-level centroids — used when an alert references an entire line
# rather than a specific station. Coordinates are approximate midpoints.
CTA_LINE_COORDS: dict[str, tuple[float, float]] = {
    "Red Line":    (41.867368, -87.627402),   # Roosevelt (midpoint of line)
    "Blue Line":   (41.875474, -87.649707),   # UIC-Halsted
    "Green Line":  (41.885269, -87.666969),   # Ashland
    "Orange Line": (41.829353, -87.680622),   # 35th/Archer
    "Purple Line": (42.047710, -87.683543),   # Davis
    "Pink Line":   (41.857908, -87.669147),   # 18th
    "Brown Line":  (41.943744, -87.663619),   # Southport
    "Yellow Line": (42.038951, -87.751919),   # Dempster-Skokie
}


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def fetch_alerts(planned_only: bool = True) -> list[dict]:
    """
    Fetch CTA service alerts from the transitchicago.com Alerts API.

    Args:
        planned_only: If True, request only planned/upcoming alerts
                      (track work, station closures). If False, fetch all.

    Returns:
        List of raw alert dicts from the API response.

    Raises:
        requests.exceptions.RequestException: on network/HTTP failure.
        RuntimeError: if the API returns an error code.
    """
    params: dict = {"outputType": "JSON"}
    if planned_only:
        params["planned"] = "true"

    label = "planned alerts" if planned_only else "all alerts"
    print(f"Fetching CTA service alerts ({label})...")
    print(f"  URL: {CTA_ALERTS_URL}")

    try:
        response = requests.get(CTA_ALERTS_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print("  ERROR: Request timed out.", file=sys.stderr)
        raise
    except requests.exceptions.HTTPError as exc:
        print(
            f"  ERROR: HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}",
            file=sys.stderr,
        )
        raise

    data = response.json()
    alerts_root = data.get("CTAAlerts", {})

    error_code = str(alerts_root.get("ErrorCode", "0"))
    if error_code != "0":
        error_msg = alerts_root.get("ErrorMessage", "Unknown API error")
        print(f"  ERROR: CTA API error {error_code}: {error_msg}", file=sys.stderr)
        raise RuntimeError(f"CTA API returned error {error_code}: {error_msg}")

    alerts = alerts_root.get("Alert", [])

    # API returns a dict (not list) when only one alert exists.
    if isinstance(alerts, dict):
        alerts = [alerts]

    print(f"  Fetched {len(alerts)} alert(s).")
    return alerts


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _parse_cta_date(value: str | None) -> str | None:
    """
    Parse a CTA date string to ISO 8601.

    CTA uses a non-standard format: "1/1/2026 5:00:00 AM"
    """
    if not value:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _extract_services(alert: dict) -> list[dict]:
    """Extract the ImpactedService.Service list from a raw alert dict."""
    impacted = alert.get("ImpactedService") or {}
    services = impacted.get("Service", [])
    # API returns a dict when only one service is impacted.
    if isinstance(services, dict):
        services = [services]
    return services if isinstance(services, list) else []


def _resolve_coords(
    service_type: str,
    service_name: str,
    headline: str,
    description: str,
) -> tuple[float | None, float | None, str]:
    """
    Resolve lat/lon for a CTA alert using station/line lookup tables.

    Resolution order:
      1. Direct station name match on service_name
      2. Station name extracted from headline text
      3. Station name extracted from description text
      4. Line-level centroid for rail line names
      5. Bus route → street address for geocode_fill fallback

    Returns (lat, lon, address).
    """
    # 1. Direct station match on service_name
    if service_name in CTA_STATION_COORDS:
        lat, lon = CTA_STATION_COORDS[service_name]
        return lat, lon, f"{service_name} station, Chicago, IL"

    # 2–3. Scan headline and description for station names.
    # Sort by length descending so "35th-Bronzeville-IIT" matches before "35th".
    stations_by_length = sorted(CTA_STATION_COORDS.keys(), key=len, reverse=True)
    for text in (headline, description):
        if not text:
            continue
        for station in stations_by_length:
            if station in text:
                lat, lon = CTA_STATION_COORDS[station]
                return lat, lon, f"{station} station, Chicago, IL"

    # 4. Line-level centroid
    if service_name in CTA_LINE_COORDS:
        lat, lon = CTA_LINE_COORDS[service_name]
        return lat, lon, f"{service_name}, Chicago, IL"

    # 5. Bus routes — service_name is typically a Chicago street name.
    # Build a geocodable address for the geocode_fill step.
    if service_type == SERVICE_TYPE_BUS and service_name:
        return None, None, f"{service_name} Ave, Chicago, IL"

    return None, None, "Chicago, IL"


def normalize_alert(alert: dict) -> dict:
    """
    Map a raw CTA alert dict to a consistent internal schema.

    Output fields:
      alert_id        — unique alert identifier
      headline        — short human-readable title
      short_description — extended summary
      impact          — CTA impact string (e.g. "Planned Service Change")
      severity_score  — numeric 1–10 from CTA
      is_major        — "1" if CTA flagged as major alert
      is_tbd          — "1" if end date is to-be-determined
      event_start     — ISO 8601 start datetime (UTC)
      event_end       — ISO 8601 end datetime (UTC), or None if TBD
      service_type    — "T" (rail) or "B" (bus)
      service_name    — route name (e.g. "Red", "Blue", "66")
      service_location — CTA location label (used as geocoding address)
      address         — geocoding address string
      latitude/longitude — resolved from station lookup, or None for geocode_fill
      alert_url       — link to full CTA alert page
    """
    services = _extract_services(alert)
    primary = services[0] if services else {}

    service_type     = str(primary.get("ServiceType") or "")
    service_name     = str(primary.get("ServiceName") or "")
    service_location = str(primary.get("ServiceLocation") or "")
    headline         = str(alert.get("Headline") or "")
    description      = str(alert.get("ShortDescription") or "")

    lat, lon, address = _resolve_coords(
        service_type, service_name, headline, description,
    )

    return {
        "alert_id":          str(alert.get("AlertId") or ""),
        "headline":          headline,
        "short_description": description,
        "impact":            str(alert.get("Impact") or ""),
        "severity_score":    str(alert.get("SeverityScore") or ""),
        "is_major":          str(alert.get("MajorAlert") or "0"),
        "is_tbd":            str(alert.get("TBD") or "0"),
        "event_start":       _parse_cta_date(alert.get("EventStart")),
        "event_end":         _parse_cta_date(alert.get("EventEnd")),
        "service_type":      service_type,
        "service_name":      service_name,
        "service_location":  service_location,
        "address":           address,
        "latitude":          str(lat) if lat is not None else None,
        "longitude":         str(lon) if lon is not None else None,
        "alert_url":         str(alert.get("AlertURL") or ""),
    }


# ---------------------------------------------------------------------------
# Staging file writer
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write normalized CTA alert records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "cta_alerts",
        "source_url":   CTA_ALERTS_URL,
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records":      records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"  Wrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest CTA planned service alerts (construction, track work, "
            "station closures) from the transitchicago.com Alerts API."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Fetch all alerts including active non-construction ones. "
            "Default: planned/upcoming alerts only."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch alerts but do not write the output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    planned_only = not args.all

    try:
        raw_alerts = fetch_alerts(planned_only=planned_only)
    except Exception as exc:
        print(f"ERROR: CTA alerts fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    records = [normalize_alert(a) for a in raw_alerts]
    print(f"\nTotal records normalized: {len(records)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"\nSample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
