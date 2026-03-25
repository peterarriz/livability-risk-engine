"""
backend/ingest/jacksonville_crime_trends.py
task: data-050
lane: data

Ingests Jacksonville Sheriff's Office (JSO) crime data and calculates
12-month crime trends by zone.

Source:
  ArcGIS FeatureServer — COJ.net open data portal
  Service: JSO Crime Incidents

  MUST VERIFY service URL before production:
    python backend/ingest/jacksonville_crime_trends.py --discover
    Or visit: https://www.coj.net/departments/information-technology/gis.aspx
    Or search: https://geo.coj.net

  Verified service URL (ArcGIS Online, services3):
    https://services3.arcgis.com/7C7xW0yv6W8spzhp/arcgis/rest/services
    /Public_Transparency_Data_View/FeatureServer/0

  Verify sample record:
    curl "{service_url}/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json"

  Key fields (verified via sample query):
    IncidentDateTime  — date of incident
    ZipCode           — zip code (no Zone field in data)
    nibrsDescription  — NIBRS crime description

Output:
  data/raw/jacksonville_crime_trends.json — zone crime trend records

Usage:
  python backend/ingest/jacksonville_crime_trends.py
  python backend/ingest/jacksonville_crime_trends.py --dry-run
  python backend/ingest/jacksonville_crime_trends.py --discover
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

# Verified: JSO Transparency Data on ArcGIS Online (services3)
FEATURESERVER_URL = (
    "https://services3.arcgis.com/7C7xW0yv6W8spzhp/arcgis/rest/services"
    "/Public_Transparency_Data_View/FeatureServer/0"
)
PORTAL_ORG_ID = "7C7xW0yv6W8spzhp"

DEFAULT_OUTPUT_PATH = Path("data/raw/jacksonville_crime_trends.json")

# Verified field names via sample query
DATE_FIELD = "IncidentDateTime"
GROUP_FIELD = "ZipCode"

JACKSONVILLE_LAT = 30.3322
JACKSONVILLE_LON = -81.6557

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
        zipcode = str(attrs.get(GROUP_FIELD) or "").strip()
        if not zipcode:
            continue
        count = int(attrs.get("crime_count", 0) or attrs.get("CRIME_COUNT", 0))
        results[zipcode] = results.get(zipcode, 0) + count
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
    all_zips = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zipcode in sorted(all_zips):
        current_count = current_data.get(zipcode, 0)
        prior_count = prior_data.get(zipcode, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "zipcode",
            "region_id": f"jacksonville_zip_{zipcode}",
            "district_id": zipcode,
            "district_name": f"Jacksonville ZIP {zipcode}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": JACKSONVILLE_LAT,
            "longitude": JACKSONVILLE_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "jacksonville_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def discover(org_id: str) -> None:
    """Query ArcGIS Hub for crime datasets."""
    hub_url = "https://hub.arcgis.com/api/v3/search"
    params = {
        "q": "crime JSO incidents",
        "filter[orgid]": org_id,
        "fields[datasets]": "id,name,url",
        "page[size]": 5,
    }
    try:
        resp = requests.get(hub_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print("ArcGIS Hub search results (crime/JSO incidents):")
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            print(f"  {attrs.get('name','?')} — {attrs.get('url','?')}")
    except Exception as exc:
        print(f"Discover failed: {exc}")
    print(f"\nAlso try: https://geo.coj.net/arcgis/rest/services/PublicSafety")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Jacksonville JSO crime trends by zone from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Query ArcGIS Hub for available crime datasets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover(PORTAL_ORG_ID)
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Jacksonville crime counts "
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} zip codes, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Jacksonville crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} zip codes, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} zone trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} zip codes")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
