"""
backend/ingest/pittsburgh_crime_trends.py
task: data-056
lane: data

Ingests Pittsburgh Bureau of Police crime data and calculates 12-month
crime trends by zone.

Source:
  CKAN — data.wprdc.org (Western PA Regional Data Center)
  Resource: Police Incident Blotter (30-day)
  Resource ID: 1797ead8-8262-41cc-9099-cbc8a161924b

  Key fields: INCIDENTTIME, INCIDENTZONE, INCIDENTHIERARCHYDESC

  Archived data (2016-2023): 044f2016-1dfd-4ab0-bc1e-065da05fca2e

Output:
  data/raw/pittsburgh_crime_trends.json

Usage:
  python backend/ingest/pittsburgh_crime_trends.py
  python backend/ingest/pittsburgh_crime_trends.py --dry-run
  python backend/ingest/pittsburgh_crime_trends.py --discover
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

CKAN_DOMAIN = "data.wprdc.org"

RESOURCE_ID_CURRENT = "1797ead8-8262-41cc-9099-cbc8a161924b"
RESOURCE_ID_ARCHIVE = "044f2016-1dfd-4ab0-bc1e-065da05fca2e"

DEFAULT_OUTPUT_PATH = Path("data/raw/pittsburgh_crime_trends.json")

DATE_FIELD = "INCIDENTTIME"
GROUP_FIELD = "INCIDENTZONE"

PITTSBURGH_LAT = 40.4406
PITTSBURGH_LON = -79.9959

STABLE_THRESHOLD_PCT = 5.0

PAGE_SIZE = 5000


def _ckan_url(action: str) -> str:
    return f"https://{CKAN_DOMAIN}/api/3/action/{action}"


def fetch_crime_counts_sql(
    resource_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    sql = (
        f'SELECT "{GROUP_FIELD}", count(*) as crime_count '
        f'FROM "{resource_id}" '
        f'WHERE "{DATE_FIELD}" >= \'{start_str}\' '
        f'AND "{DATE_FIELD}" < \'{end_str}\' '
        f'AND "{GROUP_FIELD}" IS NOT NULL '
        f'GROUP BY "{GROUP_FIELD}"'
    )

    url = _ckan_url("datastore_search_sql")
    response = requests.get(url, params={"sql": sql}, timeout=60)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"CKAN SQL error: {data.get('error', {})}")

    counts: dict[str, int] = {}
    for row in data["result"].get("records", []):
        zone = str(row.get(GROUP_FIELD, "") or "").strip()
        if not zone:
            continue
        try:
            counts[zone] = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            counts[zone] = 0
    return counts


def fetch_crime_counts_plain(
    resource_id: str,
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    counts: defaultdict[str, int] = defaultdict(int)
    offset = 0
    url = _ckan_url("datastore_search")

    while True:
        params = {
            "resource_id": resource_id,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            raise RuntimeError(f"CKAN error: {data.get('error', {})}")

        result = data["result"]
        records = result.get("records", [])
        total = result.get("total", 0)

        if not records:
            break

        for record in records:
            raw_date = str(record.get(DATE_FIELD, "") or "")[:10]
            if raw_date < start_str or raw_date >= end_str:
                continue
            zone = str(record.get(GROUP_FIELD, "") or "").strip()
            if zone:
                counts[zone] += 1

        offset += PAGE_SIZE

        if dry_run:
            print("  Dry-run: stopping after first page.")
            break

        if offset >= total:
            break

    return dict(counts)


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool,
) -> dict[str, int]:
    # Try both current (30-day blotter) and archive resources
    all_counts: dict[str, int] = {}

    for resource_id, label in [
        (RESOURCE_ID_CURRENT, "current blotter"),
        (RESOURCE_ID_ARCHIVE, "archive"),
    ]:
        print(f"  Attempting CKAN SQL ({label})...", end=" ", flush=True)
        try:
            counts = fetch_crime_counts_sql(resource_id, start_date, end_date)
            print(f"{len(counts)} zones.")
            for zone, count in counts.items():
                all_counts[zone] = all_counts.get(zone, 0) + count
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"\n  SQL endpoint returned HTTP {status} — trying plain search.", file=sys.stderr)
            try:
                counts = fetch_crime_counts_plain(resource_id, start_date, end_date, dry_run)
                for zone, count in counts.items():
                    all_counts[zone] = all_counts.get(zone, 0) + count
            except Exception as exc2:
                print(f"  WARN: {label} plain search also failed: {exc2}", file=sys.stderr)
        except Exception as exc:
            print(f"  WARN: {label} failed: {exc}", file=sys.stderr)

    return all_counts


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
    all_zones = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zone in sorted(all_zones):
        current_count = current_data.get(zone, 0)
        prior_count = prior_data.get(zone, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = zone.lower().replace(" ", "_")
        records.append({
            "region_type": "zone",
            "region_id": f"pittsburgh_zone_{slug}",
            "district_id": zone,
            "district_name": f"Pittsburgh Zone {zone}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": PITTSBURGH_LAT,
            "longitude": PITTSBURGH_LON,
        })
    return records


def discover_resource() -> None:
    url = _ckan_url("package_search")
    params = {"q": "police incident blotter", "rows": 10}

    print(f"Discovering crime datasets on {CKAN_DOMAIN}...")
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return

    packages = data.get("result", {}).get("results", [])
    if not packages:
        print("  No packages found.")
        return

    for pkg in packages:
        print(f"\n  Package: {pkg.get('name')} — {pkg.get('title')}")
        for res in pkg.get("resources", []):
            print(
                f"    resource_id={res['id']}  name={res.get('name', '?')!r}  "
                f"format={res.get('format', '?')}"
            )


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "pittsburgh_crime_trends",
        "source_url": f"https://{CKAN_DOMAIN}/api/3/action/datastore_search?resource_id={RESOURCE_ID_CURRENT}",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Pittsburgh crime trends by zone from CKAN (WPRDC)."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Query CKAN package_search to find crime dataset resource UUIDs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover_resource()
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Pittsburgh crime counts ({current_start.date()} → {now.date()})...")
    try:
        current_data = fetch_crime_counts(current_start, now, args.dry_run)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} zones with current crime data.")

    print(f"\nFetching prior 12-month Pittsburgh crime counts ({prior_start.date()} → {prior_end.date()})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end, args.dry_run)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} zones with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} zone trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} zones")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
