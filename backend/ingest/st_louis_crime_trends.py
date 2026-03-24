"""
backend/ingest/st_louis_crime_trends.py
task: data-058
lane: data

Ingests St. Louis Metropolitan Police Department (SLMPD) crime data and
calculates 12-month crime trends by neighborhood/district.

Source:
  SLMPD publishes monthly NIBRS crime CSV files on their WordPress site.
  URL pattern:
    https://slmpd.org/wp-content/uploads/{upload_year}/{upload_month:02d}/{MonthName}{data_year}.csv

  The upload directory is the month *after* the data month.
  E.g. January 2025 data lives at:
    https://slmpd.org/wp-content/uploads/2025/02/January2025.csv

  Landing page:
    https://slmpd.org/stats/slmpd-downloadable-crime-files/

  Key CSV fields (NIBRS format):
    IncidentDate   — date of incident ("M/D/YYYY H:M:S AM/PM")
    Neighborhood   — neighborhood name
    District       — police district number
    Latitude       — incident latitude
    Longitude      — incident longitude

Output:
  data/raw/st_louis_crime_trends.json

Usage:
  python backend/ingest/st_louis_crime_trends.py
  python backend/ingest/st_louis_crime_trends.py --dry-run
  python backend/ingest/st_louis_crime_trends.py --discover
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

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Monthly NIBRS CSV URL pattern.
# upload_year/upload_month is the month AFTER the data month.
CSV_URL_TEMPLATE = (
    "https://slmpd.org/wp-content/uploads/{upload_year}/{upload_month:02d}/"
    "{month_name}{data_year}.csv"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/st_louis_crime_trends.json")

# NIBRS CSV field names (verified 2025-12 file)
DATE_FIELD = "IncidentDate"
DISTRICT_FIELD = "Neighborhood"
LAT_FIELD = "Latitude"
LON_FIELD = "Longitude"

ST_LOUIS_LAT = 38.6270
ST_LOUIS_LON = -90.1994

STABLE_THRESHOLD_PCT = 5.0

REQUEST_HEADERS = {
    "User-Agent": "livability-risk-engine/1.0 (data ingest)",
}


def _monthly_csv_url(year: int, month: int) -> str:
    """Build the download URL for a given data year/month."""
    month_name = MONTH_NAMES[month - 1]
    # Upload directory is the next month
    upload_month = month + 1
    upload_year = year
    if upload_month > 12:
        upload_month = 1
        upload_year = year + 1
    return CSV_URL_TEMPLATE.format(
        upload_year=upload_year,
        upload_month=upload_month,
        month_name=month_name,
        data_year=year,
    )


def _months_in_range(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """Return list of (year, month) tuples covering the date range."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _parse_date(raw: str) -> str | None:
    """Parse SLMPD date format and return YYYY-MM-DD or None.

    SLMPD uses: "M/D/YYYY H:M:S AM" or "M/D/YYYY".
    """
    raw = raw.strip().strip('"')
    if not raw:
        return None
    # Take just the date part (before the space/time)
    date_part = raw.split(" ")[0] if " " in raw else raw
    try:
        if "/" in date_part:
            parts = date_part.split("/")
            if len(parts) == 3:
                m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2][:4]
                return f"{y}-{m}-{d}"
    except (IndexError, ValueError):
        pass
    # Try YYYY-MM-DD or ISO-like
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    return None


