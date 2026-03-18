"""
backend/ingest/building_permits.py
task: data-002
lane: data

Ingests Chicago Building Permits from the City of Chicago Socrata API
and writes raw records to a local JSON staging file.

Source:
  https://data.cityofchicago.org/resource/ydr8-5enu.json
  Dataset: Building Permits (Chicago OPA)

Usage:
  python backend/ingest/building_permits.py
  python backend/ingest/building_permits.py --output data/raw/building_permits.json
  python backend/ingest/building_permits.py --limit 500 --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-002):
  - Script pulls permits from the Socrata API.
  - Raw records are written to a JSON staging file.
  - Source identifiers (permit_ field) are preserved for traceability.
  - Script is idempotent: re-running overwrites the output file cleanly.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_BASE_URL = "https://data.cityofchicago.org/resource/ydr8-5enu.json"

# Fields to retain from the raw permit record.
# Keep only what the canonical project schema will need so the raw file
# stays lean and auditable. Source identifiers are always preserved.
FIELDS_TO_KEEP = [
    "permit_",            # source identifier — never drop this
    "permit_type",
    "application_start_date",
    "issue_date",
    "expiration_date",
    "work_description",
    "street_number",
    "street_direction",
    "street_name",
    "suffix",
    "latitude",
    "longitude",
    "reported_cost",
    "contact_1_name",
    "_comments",
]

# How many records to fetch per API page. Socrata max is 50000.
PAGE_SIZE = 5000

# Default output path relative to repo root.
DEFAULT_OUTPUT_PATH = "data/raw/building_permits.json"

# How many days back to fetch. Keeps the raw file focused on near-term MVP window.
DAYS_BACK = 90


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def build_params(
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> dict:
    """Build Socrata query params for one page of results."""
    # Filter to permits issued or updated within the lookback window so
    # the raw file stays focused on the MVP near-term scoring window.
    cutoff = datetime.now(timezone.utc)
    cutoff_str = f"{cutoff.year - (days_back // 365)}-{cutoff.month:02d}-{cutoff.day:02d}T00:00:00"

    params: dict = {
        "$limit": limit,
        "$offset": offset,
        "$where": f"issue_date >= '{cutoff_str}'",
        "$order": "issue_date DESC",
    }

    if app_token:
        params["$$app_token"] = app_token

    return params


def fetch_page(session: requests.Session, offset: int, limit: int, app_token: str | None, days_back: int) -> list[dict]:
    """Fetch one page of permit records from Socrata."""
    params = build_params(offset, limit, app_token, days_back)

    try:
        response = session.get(SOCRATA_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"  ERROR: Request timed out at offset {offset}.", file=sys.stderr)
        raise
    except requests.exceptions.HTTPError as exc:
        print(f"  ERROR: HTTP {exc.response.status_code} at offset {offset}: {exc.response.text[:200]}", file=sys.stderr)
        raise

    return response.json()


def fetch_all_permits(app_token: str | None, days_back: int, dry_run: bool) -> list[dict]:
    """
    Paginate through the Socrata API and return all raw permit records
    within the lookback window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print(f"Fetching Chicago building permits (last {days_back} days)...")

    while True:
        print(f"  Fetching page at offset {offset}...", end=" ", flush=True)
        records = fetch_page(session, offset, PAGE_SIZE, app_token, days_back)
        print(f"{len(records)} records.")

        if not records:
            break

        all_records.extend(records)
        offset += len(records)

        if dry_run and offset >= PAGE_SIZE:
            print("  Dry-run: stopping after first page.")
            break

        if len(records) < PAGE_SIZE:
            # Last page — no more data to fetch.
            break

    return all_records


# ---------------------------------------------------------------------------
# Filtering and staging
# ---------------------------------------------------------------------------

def filter_fields(record: dict) -> dict:
    """
    Retain only the fields needed for downstream normalization.
    Always preserve the source identifier regardless of FIELDS_TO_KEEP.
    """
    filtered = {k: v for k, v in record.items() if k in FIELDS_TO_KEEP}

    # Defensive: always keep permit_ even if not in FIELDS_TO_KEEP.
    if "permit_" in record and "permit_" not in filtered:
        filtered["permit_"] = record["permit_"]

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw permit records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source": "chicago_building_permits",
        "source_url": SOCRATA_BASE_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Chicago building permits from the Socrata API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_PATH),
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Fetch at most this many records (for testing).",
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
            "Register a free app token at https://data.cityofchicago.org/profile/app_tokens"
        )

    records = fetch_all_permits(app_token, args.days_back, args.dry_run)

    # Apply field filter to keep raw file lean.
    filtered = [filter_fields(r) for r in records]

    print(f"\nTotal records fetched: {len(filtered)}")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        print(f"Sample record:\n{json.dumps(filtered[0] if filtered else {}, indent=2)}")
        return

    write_staging_file(filtered, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
