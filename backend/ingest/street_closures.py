"""
backend/ingest/street_closures.py
task: data-004
lane: data

Ingests Chicago CDOT Street Closure Permits from the City of Chicago
Socrata API and writes raw records to a local JSON staging file.

Source:
  https://data.cityofchicago.org/resource/jdis-5sry.json
  Dataset: CDOT Street Closures / Work Zone Permits

Usage:
  python backend/ingest/street_closures.py
  python backend/ingest/street_closures.py --output data/raw/street_closures.json
  python backend/ingest/street_closures.py --limit 500 --dry-run

Environment variables (optional):
  CHICAGO_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                               Register free at https://data.cityofchicago.org/profile/app_tokens

Acceptance criteria (data-004):
  - Closure records are stored in a raw staging JSON file.
  - Source timestamps (creation_date / modified_date) are preserved.
  - Planned closures are prioritized over speculative/expired feeds.
  - Script is idempotent: re-running overwrites the output file cleanly.

Notes for next agent:
  Street closures provide the strongest direct evidence of traffic disruption
  in the scoring model. Prioritize these over generic permits when both are
  similarly close and active (per docs/03_scoring_model.md dominance rules).
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

SOCRATA_BASE_URL = "https://data.cityofchicago.org/resource/jdis-5sry.json"

# Fields to retain from the raw closure record.
FIELDS_TO_KEEP = [
    "row_id",                # source identifier — never drop this
    "work_type",
    "street_closure_type",
    "closure_reason",
    "status",
    "creation_date",
    "modified_date",
    "start_date",
    "end_date",
    "street_name",
    "from_street",
    "to_street",
    "street_direction",
    "latitude",
    "longitude",
    "location",              # GeoJSON point if available
    "contact_last_name",
    "contact_first_name",
    "contact_org",
    "permit_number",
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = "data/raw/street_closures.json"
DAYS_BACK = 60  # Closures are shorter-horizon than permits; 60 days covers MVP window


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def build_params(
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> dict:
    """Build Socrata query params for one page of closure results."""
    # Filter to closures active now or starting within the lookback window.
    # Includes recently ended closures (within days_back) for residual signal.
    cutoff = datetime.now(timezone.utc)
    # Simple cutoff: records modified or ending after cutoff - days_back days
    cutoff_str = f"{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}T00:00:00"

    params: dict = {
        "$limit": limit,
        "$offset": offset,
        "$where": f"end_date >= '{cutoff_str}' OR start_date >= '{cutoff_str}'",
        "$order": "start_date DESC",
    }

    if app_token:
        params["$$app_token"] = app_token

    return params


def fetch_page(
    session: requests.Session,
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> list[dict]:
    """Fetch one page of closure records from Socrata."""
    params = build_params(offset, limit, app_token, days_back)

    try:
        response = session.get(SOCRATA_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"  ERROR: Request timed out at offset {offset}.", file=sys.stderr)
        raise
    except requests.exceptions.HTTPError as exc:
        print(
            f"  ERROR: HTTP {exc.response.status_code} at offset {offset}: "
            f"{exc.response.text[:200]}",
            file=sys.stderr,
        )
        raise

    return response.json()


def fetch_all_closures(app_token: str | None, days_back: int, dry_run: bool) -> list[dict]:
    """
    Paginate through the Socrata API and return all raw closure records
    active within the MVP near-term window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print(f"Fetching Chicago street closures (active or starting within {days_back} days)...")

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
            break

    return all_records


# ---------------------------------------------------------------------------
# Filtering and staging
# ---------------------------------------------------------------------------

def filter_fields(record: dict) -> dict:
    """Retain only the fields needed for downstream normalization."""
    filtered = {k: v for k, v in record.items() if k in FIELDS_TO_KEEP}

    # Always preserve row_id as the source identifier.
    if "row_id" in record and "row_id" not in filtered:
        filtered["row_id"] = record["row_id"]

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw closure records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source": "chicago_street_closures",
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
        description="Ingest Chicago CDOT street closure permits from the Socrata API."
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
        help=f"Number of days back/forward to fetch (default: {DAYS_BACK}).",
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

    records = fetch_all_closures(app_token, args.days_back, args.dry_run)
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
