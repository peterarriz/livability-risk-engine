"""
backend/ingest/chicago_divvy_stations.py
task: data-035
lane: data

Ingests Divvy Bike Station status from the GBFS (General Bikeshare Feed
Specification) API and writes out-of-service station records to a staging file.

Out-of-service Divvy stations cause pedestrian detours and reduced mobility
options. This is a LOW-severity signal (light_permit weight) in the scoring model.

Source:
  GBFS autodiscovery: https://gbfs.divvybikes.com/gbfs/gbfs.json
  Station information: https://gbfs.divvybikes.com/gbfs/en/station_information.json
  Station status:      https://gbfs.divvybikes.com/gbfs/en/station_status.json

  Lyft also serves at: https://gbfs.lyft.com/gbfs/1.1/bss_chicago/en/station_status.json
  Either URL should work; PRIMARY_URL is tried first with fallback to FALLBACK_URL.

No API key is required — the Divvy GBFS API is public.

A station is considered "out of service" when:
  - is_installed == 0  (station removed / in relocation), OR
  - is_renting == 0 AND is_returning == 0  (station closed for maintenance)

Usage:
  python backend/ingest/chicago_divvy_stations.py
  python backend/ingest/chicago_divvy_stations.py --dry-run
  python backend/ingest/chicago_divvy_stations.py --output data/raw/chicago_divvy_stations.json

Acceptance criteria (data-035):
  - Script fetches station_information and station_status from GBFS.
  - Only out-of-service stations are written to the staging file.
  - Records include lat/lon from station_information.
  - Output is written to data/raw/chicago_divvy_stations.json.
  - Script is idempotent: re-running overwrites the output file cleanly.
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

GBFS_STATION_INFO_URL    = "https://gbfs.divvybikes.com/gbfs/en/station_information.json"
GBFS_STATION_STATUS_URL  = "https://gbfs.divvybikes.com/gbfs/en/station_status.json"

# Fallback Lyft-hosted URLs if primary is unreachable.
GBFS_STATION_INFO_FALLBACK   = "https://gbfs.lyft.com/gbfs/1.1/bss_chicago/en/station_information.json"
GBFS_STATION_STATUS_FALLBACK = "https://gbfs.lyft.com/gbfs/1.1/bss_chicago/en/station_status.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_divvy_stations.json")


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_json(session: requests.Session, primary_url: str, fallback_url: str) -> dict:
    """
    Fetch JSON from primary_url, falling back to fallback_url on failure.
    Returns the parsed JSON dict.
    """
    for url in (primary_url, fallback_url):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            print(f"  Fetched: {url}")
            return resp.json()
        except requests.exceptions.RequestException as exc:
            print(f"  WARN: {url} failed — {exc}. Trying fallback...", file=sys.stderr)

    raise RuntimeError(
        f"Both primary ({primary_url}) and fallback ({fallback_url}) URLs failed."
    )


def fetch_station_info(session: requests.Session) -> dict[str, dict]:
    """
    Fetch GBFS station_information and return a dict keyed by station_id.

    Each value is a dict with: name, lat, lon, capacity, address.
    """
    print("Fetching Divvy station information...")
    data = _fetch_json(session, GBFS_STATION_INFO_URL, GBFS_STATION_INFO_FALLBACK)

    stations_raw = data.get("data", {}).get("stations", [])
    print(f"  {len(stations_raw)} stations in information feed.")

    return {
        s["station_id"]: {
            "station_id": s["station_id"],
            "name":       s.get("name", ""),
            "lat":        s.get("lat"),
            "lon":        s.get("lon"),
            "capacity":   s.get("capacity"),
            "address":    s.get("address") or s.get("name", ""),
        }
        for s in stations_raw
        if "station_id" in s
    }


def fetch_station_status(session: requests.Session) -> list[dict]:
    """
    Fetch GBFS station_status and return the raw list of status dicts.
    """
    print("Fetching Divvy station status...")
    data = _fetch_json(session, GBFS_STATION_STATUS_URL, GBFS_STATION_STATUS_FALLBACK)

    stations = data.get("data", {}).get("stations", [])
    print(f"  {len(stations)} stations in status feed.")
    return stations


# ---------------------------------------------------------------------------
# Out-of-service detection
# ---------------------------------------------------------------------------

def _is_out_of_service(status: dict) -> bool:
    """
    Return True if the station is considered out of service.

    Criteria (conservative — only flag fully closed stations):
      - is_installed == 0  (station has been removed / in relocation)
      - is_renting == 0 AND is_returning == 0  (closed for maintenance)
    """
    is_installed  = int(status.get("is_installed", 1))
    is_renting    = int(status.get("is_renting", 1))
    is_returning  = int(status.get("is_returning", 1))

    if is_installed == 0:
        return True
    if is_renting == 0 and is_returning == 0:
        return True
    return False


def _reason(status: dict) -> str:
    """Build a human-readable reason string for the closure."""
    is_installed = int(status.get("is_installed", 1))
    if is_installed == 0:
        return "Station removed / relocated"
    return "Station closed for maintenance (not renting or returning)"


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------

def build_records(
    info_by_id: dict[str, dict],
    statuses: list[dict],
) -> list[dict]:
    """
    Join station_information and station_status.
    Return only out-of-service stations as normalized records.
    """
    records = []
    total_checked = 0
    total_oos = 0

    for status in statuses:
        station_id = str(status.get("station_id", ""))
        if not station_id:
            continue

        total_checked += 1

        if not _is_out_of_service(status):
            continue

        total_oos += 1
        info = info_by_id.get(station_id, {})

        records.append({
            "station_id":         station_id,
            "name":               info.get("name", f"Station {station_id}"),
            "address":            info.get("address", ""),
            "latitude":           str(info["lat"])  if info.get("lat")  is not None else None,
            "longitude":          str(info["lon"])  if info.get("lon")  is not None else None,
            "capacity":           info.get("capacity"),
            "is_installed":       status.get("is_installed"),
            "is_renting":         status.get("is_renting"),
            "is_returning":       status.get("is_returning"),
            "num_bikes_available": status.get("num_bikes_available"),
            "num_docks_available": status.get("num_docks_available"),
            "reason":             _reason(status),
            "last_reported":      status.get("last_reported"),
        })

    print(f"  Checked {total_checked} stations; {total_oos} out of service.")
    return records


# ---------------------------------------------------------------------------
# Staging file writer
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write out-of-service Divvy station records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "chicago_divvy_stations",
        "source_url":   GBFS_STATION_STATUS_URL,
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records":      records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(records)} out-of-service records to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Divvy bike station closures from the GBFS API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = requests.Session()

    try:
        info_by_id = fetch_station_info(session)
        statuses   = fetch_station_status(session)
    except Exception as exc:
        print(f"ERROR: Divvy GBFS fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    records = build_records(info_by_id, statuses)
    print(f"\nTotal out-of-service stations: {len(records)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"\nSample record:\n{json.dumps(records[0], indent=2)}")
        else:
            print("(No out-of-service stations found.)")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
