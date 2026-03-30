"""
backend/ingest/boston_crime_trends.py
task: data-045
lane: data

Ingests Boston Police Department crime data via CSV download and
calculates 12-month crime trends by district.

Source:
  Boston CKAN portal — CSV download only (datastore_search not supported).
  "2023 to Present": https://data.boston.gov/.../tmpwz5bwsax.csv
  "2022": https://data.boston.gov/.../tmpdfeo3qy2.csv

  Key fields: OCCURRED_ON_DATE, DISTRICT, Lat, Long

Output:
  data/raw/boston_crime_trends.json

Usage:
  python backend/ingest/boston_crime_trends.py
  python backend/ingest/boston_crime_trends.py --dry-run
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

CSV_2023_PRESENT_URL = (
    "https://data.boston.gov/dataset/6220d948-eae2-4e4b-8723-2dc8e67722a3"
    "/resource/b973d8cb-eeb2-4e7e-99da-c92938efc9c0/download/tmpwz5bwsax.csv"
)
CSV_2022_URL = (
    "https://data.boston.gov/dataset/6220d948-eae2-4e4b-8723-2dc8e67722a3"
    "/resource/313e56df-6d77-49d2-9c49-ee411f10cf58/download/tmpdfeo3qy2.csv"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/boston_crime_trends.json")

DATE_FIELD = "OCCURRED_ON_DATE"
DISTRICT_FIELD = "DISTRICT"
LAT_FIELD = "Lat"
LON_FIELD = "Long"

BOSTON_LAT = 42.3601
BOSTON_LON = -71.0589

STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# CSV download + parse
# ---------------------------------------------------------------------------

def _download_csv(url: str, label: str) -> str:
    print(f"  Downloading {label}...", end=" ", flush=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    content = resp.content.decode("utf-8", errors="replace")
    lines = content.strip().split("\n")
    print(f"{len(lines) - 1} rows.")
    return content


def _count_crimes_by_district(
    csv_text: str,
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """Parse CSV, filter by date range, count incidents per district.
    Also collects average lat/lon per district from the data."""
    reader = csv.DictReader(io.StringIO(csv_text))
    counts: dict[str, int] = {}
    lat_sums: dict[str, float] = {}
    lon_sums: dict[str, float] = {}
    coord_counts: dict[str, int] = {}

    for row in reader:
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

        counts[district] = counts.get(district, 0) + 1

        try:
            lat = float(row.get(LAT_FIELD) or 0)
            lon = float(row.get(LON_FIELD) or 0)
            if lat > 40 and lon < -69:
                lat_sums[district] = lat_sums.get(district, 0.0) + lat
                lon_sums[district] = lon_sums.get(district, 0.0) + lon
                coord_counts[district] = coord_counts.get(district, 0) + 1
        except (ValueError, TypeError):
            pass

    centroids: dict[str, tuple[float, float]] = {}
    for d in coord_counts:
        if coord_counts[d] > 0:
            centroids[d] = (
                round(lat_sums[d] / coord_counts[d], 6),
                round(lon_sums[d] / coord_counts[d], 6),
            )

    return counts, centroids


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
    centroids: dict[str, tuple[float, float]],
) -> list[dict]:
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        centroid = centroids.get(district)
        lat = centroid[0] if centroid else BOSTON_LAT
        lon = centroid[1] if centroid else BOSTON_LON
        records.append({
            "region_type": "district",
            "region_id": f"boston_district_{district.lower()}",
            "district_id": district,
            "district_name": f"Boston District {district}",
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
        "source": "boston_crime_trends",
        "source_url": CSV_2023_PRESENT_URL,
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
        description="Ingest Boston BPD crime trends by district from CKAN CSV download."
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

    print("Boston crime trends ingest — CSV download mode")

    try:
        csv_2023 = _download_csv(CSV_2023_PRESENT_URL, "2023-present CSV")
    except Exception as exc:
        print(f"ERROR: 2023+ download failed — {exc}", file=sys.stderr)
        sys.exit(1)

    csv_2022 = None
    try:
        csv_2022 = _download_csv(CSV_2022_URL, "2022 CSV")
    except Exception as exc:
        print(f"WARN: 2022 download failed — {exc}. Prior year may be incomplete.", file=sys.stderr)

    combined = csv_2023
    if csv_2022:
        lines_2023 = csv_2023.strip().split("\n")
        combined = csv_2022.strip() + "\n" + "\n".join(lines_2023[1:])

    print(f"\nCounting current 12-month crimes ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    current_data, current_centroids = _count_crimes_by_district(combined, current_start, now)
    print(f"  {len(current_data)} districts, {sum(current_data.values()):,} total crimes.")

    print(f"\nCounting prior 12-month crimes ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data, prior_centroids = _count_crimes_by_district(combined, prior_start, prior_end)
    print(f"  {len(prior_data)} districts, {sum(prior_data.values()):,} total crimes.")

    centroids = {**prior_centroids, **current_centroids}

    records = build_trend_records(current_data, prior_data, centroids)
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