def _fetch_month_csv(
    year: int,
    month: int,
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, dict]:
    """Download one monthly SLMPD CSV, filter by date range, count by neighborhood."""
    url = _monthly_csv_url(year, month)
    print(f"    Downloading {url}...", end=" ", flush=True)

    try:
        resp = requests.get(url, timeout=120, headers=REQUEST_HEADERS)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"HTTP {status} -- skipping {MONTH_NAMES[month-1]} {year}")
        return {}
    except requests.RequestException as exc:
        print(f"ERROR: {exc}")
        return {}

    start_iso = start_date.strftime("%Y-%m-%d")
    end_iso = end_date.strftime("%Y-%m-%d")

    counts: dict[str, dict] = {}
    lines_read = 0

    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            raw_date = (row.get(DATE_FIELD) or "").strip()
            dt_str = _parse_date(raw_date)
            if not dt_str:
                continue
            if dt_str < start_iso or dt_str >= end_iso:
                continue

            district = (row.get(DISTRICT_FIELD) or "").strip()
            if not district:
                continue

            try:
                lat = float(row.get(LAT_FIELD) or 0) or None
            except (TypeError, ValueError):
                lat = None
            try:
                lon = float(row.get(LON_FIELD) or 0) or None
            except (TypeError, ValueError):
                lon = None

            if district not in counts:
                counts[district] = {"count": 0, "lat_sum": 0.0, "lon_sum": 0.0, "n": 0}
            counts[district]["count"] += 1
            if lat and lon:
                counts[district]["lat_sum"] += lat
                counts[district]["lon_sum"] += lon
                counts[district]["n"] += 1

            lines_read += 1
            if dry_run and lines_read >= 5000:
                break

    except Exception as exc:
        print(f"WARN: CSV parse error for {MONTH_NAMES[month-1]} {year}: {exc}")
        return {}

    total = sum(v["count"] for v in counts.values())
    print(f"{total:,} matching crimes in {len(counts)} neighborhoods")
    return counts


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, dict]:
    combined: dict[str, dict] = {}
    for year, month in _months_in_range(start_date, end_date):
        try:
            month_counts = _fetch_month_csv(year, month, start_date, end_date, dry_run)
            for district, v in month_counts.items():
                if district not in combined:
                    combined[district] = {
                        "count": 0,
                        "lat_sum": 0.0,
                        "lon_sum": 0.0,
                        "n": 0,
                    }
                combined[district]["count"] += v["count"]
                combined[district]["lat_sum"] += v["lat_sum"]
                combined[district]["lon_sum"] += v["lon_sum"]
                combined[district]["n"] += v["n"]
        except Exception as exc:
            print(f"WARN: {MONTH_NAMES[month-1]} {year} -- {exc}")

    # Compute centroid averages
    result: dict[str, dict] = {}
    for dist, v in combined.items():
        avg_lat = (v["lat_sum"] / v["n"]) if v["n"] > 0 else None
        avg_lon = (v["lon_sum"] / v["n"]) if v["n"] > 0 else None
        result[dist] = {"count": v["count"], "lat": avg_lat, "lon": avg_lon}
    return result


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
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        curr = current_data.get(district, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(district, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr.get("lat") or prev.get("lat")
        lon = curr.get("lon") or prev.get("lon")
        slug = district.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "neighborhood",
            "region_id": f"st_louis_neighborhood_{slug}",
            "district_id": district,
            "district_name": f"St. Louis {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or ST_LOUIS_LAT,
            "longitude": lon or ST_LOUIS_LON,
        })
    return records


def discover_files() -> None:
    """Check which SLMPD monthly CSV files are available."""
    print("Discovering SLMPD monthly NIBRS CSV files...")
    now = datetime.now(timezone.utc)
    # Check from Jan 2024 through current month
    start_year = now.year - 2
    for year in range(start_year, now.year + 1):
        for month in range(1, 13):
            if (year, month) > (now.year, now.month):
                break
            url = _monthly_csv_url(year, month)
            try:
                resp = requests.head(
                    url, timeout=10, allow_redirects=True, headers=REQUEST_HEADERS
                )
                size = resp.headers.get("Content-Length", "?")
                status_mark = "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}"
                print(f"  {MONTH_NAMES[month-1]:>10} {year}: {status_mark:>8}  size={size}  {url}")
            except Exception as exc:
                print(f"  {MONTH_NAMES[month-1]:>10} {year}: ERROR -- {exc}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "st_louis_crime_trends",
        "source_url": "https://slmpd.org/stats/slmpd-downloadable-crime-files/",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest St. Louis SLMPD crime trends by neighborhood from CSV."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch data but do not write output file.",
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Check which SLMPD monthly CSV files are available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover_files()
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month St. Louis crime counts ({current_start:%Y-%m-%d} -> {now:%Y-%m-%d})...")
    current_data = fetch_crime_counts(current_start, now, args.dry_run)
    print(f"  {len(current_data)} neighborhoods with current data.")

    print(f"\nFetching prior 12-month St. Louis crime counts ({prior_start:%Y-%m-%d} -> {prior_end:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(prior_start, prior_end, args.dry_run)
    print(f"  {len(prior_data)} neighborhoods with prior data.")

    if not current_data and not prior_data:
        print(
            "ERROR: no data returned. CSV URL or field names may be wrong.\n"
            "  Run: python backend/ingest/st_louis_crime_trends.py --discover\n"
            "  Then check CSV_URL_TEMPLATE and field name constants.",
            file=sys.stderr,
        )
        sys.exit(1)

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} neighborhood trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} neighborhoods")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
