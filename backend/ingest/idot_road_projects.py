"""
backend/ingest/idot_road_projects.py
task: data-031
lane: data

Ingests IDOT (Illinois Department of Transportation) active road construction
and work zone projects from the Illinois Open Data Portal (Socrata API) and
writes raw records to a local JSON staging file.

Source:
  https://data.illinois.gov/resource/hhkm-y6y2.json
  Dataset: IDOT Highway Improvement Projects (Active)

  ⚠ Dataset ID validation:
    Verify the dataset ID at https://data.illinois.gov/browse?q=IDOT+construction
    Look for "IDOT Construction Year Highway Projects" or "IDOT Work Zones".
    Update SOCRATA_BASE_URL below if the dataset ID has changed.

Usage:
  python backend/ingest/idot_road_projects.py
  python backend/ingest/idot_road_projects.py --output data/raw/idot_road_projects.json
  python backend/ingest/idot_road_projects.py --limit 500 --dry-run

Environment variables (optional):
  ILLINOIS_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                                Register free at https://data.illinois.gov/profile/app_tokens
  CHICAGO_SOCRATA_APP_TOKEN   — Accepted as fallback if IL-specific token not set.

Acceptance criteria (data-031):
  - Script pulls IDOT road projects from the Socrata API.
  - Raw records are written to a JSON staging file.
  - Source identifiers (project_number) are preserved for traceability.
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

# IDOT Active Construction Projects on Illinois Open Data Portal.
# Dataset: "IDOT Construction Year Highway Projects"
# Verify at: https://data.illinois.gov/browse?q=IDOT+highway+projects
SOCRATA_BASE_URL = "https://data.illinois.gov/resource/hhkm-y6y2.json"

# Fields to retain from the raw IDOT project record.
FIELDS_TO_KEEP = [
    "project_number",        # source identifier — never drop this
    "project_description",   # human-readable description of the work
    "work_type",             # type of road work (paving, bridge, etc.)
    "county",                # county name within Illinois
    "district",              # IDOT district (1–9)
    "route",                 # IL route / US route / Interstate
    "start_date",            # planned construction start
    "end_date",              # planned construction end
    "contract_date",         # date contract awarded
    "contractor",            # prime contractor
    "contract_amount",       # total contract value
    "latitude",              # project centroid lat (if available)
    "longitude",             # project centroid lon (if available)
    "location",              # location dict (fallback for lat/lon)
    "status",                # active | completed | planned
]

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = "data/raw/idot_road_projects.json"

# Fetch projects active or starting within this many days.
DAYS_BACK = 180  # IDOT projects span longer horizons than city permits


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def build_params(
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> dict:
    """Build Socrata query params for one page of IDOT project results."""
    cutoff = datetime.now(timezone.utc)
    # Use a simple date filter — keep projects active or starting in window.
    cutoff_str = f"{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}T00:00:00"

    params: dict = {
        "$limit": limit,
        "$offset": offset,
        # Include projects that end in the future or started recently.
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
    """Fetch one page of IDOT project records from Socrata."""
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


def fetch_all_projects(app_token: str | None, days_back: int, dry_run: bool) -> list[dict]:
    """
    Paginate through the Socrata API and return all IDOT project records
    within the active window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print(f"Fetching IDOT road projects (active or starting within {days_back} days)...")

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
    """
    Retain only the fields needed for downstream normalization.
    Always preserve the source identifier regardless of FIELDS_TO_KEEP.
    """
    filtered = {k: v for k, v in record.items() if k in FIELDS_TO_KEEP}

    # Defensive: always keep project_number even if not in FIELDS_TO_KEEP.
    if "project_number" in record and "project_number" not in filtered:
        filtered["project_number"] = record["project_number"]

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw IDOT project records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source": "idot_road_projects",
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
        description="Ingest IDOT road construction projects from the Illinois Open Data Portal."
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
        help=f"Active window in days (default: {DAYS_BACK}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch one page only; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Accept either IL-specific or Chicago token (same Socrata platform).
    app_token = (
        os.environ.get("ILLINOIS_SOCRATA_APP_TOKEN")
        or os.environ.get("CHICAGO_SOCRATA_APP_TOKEN")
    )

    if not app_token:
        print(
            "Note: ILLINOIS_SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register a free token at https://data.illinois.gov/profile/app_tokens"
        )

    records = fetch_all_projects(app_token, args.days_back, args.dry_run)
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
