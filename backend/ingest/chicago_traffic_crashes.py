"""
backend/ingest/chicago_traffic_crashes.py
task: data-035
lane: data

Ingests Chicago Traffic Crashes from the City of Chicago Socrata API.
Recent crashes (last N days) represent active disruption zones — crash scenes
with injuries or tow requirements cause lane blockages and emergency response.

Source:
  https://data.cityofchicago.org/resource/85ca-t3if.json
  Dataset: Traffic Crashes - Crashes (Chicago CDOT / CPD)

Usage:
  python backend/ingest/chicago_traffic_crashes.py
  python backend/ingest/chicago_traffic_crashes.py --days-back 7 --dry-run
  python backend/ingest/chicago_traffic_crashes.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-035):
  - Script pulls recent crash records from the Socrata API.
  - Raw records are filtered to the lookback window and key fields retained.
  - Output is written to data/raw/chicago_traffic_crashes.json.
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

SOCRATA_URL = "https://data.cityofchicago.org/resource/85ca-t3if.json"

# Fields to retain from the raw crash record.
FIELDS_TO_KEEP = [
    "crash_record_id",    # stable unique identifier
    "crash_date",         # ISO datetime of crash
    "crash_type",         # "INJURY AND/OR TOW DUE TO CRASH" | "NO INJURY / DRIVE AWAY"
    "most_severe_injury", # "FATAL" | "INCAPACITATING INJURY" | etc.
    "injuries_total",
    "num_units",          # number of vehicles involved
    "street_no",          # street number
    "street_direction",   # N/S/E/W
    "street_name",
    "latitude",
    "longitude",
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_traffic_crashes.json")

# How many days back to fetch. Crash scenes are short-lived disruptions;
# 30 days captures recent-history risk clusters at an intersection level.
DAYS_BACK = 30


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def fetch_crashes(
    app_token: str | None,
    days_back: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through the Socrata API and return all raw crash records
    within the lookback window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime("%Y-%m-%dT00:00:00")

    print(f"Fetching Chicago traffic crashes (last {days_back} days)...")

    while True:
        params: dict = {
            "$limit":  PAGE_SIZE,
            "$offset": offset,
            "$where":  f"crash_date >= '{cutoff_str}'",
            "$order":  "crash_date DESC",
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
    return {k: v for k, v in record.items() if k in FIELDS_TO_KEEP}


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw crash records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "chicago_traffic_crashes",
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
        description="Ingest Chicago traffic crashes from the Socrata API."
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
        records = fetch_crashes(app_token, args.days_back, args.dry_run)
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
