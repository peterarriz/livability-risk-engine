"""
backend/ingest/milwaukee_crime_trends.py
task: data-045
lane: data

Ingests Milwaukee Police Department crime data via CSV download and
calculates 12-month crime trends by police district.

Source:
  Milwaukee CKAN portal — CSV download only (datastore_search not supported).
  YTD CSV: https://data.milwaukee.gov/.../wibr.csv
  Archive CSV: https://data.milwaukee.gov/.../wibrarchive.csv

  Key fields: ReportedDateTime, POLICE (district), boolean crime columns.
  Coordinates: RoughX/RoughY are WI State Plane (not lat/lon) — use
  hardcoded district centroids instead.

  WARNING: Dataset is a rolling ~3 month YTD window. Archive has 73MB+
  of historical data. Prior-year comparison requires the archive file.

Output:
  data/raw/milwaukee_crime_trends.json

Usage:
  python backend/ingest/milwaukee_crime_trends.py
  python backend/ingest/milwaukee_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

YTD_CSV_URL = (
    "https://data.milwaukee.gov/dataset/e5feaad3-ee73-418c-b65d-ef810c199390"
    "/resource/87843297-a6fa-46d4-ba5d-cb342fb2d3bb/download/wibr.csv"
)
ARCHIVE_CSV_URL = (
    "https://data.milwaukee.gov/dataset/5a537f5c-10d7-40a2-9b93-3527a4c89fbd"
    "/resource/395db729-a30a-4e53-ab66-faeb5e1899c8/download/wibrarchive.csv"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/milwaukee_crime_trends.json")

DATE_FIELD = "ReportedDateTime"
DISTRICT_FIELD = "POLICE"
CRIME_COLUMNS = [
    "Arson", "AssaultOffense", "Burglary", "CriminalDamage",
    "Homicide", "LockedVehicle", "Robbery", "SexOffense",
    "Theft", "VehicleTheft",
]

# Hardcoded district centroids (WGS84) — avoids converting WI State Plane coords
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "1": (43.038, -87.912),  # District 1 — Downtown/Near South
    "2": (42.987, -87.921),  # District 2 — South Side
    "3": (43.060, -87.960),  # District 3 — Near West
    "4": (43.110, -87.940),  # District 4 — North Side
    "5": (43.065, -87.920),  # District 5 — Central/Near North
    "6": (42.975, -87.880),  # District 6 — Bay View/South Shore
    "7": (43.090, -87.950),  # District 7 — Northwest
}

MILWAUKEE_LAT = 43.0389
MILWAUKEE_LON = -87.9065

STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# CSV download + parse
# ---------------------------------------------------------------------------

def _download_csv(url: str, label: str) -> str:
    print(f"  Downloading {label}...", end=" ", flush=True)
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    content = resp.content.decode("utf-8", errors="replace")
    # Normalize line endings (Milwaukee uses \r between records)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.strip().split("\n")
    print(f"{len(lines) - 1} rows.")
    return content


def _count_crimes_by_district(
    csv_text: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Parse CSV, filter by date range, sum crime columns per district."""
    reader = csv.DictReader(io.StringIO(csv_text))
    counts: dict[str, int] = {}

    for row in reader:
        # Parse date
        date_str = (row.get(DATE_FIELD) or "").strip()
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        if dt < start_date or dt >= end_date:
            continue

        district = (row.get(DISTRICT_FIELD) or "").strip()
        if not district:
            continue

        # Sum boolean crime columns
        crime_count = 0
        for col in CRIME_COLUMNS:
            try:
                crime_count += int(row.get(col, 0) or 0)
            except (ValueError, TypeError):
                pass

        if crime_count > 0:
            counts[district] = counts.get(district, 0) + crime_count

    return counts


# ---------------------------------------------------------------------------
# Trend logic
# ---------------------------------------------------------------------------

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
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        centroid = DISTRICT_CENTROIDS.get(district)
        lat = centroid[0] if centroid else MILWAUKEE_LAT
        lon = centroid[1] if centroid else MILWAUKEE_LON
        records.append({
            "region_type": "district",
            "region_id": f"milwaukee_district_{district}",
            "district_id": district,
            "district_name": f"Milwaukee District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat,
            "longitude": lon,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "milwaukee_crime_trends",
        "source_url": YTD_CSV_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Milwaukee crime trends by district from CKAN CSV download."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now()
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print("Milwaukee crime trends ingest — CSV download mode")

    # Download YTD CSV (current year data)
    try:
        ytd_csv = _download_csv(YTD_CSV_URL, "YTD CSV")
    except Exception as exc:
        print(f"ERROR: YTD download failed — {exc}", file=sys.stderr)
        sys.exit(1)

    # Download archive CSV (historical data for prior year comparison)
    archive_csv = None
    try:
        archive_csv = _download_csv(ARCHIVE_CSV_URL, "Archive CSV")
    except Exception as exc:
        print(f"WARN: Archive download failed — {exc}. Prior year will be empty.", file=sys.stderr)

    # Combine both CSVs for parsing (archive first, then YTD)
    combined = ""
    if archive_csv:
        # Strip header from YTD before appending
        ytd_lines = ytd_csv.strip().split("\n")
        combined = archive_csv.strip() + "\n" + "\n".join(ytd_lines[1:])
    else:
        combined = ytd_csv

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data = _count_crimes_by_district(combined, current_start, now)
    print(f"  {len(current_data)} districts, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data = _count_crimes_by_district(combined, prior_start, prior_end)
    print(f"  {len(prior_data)} districts, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    for r in records:
        print(f"  District {r['district_id']}: {r['crime_12mo']:,} current, {r['crime_prior_12mo']:,} prior → {r['crime_trend']} ({r['crime_trend_pct']:+.1f}%)")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
