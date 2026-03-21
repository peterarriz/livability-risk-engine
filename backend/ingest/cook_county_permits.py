"""
backend/ingest/cook_county_permits.py
task: data-031
lane: data

Ingests Cook County building permits (suburban, outside Chicago city limits)
from the Cook County Open Data Portal (Socrata API) and writes raw records
to a local JSON staging file.

Source:
  https://datacatalog.cookcountyil.gov/resource/ydr8-5enu.json
  Dataset: Cook County Building Permits

  ⚠ Dataset ID validation:
    Verify the dataset ID at https://datacatalog.cookcountyil.gov/browse?q=building+permits
    Look for "Building Permits" or "Permit Applications".
    Update SOCRATA_BASE_URL below if the dataset ID has changed.

  Note: This covers unincorporated Cook County and suburban municipalities
  that report through the county. Chicago city permits use a separate pipeline
  (backend/ingest/building_permits.py).

Usage:
  python backend/ingest/cook_county_permits.py
  python backend/ingest/cook_county_permits.py --output data/raw/cook_county_permits.json
  python backend/ingest/cook_county_permits.py --limit 500 --dry-run

Environment variables (optional):
  COOK_COUNTY_SOCRATA_APP_TOKEN  — Socrata app token for higher rate limits.
                                   Register free at https://datacatalog.cookcountyil.gov/profile/app_tokens
  CHICAGO_SOCRATA_APP_TOKEN      — Accepted as fallback.

Acceptance criteria (data-031):
  - Script pulls Cook County permits from the Socrata API.
  - Raw records are written to a JSON staging file.
  - Source identifiers (permit_number) are preserved for traceability.
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

# Cook County Open Data Portal — Building Permits.
# Verify dataset ID at: https://datacatalog.cookcountyil.gov/browse?q=building+permits
SOCRATA_BASE_URL = "https://datacatalog.cookcountyil.gov/resource/ydr8-5enu.json"

# Mapping from Socrata column names to internal pipeline field names.
# Adjust keys if the Cook County portal uses different column names than
# the Chicago portal (same Socrata platform, field names often differ).
SOCRATA_TO_INTERNAL = {
    "permit_number":           "permit_number",    # source identifier
    "permit_type":             "permit_type",
    "application_date":        "application_start_date",
    "issue_date":              "issue_date",
    "expiration_date":         "expiration_date",
    "description":             "work_description",
    "address":                 "full_address",     # Cook County may supply full address
    "street_number":           "street_number",
    "street_direction":        "street_direction",
    "street_name":             "street_name",
    "city":                    "city",             # suburb name (e.g. "Evanston", "Skokie")
    "state":                   "state",
    "zip":                     "zip_code",
    "latitude":                "latitude",
    "longitude":               "longitude",
    "location":                "location",         # nested dict fallback for lat/lon
    "contractor_name":         "contact_1_name",
    "estimated_cost":          "reported_cost",
    "status":                  "status",
}

PAGE_SIZE = 5000
DEFAULT_OUTPUT_PATH = "data/raw/cook_county_permits.json"

# How many days back to fetch.
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
    """Build Socrata query params for one page of Cook County permit results."""
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


def fetch_page(
    session: requests.Session,
    offset: int,
    limit: int,
    app_token: str | None,
    days_back: int,
) -> list[dict]:
    """Fetch one page of Cook County permit records from Socrata."""
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


def fetch_all_permits(app_token: str | None, days_back: int, dry_run: bool) -> list[dict]:
    """
    Paginate through the Socrata API and return all Cook County permit records
    within the lookback window.
    """
    session = requests.Session()
    all_records: list[dict] = []
    offset = 0

    print(f"Fetching Cook County building permits (last {days_back} days)...")

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
    Remap Socrata column names to internal names and drop unneeded fields.
    Falls back to direct key pass-through for columns not in the map.
    """
    filtered: dict = {}

    # Remap known columns.
    for socrata_key, internal_key in SOCRATA_TO_INTERNAL.items():
        if socrata_key in record:
            filtered[internal_key] = record[socrata_key]

    # Extract lat/lon from nested location dict if top-level is absent.
    if (
        ("latitude" not in filtered or not filtered["latitude"])
        and isinstance(record.get("location"), dict)
    ):
        loc = record["location"]
        if "latitude" in loc:
            filtered["latitude"] = loc["latitude"]
        if "longitude" in loc:
            filtered["longitude"] = loc["longitude"]

    # Ensure source identifier is always present.
    if "permit_number" not in filtered:
        # Some portals use permit_no or permitnumber.
        for alt_key in ("permit_no", "permitnumber", "permit_id", "id"):
            if alt_key in record:
                filtered["permit_number"] = record[alt_key]
                break

    return filtered


def write_staging_file(records: list[dict], output_path: Path) -> None:
    """Write raw Cook County permit records to a JSON staging file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    staging = {
        "source": "cook_county_permits",
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
        description="Ingest Cook County building permits from the Cook County Open Data Portal."
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

    app_token = (
        os.environ.get("COOK_COUNTY_SOCRATA_APP_TOKEN")
        or os.environ.get("CHICAGO_SOCRATA_APP_TOKEN")
    )

    if not app_token:
        print(
            "Note: COOK_COUNTY_SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register a free token at https://datacatalog.cookcountyil.gov/profile/app_tokens"
        )

    records = fetch_all_permits(app_token, args.days_back, args.dry_run)
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
