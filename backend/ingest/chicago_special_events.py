"""
backend/ingest/chicago_special_events.py
task: data-036
lane: data

Ingests Chicago Special Events Permits from the City of Chicago Socrata API.
Large public events (festivals, parades, marathons, street fairs) cause
significant traffic disruption, parking restrictions, and road closures.

Source:
  https://data.cityofchicago.org/resource/r5kz-chrr.json
  Dataset: Special Events Permits — Chicago DCASE

Usage:
  python backend/ingest/chicago_special_events.py
  python backend/ingest/chicago_special_events.py --days-back 60 --dry-run
  python backend/ingest/chicago_special_events.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-036):
  - Script pulls special event permit records from the Socrata API.
  - Raw records are filtered to the lookback + forward window and key fields retained.
  - Output is written to data/raw/chicago_special_events.json.
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

SOCRATA_URL = "https://data.cityofchicago.org/resource/r5kz-chrr.json"

# Fields to retain from the raw special events license record.
# Dataset r5kz-chrr is the Chicago Business Licenses dataset, filtered
# to special-event license types. Verified 2026-03-20.
FIELDS_TO_KEEP = [
    "id",                    # stable unique identifier
    "license_description",   # e.g. "Special Event Food"
    "doing_business_as_name",# event/vendor name
    "date_issued",           # license issue date
    "expiration_date",       # license expiration
    "license_start_date",    # when the event/license starts
    "license_status",        # AAI, AAC, etc.
    "address",               # venue address
    "community_area_name",   # Chicago community area
    "latitude",
    "longitude",
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_special_events.json")

# Lookback + forward window.
DAYS_BACK = 60
DAYS_FORWARD = 90


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def fetch_events(
    app_token: str | None,
    days_back: int,
    days_forward: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through the Socrata API and return special event permits
    active within the lookback + forward window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    now = datetime.now(timezone.utc)
    cutoff_start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00")
    cutoff_end   = (now + timedelta(days=days_forward)).strftime("%Y-%m-%dT23:59:59")

    # Filter to special-event license types within the date window.
    where_clause = (
        f"date_issued >= '{cutoff_start}' AND date_issued <= '{cutoff_end}' "
        f"AND license_description like '%Special Event%'"
    )

    print(f"Fetching Chicago special events permits (last {days_back} days + next {days_forward} days)...")

    while True:
        params: dict = {
            "$limit":  PAGE_SIZE,
            "$offset": offset,
            "$where":  where_clause,
            "$order":  "date_issued DESC",
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
            filtered.setdefault("latitude", loc.get("latitude"))
            filtered.setdefault("longitude", loc.get("longitude"))

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw special event permit records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "chicago_special_events",
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
        description="Ingest Chicago special events permits from the Socrata API."
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
        "--days-forward",
        type=int,
        default=DAYS_FORWARD,
        help=f"Number of days forward to fetch (default: {DAYS_FORWARD}).",
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
        records = fetch_events(app_token, args.days_back, args.days_forward, args.dry_run)
    except Exception as exc:
        print(f"ERROR: fetch failed — {exc}", file=sys.stderr)
        sys.exit(1)

    normalized = [filter_fields(r) for r in records]
    print(f"\nTotal records fetched: {len(normalized)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if normalized:
            print(f"Sample record:\n{json.dumps(normalized[0], indent=2)}")
        return

    write_staging_file(normalized, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
