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
      latitude/longitude — None; filled by geocode_fill.py
      alert_url       — link to full CTA alert page
    """
    services = _extract_services(alert)
    primary = services[0] if services else {}

    service_type     = str(primary.get("ServiceType") or "")
    service_name     = str(primary.get("ServiceName") or "")
    service_location = str(primary.get("ServiceLocation") or "")

    # Build a geocodable address string.
    # Rail alerts include named segments like "Howard-95th/Dan Ryan".
    # Bus alerts often have route numbers which aren't useful as addresses.
    if service_location:
        address = f"{service_location}, Chicago, IL"
    else:
        address = "Chicago, IL"

    return {
        "alert_id":          str(alert.get("AlertId") or ""),
        "headline":          str(alert.get("Headline") or ""),
        "short_description": str(alert.get("ShortDescription") or ""),
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
        "latitude":          None,   # filled by geocode_fill.py
        "longitude":         None,
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
