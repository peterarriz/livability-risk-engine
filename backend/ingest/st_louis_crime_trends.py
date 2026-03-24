"""
backend/ingest/st_louis_crime_trends.py
task: data-058
lane: data

Ingests St. Louis Metropolitan Police Department (SLMPD) crime data and
calculates 12-month crime trends by neighborhood/district.

Source:
  SLMPD publishes annual and monthly crime CSV files at slmpd.org/stats/
  Annual file URL pattern (MUST VERIFY):
    https://www.slmpd.org/Crime/{year}Annual.csv

  Verify available files:
    curl -I "https://www.slmpd.org/Crime/2025Annual.csv"
    curl -I "https://www.slmpd.org/Crime/2024Annual.csv"

  Alternatively, the SLMPD may publish monthly files:
    https://www.slmpd.org/Crime/CrimeXtMonth.csv   (current month)
    https://www.slmpd.org/Crime/{year}{month}.csv   (historical)

  Key fields (MUST VERIFY field names by downloading a sample CSV):
    Date         — date of incident (MM/DD/YYYY or similar)
    NeighborhoodDesc (or District) — geographic grouping
    Latitude, Longitude — incident coordinates

  If the URL pattern returns 404, visit slmpd.org/stats/ to find the
  current download links and update CSV_URL_TEMPLATE below.

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

# SLMPD annual crime CSV files.
# MUST VERIFY URL pattern: visit https://www.slmpd.org/stats/ to confirm.
# Typical pattern: https://www.slmpd.org/Crime/{year}Annual.csv
CSV_URL_TEMPLATE = "https://www.slmpd.org/Crime/{year}Annual.csv"

# Fallback: SLMPD also publishes a running YTD file
CSV_CURRENT_MONTH_URL = "https://www.slmpd.org/Crime/CrimeXtMonth.csv"

DEFAULT_OUTPUT_PATH = Path("data/raw/st_louis_crime_trends.json")

# MUST VERIFY: Run --dry-run to inspect the CSV headers and update these.
# Common SLMPD field names include: "NeighborhoodDesc", "District",
#   "Neighborhood", "CodedMonth", "DateOccur", "Latitude", "Longitude"
DATE_FIELD = "DateOccur"           # MUST VERIFY
DISTRICT_FIELD = "NeighborhoodDesc"  # MUST VERIFY — may be "District" or "Neighborhood"
LAT_FIELD = "Latitude"             # MUST VERIFY
LON_FIELD = "Longitude"            # MUST VERIFY

ST_LOUIS_LAT = 38.6270
ST_LOUIS_LON = -90.1994

STABLE_THRESHOLD_PCT = 5.0


def _years_in_range(start: datetime, end: datetime) -> list[int]:
    years = set()
    d = start
    while d <= end:
        years.add(d.year)
        d += timedelta(days=365)
    years.add(end.year)
    return sorted(years)


def _parse_date(raw: str) -> str | None:
    """Parse various SLMPD date formats and return YYYY-MM-DD or None."""
    raw = raw.strip()
    if not raw:
        return None
    # Try MM/DD/YYYY
    try:
        if "/" in raw:
            parts = raw.split("/")
            if len(parts) == 3:
                m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2][:4]
                return f"{y}-{m}-{d}"
    except (IndexError, ValueError):
        pass
    # Try YYYY-MM-DD or ISO-like
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    return None


def _fetch_and_count(
    year: int,
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, dict]:
    """Download SLMPD annual CSV for one year, filter by date range, count by district."""
    url = CSV_URL_TEMPLATE.format(year=year)
    print(f"    Downloading {url}...", end=" ", flush=True)

    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            print(f"HTTP 404 — skipping year {year}")
            return {}
        raise

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

            district = (row.get(DISTRICT_FIELD) or "").strip().upper()
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
        print(f"WARN: CSV parse error for {year}: {exc}")
        return {}

    total = sum(v["count"] for v in counts.values())
    print(f"{total:,} matching crimes in {len(counts)} districts")

    # Compute centroid averages
    result: dict[str, dict] = {}
    for dist, v in counts.items():
        avg_lat = (v["lat_sum"] / v["n"]) if v["n"] > 0 else None
        avg_lon = (v["lon_sum"] / v["n"]) if v["n"] > 0 else None
        result[dist] = {"count": v["count"], "lat": avg_lat, "lon": avg_lon}
    return result


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, dict]:
    combined: dict[str, dict] = {}
    for year in _years_in_range(start_date, end_date):
        try:
            year_counts = _fetch_and_count(year, start_date, end_date, dry_run)
            for district, v in year_counts.items():
                if district not in combined:
                    combined[district] = {"count": 0, "lat": v["lat"], "lon": v["lon"]}
                combined[district]["count"] += v["count"]
                if v["lat"] and not combined[district]["lat"]:
                    combined[district]["lat"] = v["lat"]
                    combined[district]["lon"] = v["lon"]
        except Exception as exc:
            print(f"WARN: year {year} — {exc}")
    return combined


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
    """Check which SLMPD annual CSV files are available."""
    print("Discovering SLMPD annual CSV files...")
    for year in range(2019, datetime.now().year + 2):
        url = CSV_URL_TEMPLATE.format(year=year)
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            size = resp.headers.get("Content-Length", "?")
            print(f"  {year}: HTTP {resp.status_code} — {url} (size={size})")
        except Exception as exc:
            print(f"  {year}: ERROR — {exc}")
    # Also check the current month file
    try:
        resp = requests.head(CSV_CURRENT_MONTH_URL, timeout=10, allow_redirects=True)
        print(f"  Current month: HTTP {resp.status_code} — {CSV_CURRENT_MONTH_URL}")
    except Exception as exc:
        print(f"  Current month: ERROR — {exc}")


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "st_louis_crime_trends",
        "source_url": CSV_URL_TEMPLATE.format(year="YYYY"),
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
        help="Check which SLMPD annual CSV files are available.",
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

    print(f"Fetching current 12-month St. Louis crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    print(f"  NOTE: Run --discover first to verify CSV URL pattern.")
    print(f"  Field names (DATE_FIELD={DATE_FIELD!r}, DISTRICT_FIELD={DISTRICT_FIELD!r}) MUST VERIFY.")
    current_data = fetch_crime_counts(current_start, now, args.dry_run)
    print(f"  {len(current_data)} districts with current data.")

    print(f"\nFetching prior 12-month St. Louis crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    prior_data = fetch_crime_counts(prior_start, prior_end, args.dry_run)
    print(f"  {len(prior_data)} districts with prior data.")

    if not current_data and not prior_data:
        print(
            "ERROR: no data returned. CSV URL or field names may be wrong.\n"
            "  Run: python backend/ingest/st_louis_crime_trends.py --discover\n"
            "  Then update CSV_URL_TEMPLATE, DATE_FIELD, DISTRICT_FIELD.",
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
