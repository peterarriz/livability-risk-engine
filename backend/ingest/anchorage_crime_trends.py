"""
backend/ingest/anchorage_crime_trends.py
task: data-058
lane: data

Ingests Anchorage Police Department (APD) crime data and calculates
12-month crime trends by offense type.

Source:
  FBI Crime Data Explorer (CDE) API
  https://api.usa.gov/crime/fbi/cde/summarized/agency/{ORI}/{offense}
  ORI: AK0010100 (Anchorage Police Department)

  Note: The Municipality of Anchorage Socrata portal (data.muni.org) was
  decommissioned; all requests 302-redirect to the muni.org homepage.
  Anchorage crime mapping uses LexisNexis Community Crime Map which has
  no public API. The FBI CDE API is the only freely available, structured
  data source for APD crime statistics.

  Offense types queried:
    robbery, burglary, larceny, motor-vehicle-theft,
    aggravated-assault, homicide, rape, arson

  The API returns monthly offense counts ("actuals") per agency.
  We sum 12-month windows and compare current vs. prior year.

Output:
  data/raw/anchorage_crime_trends.json

Usage:
  python backend/ingest/anchorage_crime_trends.py
  python backend/ingest/anchorage_crime_trends.py --dry-run
  python backend/ingest/anchorage_crime_trends.py --discover

Environment variables (optional):
  FBI_API_KEY  — api.data.gov key (falls back to DEMO_KEY)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FBI_CDE_BASE = "https://api.usa.gov/crime/fbi/cde"
AGENCY_ORI = "AK0010100"  # Anchorage Police Department

# UCR/SRS offense types available via the summarized endpoint
OFFENSE_TYPES = [
    "aggravated-assault",
    "arson",
    "burglary",
    "homicide",
    "larceny",
    "motor-vehicle-theft",
    "rape",
    "robbery",
]

# Human-readable labels
OFFENSE_LABELS = {
    "aggravated-assault": "Aggravated Assault",
    "arson": "Arson",
    "burglary": "Burglary",
    "homicide": "Homicide",
    "larceny": "Larceny/Theft",
    "motor-vehicle-theft": "Motor Vehicle Theft",
    "rape": "Rape",
    "robbery": "Robbery",
}

DEFAULT_OUTPUT_PATH = Path("data/raw/anchorage_crime_trends.json")

ANCHORAGE_LAT = 61.2181
ANCHORAGE_LON = -149.9003

STABLE_THRESHOLD_PCT = 5.0

# Delay between API calls to avoid DEMO_KEY rate limits (60/hr)
API_DELAY_SECS = 2.0
# Max retries on 429 rate-limit errors
MAX_RETRIES = 3
RETRY_BACKOFF_SECS = 10


def _get_api_key() -> str:
    return os.environ.get("FBI_API_KEY", "DEMO_KEY")


def _month_key(year: int, month: int) -> str:
    """Return MM-YYYY string used by the FBI CDE API."""
    return f"{month:02d}-{year}"


def fetch_offense_monthly(
    offense: str,
    from_year: int,
    to_year: int,
    api_key: str,
) -> dict[str, int | None]:
    """Fetch monthly actuals for a single offense type from FBI CDE.

    Returns dict like {"01-2023": 27, "02-2023": 29, ...} with actual
    offense counts per month for the Anchorage PD.
    """
    url = f"{FBI_CDE_BASE}/summarized/agency/{AGENCY_ORI}/{offense}"
    params = {
        "from": f"01-{from_year}",
        "to": f"12-{to_year}",
        "API_KEY": api_key,
    }
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 429:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECS * (attempt + 1)
                print(f"    Rate limited, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Rate limited after {MAX_RETRIES} retries for {offense}")
        resp.raise_for_status()
        break

    data = resp.json()

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"FBI CDE error for {offense}: {data['error']}")

    # Navigate to actuals for this agency
    actuals_key = "Anchorage Police Department Offenses"
    try:
        actuals = data["offenses"]["actuals"][actuals_key]
    except (KeyError, TypeError):
        # Try to find the key dynamically
        try:
            all_actuals = data["offenses"]["actuals"]
            agency_keys = [k for k in all_actuals if "Anchorage" in k and "Offense" in k]
            if agency_keys:
                actuals = all_actuals[agency_keys[0]]
            else:
                print(f"  WARNING: no Anchorage actuals found for {offense}", file=sys.stderr)
                return {}
        except (KeyError, TypeError):
            print(f"  WARNING: unexpected response structure for {offense}", file=sys.stderr)
            return {}

    return actuals


def _sum_months(
    monthly: dict[str, int | None],
    year_start: int,
    month_start: int,
    year_end: int,
    month_end: int,
) -> int:
    """Sum monthly counts for a date range [start, end] inclusive."""
    total = 0
    y, m = year_start, month_start
    while (y, m) <= (year_end, month_end):
        key = _month_key(y, m)
        val = monthly.get(key)
        if val is not None:
            total += int(val)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return total


def fetch_crime_counts_by_offense(
    api_key: str,
    current_year: int,
    prior_year: int,
) -> tuple[dict[str, int], dict[str, int]]:
    """Fetch crime counts for current and prior 12-month periods by offense.

    Returns (current_counts, prior_counts) where keys are offense slugs.
    Uses calendar years for simplicity (Jan-Dec).
    """
    current_counts: dict[str, int] = {}
    prior_counts: dict[str, int] = {}

    for i, offense in enumerate(OFFENSE_TYPES):
        if i > 0:
            time.sleep(API_DELAY_SECS)

        print(f"  Fetching {offense}...")
        try:
            monthly = fetch_offense_monthly(offense, prior_year, current_year, api_key)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {offense} — {exc}", file=sys.stderr)
            continue

        current_counts[offense] = _sum_months(monthly, current_year, 1, current_year, 12)
        prior_counts[offense] = _sum_months(monthly, prior_year, 1, prior_year, 12)

    return current_counts, prior_counts


def _classify_trend(current: int, prior: int) -> tuple[str, float]:
    if prior == 0:
        if current > 0:
            return "INCREASING", 100.0
        return "STABLE", 0.0
    pct = (current - prior) / prior * 100.0
    if pct >= STABLE_THRESHOLD_PCT:
        return "INCREASING", round(pct, 1)
    if pct <= -STABLE_THRESHOLD_PCT:
        return "DECREASING", round(pct, 1)
    return "STABLE", round(pct, 1)


def build_trend_records(
    current_counts: dict[str, int],
    prior_counts: dict[str, int],
) -> list[dict]:
    all_offenses = set(current_counts.keys()) | set(prior_counts.keys())
    records = []
    for offense in sorted(all_offenses):
        current = current_counts.get(offense, 0)
        prior = prior_counts.get(offense, 0)
        trend, trend_pct = _classify_trend(current, prior)
        slug = offense.replace("-", "_")
        label = OFFENSE_LABELS.get(offense, offense.replace("-", " ").title())
        records.append({
            "region_type": "offense_type",
            "region_id": f"anchorage_{slug}",
            "district_id": offense,
            "district_name": f"Anchorage — {label}",
            "crime_12mo": current,
            "crime_prior_12mo": prior,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": ANCHORAGE_LAT,
            "longitude": ANCHORAGE_LON,
        })
    return records


def discover_datasets() -> None:
    """Show available FBI CDE data for Anchorage PD."""
    api_key = _get_api_key()
    print(f"FBI CDE API — Agency: {AGENCY_ORI}")
    print(f"API key: {'(custom)' if api_key != 'DEMO_KEY' else 'DEMO_KEY (rate-limited)'}")

    # Fetch agency info
    url = f"{FBI_CDE_BASE}/agency/byStateAbbr/AK"
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(url, params={"API_KEY": api_key}, timeout=30)
        if resp.status_code == 429:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECS * (attempt + 1)
                print(f"  Rate limited, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            print("ERROR: rate limited; set FBI_API_KEY env var or wait and retry.", file=sys.stderr)
            return
        resp.raise_for_status()
        break
    data = resp.json()

    print("\nAnchorage-area agencies:")
    for county, agencies in data.items():
        for ag in agencies:
            if "anchorage" in ag.get("agency_name", "").lower():
                print(f"  ORI: {ag['ori']}")
                print(f"  Name: {ag['agency_name']}")
                print(f"  Type: {ag['agency_type_name']}")
                print(f"  NIBRS: {ag['is_nibrs']}")
                print(f"  Lat/Lon: {ag.get('latitude')}, {ag.get('longitude')}")
                print()

    print(f"Offense types available: {', '.join(OFFENSE_TYPES)}")

    # Test one offense
    print("\nSample query (robbery, 2024):")
    time.sleep(API_DELAY_SECS)
    try:
        monthly = fetch_offense_monthly("robbery", 2024, 2024, api_key)
        total = sum(v for v in monthly.values() if v is not None)
        print(f"  Monthly data points: {len(monthly)}")
        print(f"  Total robbery offenses in 2024: {total}")
        non_null = {k: v for k, v in sorted(monthly.items()) if v is not None}
        for k, v in list(non_null.items())[:6]:
            print(f"    {k}: {v}")
        if len(non_null) > 6:
            print(f"    ... ({len(non_null) - 6} more months)")
    except Exception as exc:
        print(f"  ERROR: {exc}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_url = f"{FBI_CDE_BASE}/summarized/agency/{AGENCY_ORI}/{{offense}}"
    staging = {
        "source": "anchorage_crime_trends",
        "source_url": source_url,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Anchorage APD crime trends by offense type from FBI CDE API."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="Show available FBI CDE data for Anchorage PD.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = _get_api_key()

    if args.discover:
        discover_datasets()
        return

    now = datetime.now(timezone.utc)
    # Use most recent complete calendar year as "current" and year before as "prior"
    # FBI CDE data lags ~6 months, so current calendar year may be incomplete.
    # If we're in the first half of the year, use (year-2, year-1).
    # Otherwise use (year-1, year).
    if now.month <= 6:
        current_year = now.year - 1
    else:
        current_year = now.year
    prior_year = current_year - 1

    print(f"FBI CDE API — Anchorage PD (ORI: {AGENCY_ORI})")
    print(f"API key: {'(custom)' if api_key != 'DEMO_KEY' else 'DEMO_KEY (rate-limited)'}")
    print(f"Current period: {current_year} (Jan-Dec)")
    print(f"Prior period:   {prior_year} (Jan-Dec)")
    print()

    print("Fetching offense data from FBI CDE...")
    try:
        current_counts, prior_counts = fetch_crime_counts_by_offense(
            api_key, current_year, prior_year,
        )
    except Exception as exc:
        print(f"ERROR: failed to fetch crime data — {exc}", file=sys.stderr)
        sys.exit(1)

    if not current_counts and not prior_counts:
        print("ERROR: no data returned for any offense type.", file=sys.stderr)
        sys.exit(1)

    print(f"\n  {len(current_counts)} offense types with current data.")
    print(f"  {len(prior_counts)} offense types with prior data.")

    records = build_trend_records(current_counts, prior_counts)
    print(f"\nBuilt {len(records)} offense trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} offense types")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
