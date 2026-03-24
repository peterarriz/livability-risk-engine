"""
backend/ingest/chicago_311_requests.py
task: data-036
lane: data

Ingests Chicago 311 Service Requests from the City of Chicago Socrata API.
Filters for infrastructure disruption types: potholes, water main breaks,
cave-ins, and tree emergencies that cause lane closures.

Source:
  https://data.cityofchicago.org/resource/v6vf-nfxy.json
  Dataset: 311 Service Requests (All) — Chicago 311 / CDOT

Usage:
  python backend/ingest/chicago_311_requests.py
  python backend/ingest/chicago_311_requests.py --days-back 30 --dry-run
  python backend/ingest/chicago_311_requests.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-036):
  - Script pulls 311 service requests filtered to infrastructure disruption types.
  - Raw records are filtered to the lookback window and key fields retained.
  - Output is written to data/raw/chicago_311_requests.json.
  - Script is idempotent: re-running overwrites the output file cleanly.
  - --dry-run mode fetches one page and reports without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"

# 311 service request types that represent active street-level disruptions.
# These cause lane blockages, emergency response, or hazardous conditions.
DISRUPTION_SR_TYPES = [
    "Pothole in Street",
    "Water Main Break in Street",
    "Cave-In",
    "Pavement Cave-In",
    "Tree Emergency",
    "Street Light - Pole Down",
    "Gas Leak",                   # data-046: Peoples Gas emergency events
]

# Fields to retain from the raw 311 request record.
FIELDS_TO_KEEP = [
    "sr_number",        # stable unique identifier
    "sr_type",          # type of service request
    "created_date",     # ISO datetime request was opened
    "closed_date",      # ISO datetime request was closed (if resolved)
    "status",           # 'Open' | 'Completed' | 'Open - Dup'
    "street_address",   # address of the issue
    "latitude",
    "longitude",
    "location",         # nested location dict (fallback for lat/lon)
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_311_requests.json")

# Lookback window. 311 requests represent active infrastructure issues;
# 90 days captures recent open complaints and recent resolutions.
DAYS_BACK = 90


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def _sr_type_filter() -> str:
    """Build a Socrata SoQL WHERE clause for the configured SR types."""
    quoted = ", ".join(f"'{t}'" for t in DISRUPTION_SR_TYPES)
    return f"sr_type in ({quoted})"


def fetch_requests(
    app_token: str | None,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through the Socrata API and return all 311 service request
    records for configured disruption types within the lookback window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime("%Y-%m-%dT00:00:00")

    # Combine date filter with SR type filter.
    where_clause = (
        f"created_date >= '{cutoff_str}' AND {_sr_type_filter()}"
    )

    print(f"Fetching Chicago 311 service requests (last {days_back} days)...")
    print(f"  Types: {', '.join(DISRUPTION_SR_TYPES)}")

    while True:
        params: dict = {
            "$limit":  PAGE_SIZE,
            "$offset": offset,
            "$where":  where_clause,
            "$order":  "created_date DESC",
        }
        if app_token:
            params["$$app_token"] = app_token

        print(f"  Fetching page at offset {offset}...", end=" ", flush=True)

        try:
            resp = session.get(SOCRATA_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"\n  ERROR: Timed out at offset {offset}.", file=sys.stderr)
            raise
        except requests.exceptions.HTTPError as exc:
            print(
                f"\n  ERROR: HTTP {exc.response.status_code} at offset {offset}: "
                f"{exc.response.text[:200]}",
                file=sys.stderr,
            )
            raise

        records = resp.json()
        print(f"{len(records)} records.")

        if not records:
            break

        all_records.extend(records)
        offset += len(records)

        if dry_run and offset >= PAGE_SIZE:
            print("  Dry-run: stopping after first page.")
            break

        if len(records) < PAGE_SIZE:
            break

    return all_records


# ---------------------------------------------------------------------------
# Filtering and staging
# ---------------------------------------------------------------------------

def filter_fields(record: dict) -> dict:
    """Retain only the fields needed for downstream normalization."""
    filtered = {k: v for k, v in record.items() if k in FIELDS_TO_KEEP}

    # Extract lat/lon from nested location dict if top-level is absent.
    if "latitude" not in filtered or "longitude" not in filtered:
        loc = record.get("location", {})
        if isinstance(loc, dict):
            if "latitude" in loc:
                filtered["latitude"] = loc["latitude"]
            if "longitude" in loc:
                filtered["longitude"] = loc["longitude"]

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw 311 request records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "chicago_311_requests",
        "source_url":   SOCRATA_URL,
        "ingested_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records":      records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Chicago 311 infrastructure service requests from the Socrata API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=DAYS_BACK,
        help=f"Number of days back to fetch (default: {DAYS_BACK}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page only; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("CHICAGO_SOCRATA_APP_TOKEN")

    if not app_token:
        print(
            "Note: CHICAGO_SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register a free token at https://data.cityofchicago.org/profile/app_tokens"
        )

    try:
        records = fetch_requests(app_token, args.days_back, args.dry_run)
    except Exception as exc:
        print(f"ERROR: fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    filtered = [filter_fields(r) for r in records]
    print(f"\nTotal records fetched: {len(filtered)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if filtered:
            print(f"Sample record:\n{json.dumps(filtered[0], indent=2)}")
        return

    write_staging_file(filtered, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
