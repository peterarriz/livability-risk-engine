"""
backend/ingest/chicago_film_permits.py
task: data-036
lane: data

Ingests Chicago Film Permits from the City of Chicago Socrata API.
Film shoots cause active street closures, parking restrictions, and
lane blockages — they are medium-severity disruption events.

Source:
  https://data.cityofchicago.org/resource/ivkd-2m2v.json
  Dataset: Film Permits — Chicago DCASE

Usage:
  python backend/ingest/chicago_film_permits.py
  python backend/ingest/chicago_film_permits.py --days-back 60 --dry-run
  python backend/ingest/chicago_film_permits.py --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-036):
  - Script pulls film permit records from the Socrata API.
  - Raw records are filtered to the lookback window and key fields retained.
  - Output is written to data/raw/chicago_film_permits.json.
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

SOCRATA_URL = "https://data.cityofchicago.org/resource/c2az-nhru.json"

# Fields to retain from the raw film permit record.
# Dataset: "Filming Permits - Transportation Department" (c2az-nhru)
# Verified 2026-03-20 via catalog API.
FIELDS_TO_KEEP = [
    "applicationnumber",        # stable unique identifier
    "applicationstartdate",     # permit start date/time
    "applicationenddate",       # permit end date/time
    "applicationtype",          # type (e.g. "Filming")
    "applicationdescription",   # description of filming activity
    "applicationstatus",        # status (Issued, Complete, etc.)
    "streetname",               # street being used
    "streetnumberfrom",         # block number start
    "streetnumberto",           # block number end
    "direction",                # street direction
    "streetclosure",            # whether street is closed
    "latitude",
    "longitude",
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = Path("data/raw/chicago_film_permits.json")

# Lookback + forward window. Film permits are filed in advance;
# fetch permits active within the window (applicationstartdate through now + 30 days).
DAYS_BACK = 90
DAYS_FORWARD = 30


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def fetch_permits(
    app_token: str | None,
    days_back: int,
    days_forward: int,
    dry_run: bool,
) -> list[dict]:
    """
    Paginate through the Socrata API and return film permits active
    within the lookback + forward window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    now = datetime.now(timezone.utc)
    cutoff_start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00")
    cutoff_end   = (now + timedelta(days=days_forward)).strftime("%Y-%m-%dT23:59:59")

    # Fetch permits where the start is within our window (not yet expired).
    where_clause = f"applicationstartdate >= '{cutoff_start}' AND applicationstartdate <= '{cutoff_end}'"

    print(f"Fetching Chicago film permits (last {days_back} days + next {days_forward} days)...")

    while True:
        params: dict = {
            "$limit":  PAGE_SIZE,
            "$offset": offset,
            "$where":  where_clause,
            "$order":  "applicationstartdate DESC",
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
    if ("latitude" not in filtered or "longitude" not in filtered):
        loc = record.get("location", {})
        if isinstance(loc, dict):
            coords = loc.get("coordinates", [])
            if len(coords) == 2:
                filtered.setdefault("longitude", str(coords[0]))
                filtered.setdefault("latitude", str(coords[1]))

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw film permit records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source":       "chicago_film_permits",
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
        description="Ingest Chicago film permits from the Socrata API."
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
        records = fetch_permits(app_token, args.days_back, args.days_forward, args.dry_run)
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
