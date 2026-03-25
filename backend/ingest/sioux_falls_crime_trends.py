"""
backend/ingest/sioux_falls_crime_trends.py
task: data-070
lane: data

Ingests Sioux Falls Police Department crime data and calculates 12-month
crime trends by district/sector.

Source:
  ArcGIS FeatureServer — ArcGIS Hub (City of Sioux Falls)
  Portal: https://hub.arcgis.com/datasets (search "Sioux Falls crime")

  Service URL (MUST VERIFY):
    https://services.arcgis.com/Nf5qHqEDvuX5aNFd/arcgis/rest/services
    /SFPD_Crime_Incidents/FeatureServer/0

  To verify:
    python backend/ingest/sioux_falls_crime_trends.py --dry-run
    Or search ArcGIS Hub for "Sioux Falls police crime incidents"
    Click the dataset → "I want to use this" → "API" to get the FeatureServer URL.

  Key fields (MUST VERIFY field names via --dry-run):
    ReportedDate  — date of incident (MUST VERIFY)
    Sector        — patrol sector/district (MUST VERIFY)

Output:
  data/raw/sioux_falls_crime_trends.json

Usage:
  python backend/ingest/sioux_falls_crime_trends.py
  python backend/ingest/sioux_falls_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# MUST VERIFY — search ArcGIS Hub for "Sioux Falls crime" to find correct URL
FEATURESERVER_URL = (
    "https://services.arcgis.com/Nf5qHqEDvuX5aNFd/arcgis/rest/services"
    "/SFPD_Crime_Incidents/FeatureServer/0"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/sioux_falls_crime_trends.json")

# MUST VERIFY field names via --dry-run
DATE_FIELD = "ReportedDate"
GROUP_FIELD = "Sector"

SIOUX_FALLS_LAT = 43.5460
SIOUX_FALLS_LON = -96.7313

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = f"{FEATURESERVER_URL}/query"

    where_clause = (
        f"{DATE_FIELD} >= {_date_str(start_date)} "
        f"AND {DATE_FIELD} < {_date_str(end_date)}"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
    ])

    params = {
        "where": where_clause,
        "groupByFieldsForStatistics": GROUP_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(url, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        sector = str(attrs.get(GROUP_FIELD) or "").strip()
        if not sector:
            continue
        count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
        results[sector] = results.get(sector, 0) + count
    return results


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
    all_sectors = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for sector in sorted(all_sectors):
        current_count = current_data.get(sector, 0)
        prior_count = prior_data.get(sector, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = sector.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "sector",
            "region_id": f"sioux_falls_sector_{slug}",
            "district_id": sector,
            "district_name": f"Sioux Falls Sector {sector}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": SIOUX_FALLS_LAT,
            "longitude": SIOUX_FALLS_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "sioux_falls_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Sioux Falls SFPD crime trends by sector from ArcGIS FeatureServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Sioux Falls crime trends ingest — source: {FEATURESERVER_URL}")
    print("NOTE: Service URL and field names are MUST VERIFY estimates.")
    print("Verify via: ArcGIS Hub search 'Sioux Falls crime incidents'")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} sectors, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} sectors, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} sector trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} sectors")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
