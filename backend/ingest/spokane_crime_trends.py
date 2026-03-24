"""
backend/ingest/spokane_crime_trends.py
task: data-058
lane: data

Ingests Spokane-area crime data from the Washington State NIBRS dataset
on data.wa.gov and calculates year-over-year crime trends by agency.

Source:
  Socrata — data.wa.gov (Washington State Open Data)
  Dataset: WA Uniform Crime Reporting – NIBRS (vvfu-ry7f)
  Sample: curl "https://data.wa.gov/resource/vvfu-ry7f.json?location=Spokane%20Police%20Department&$limit=3&$order=indexyear%20DESC"

  Key fields:
    indexyear  — year of report
    location   — agency name (e.g. "Spokane Police Department")
    county     — county name (SPOKANE)
    total      — total offenses
    prsntotal  — person offenses
    prprtytotal — property offenses
    sctytotal  — society offenses
    murder, assault, burglary, theft, robbery, etc. — individual categories

  Note: Spokane does not publish incident-level crime data via Socrata.
  The city's own portal (my.spokanecity.org) uses a proprietary dashboard
  with no public API. This script uses the state-level NIBRS data instead,
  which provides annual totals per law-enforcement agency.

Output:
  data/raw/spokane_crime_trends.json

Usage:
  python backend/ingest/spokane_crime_trends.py
  python backend/ingest/spokane_crime_trends.py --dry-run
  python backend/ingest/spokane_crime_trends.py --discover

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
"""

from __future__ import annotations

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

SOCRATA_DOMAIN = "data.wa.gov"
DATASET_ID = "vvfu-ry7f"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/spokane_crime_trends.json")

# Agencies to include — covers the Spokane metro area
SPOKANE_AGENCIES = [
    "Spokane Police Department",
    "Spokane County Sheriffs Office",
    "Spokane Valley Police Department",
]

# Approximate centroids for each agency's jurisdiction
AGENCY_COORDS: dict[str, tuple[float, float]] = {
    "Spokane Police Department":       (47.6588, -117.4260),
    "Spokane County Sheriffs Office":   (47.6200, -117.3600),
    "Spokane Valley Police Department": (47.6733, -117.2394),
}

SPOKANE_LAT = 47.6587
SPOKANE_LON = -117.4260

STABLE_THRESHOLD_PCT = 5.0


def fetch_agency_year(
    app_token: str | None,
    agency: str,
    year: int,
) -> dict | None:
    """Fetch a single agency-year record from the WA NIBRS dataset."""
    params: dict = {
        "$where": f"location='{agency}' AND indexyear='{year}'",
        "$limit": 1,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"Socrata query error: {rows}")

    if not rows:
        return None
    return rows[0]


def fetch_available_years(
    app_token: str | None,
    agency: str,
) -> list[int]:
    """Return sorted list of years available for a given agency."""
    params: dict = {
        "$select": "indexyear",
        "$where": f"location='{agency}'",
        "$order": "indexyear DESC",
        "$limit": 50,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"Socrata query error: {rows}")

    years = []
    for row in rows:
        try:
            years.append(int(row["indexyear"]))
        except (KeyError, ValueError):
            continue
    return sorted(years, reverse=True)


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


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
    current_rows: dict[str, dict | None],
    prior_rows: dict[str, dict | None],
    current_year: int,
    prior_year: int,
) -> list[dict]:
    """Build trend records comparing two years of data per agency."""
    records = []
    for agency in SPOKANE_AGENCIES:
        curr = current_rows.get(agency)
        prev = prior_rows.get(agency)

        current_total = _safe_int((curr or {}).get("total", 0))
        prior_total = _safe_int((prev or {}).get("total", 0))
        trend, trend_pct = _classify_trend(current_total, prior_total)

        lat, lon = AGENCY_COORDS.get(agency, (SPOKANE_LAT, SPOKANE_LON))

        slug = agency.lower().replace(" ", "_").replace("'", "")
        region_id = f"spokane_{slug}"

        # Build crime category breakdown from current year
        categories = {}
        if curr:
            for field in [
                "murder", "manslaughter", "forcible_sex", "assault",
                "robbery", "burglary", "theft", "arson",
                "destruction_of_property", "drug_violations",
                "weapon_law_violation",
            ]:
                categories[field] = _safe_int(curr.get(field, 0))

        record = {
            "region_type": "agency",
            "region_id": region_id,
            "district_id": agency,
            "district_name": agency,
            "crime_12mo": current_total,
            "crime_prior_12mo": prior_total,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "current_year": current_year,
            "prior_year": prior_year,
            "person_crimes": _safe_int((curr or {}).get("prsntotal", 0)),
            "property_crimes": _safe_int((curr or {}).get("prprtytotal", 0)),
            "society_crimes": _safe_int((curr or {}).get("sctytotal", 0)),
            "population": _safe_int((curr or {}).get("population", 0)),
            "categories": categories,
            "latitude": lat,
            "longitude": lon,
        }
        records.append(record)

    return records


def discover_datasets() -> None:
    """Search data.wa.gov for Spokane-related crime datasets."""
    url = f"https://{SOCRATA_DOMAIN}/api/catalog/v1"
    for q in ["washington crime NIBRS", "uniform crime reporting", "spokane"]:
        resp = requests.get(url, params={"q": q, "limit": 5}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"\nQuery: {q!r}")
        for r in data.get("results", []):
            meta = r.get("resource", {})
            print(f"  {meta.get('id')} — {meta.get('name')}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "spokane_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Spokane crime trends from WA State NIBRS data on data.wa.gov."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    parser.add_argument("--discover", action="store_true",
                        help="Search data.wa.gov for crime datasets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if args.discover:
        discover_datasets()
        return

    # Find the two most recent years with data for SPD
    print("Fetching available years for Spokane Police Department...")
    years = fetch_available_years(app_token, "Spokane Police Department")
    if len(years) < 2:
        print(f"ERROR: need at least 2 years of data, found {len(years)}", file=sys.stderr)
        sys.exit(1)
    current_year = years[0]
    prior_year = years[1]
    print(f"  Most recent years: {current_year} (current), {prior_year} (prior)")

    # Fetch data for each agency for both years
    print(f"\nFetching {current_year} crime data for Spokane-area agencies...")
    current_rows: dict[str, dict | None] = {}
    for agency in SPOKANE_AGENCIES:
        row = fetch_agency_year(app_token, agency, current_year)
        current_rows[agency] = row
        total = _safe_int((row or {}).get("total", 0))
        print(f"  {agency}: {total:,} total offenses")

    print(f"\nFetching {prior_year} crime data for Spokane-area agencies...")
    prior_rows: dict[str, dict | None] = {}
    for agency in SPOKANE_AGENCIES:
        row = fetch_agency_year(app_token, agency, prior_year)
        prior_rows[agency] = row
        total = _safe_int((row or {}).get("total", 0))
        print(f"  {agency}: {total:,} total offenses")

    records = build_trend_records(current_rows, prior_rows, current_year, prior_year)
    print(f"\nBuilt {len(records)} agency trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} agencies")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
