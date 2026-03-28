"""
backend/ingest/fhfa_hpi.py
task: data-081
lane: data

Ingests FHFA House Price Index (HPI) data at zip code and metro (CBSA) level.
Data is quarterly, going back to 2008 for zip-level and further for metro-level.

Sources:
  FHFA HPI zip-level (XLSX, quarterly since 2008):
    https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx
  FHFA HPI metro-level (CSV, quarterly):
    https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv

Output:
  data/raw/fhfa_hpi_zip.json   — most recent HPI per 5-digit ZIP code
  data/raw/fhfa_hpi_metro.json — most recent HPI per metro CBSA

Usage:
  python backend/ingest/fhfa_hpi.py
  python backend/ingest/fhfa_hpi.py --dry-run
  python backend/ingest/fhfa_hpi.py --source zip
  python backend/ingest/fhfa_hpi.py --source metro

Prerequisites:
  pip install openpyxl requests
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# FHFA restructured their site in 2025. Old /sites/default/files/YYYY-MM/ paths
# now 404. New paths use /hpi/download/{annual,quarterly_datasets}/ with lowercase
# filenames. Verified 2026-03-28.
ZIP_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx"
METRO_URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv"

ZIP_OUTPUT_PATH = Path("data/raw/fhfa_hpi_zip.json")
METRO_OUTPUT_PATH = Path("data/raw/fhfa_hpi_metro.json")

# Download timeout in seconds — XLSX file can be ~20 MB
DOWNLOAD_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Column-name normalization
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Lowercase, strip, replace spaces/special chars with underscore."""
    return (
        name.lower()
        .strip()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace("%", "pct")
        .replace("/", "_")
    )


def _find_col(headers: list[str], candidates: list[str]) -> str | None:
    """Return the first header (normalized) that matches any candidate string."""
    norm_headers = [_norm(h) for h in headers]
    for candidate in candidates:
        target = _norm(candidate)
        if not target:
            continue
        for i, nh in enumerate(norm_headers):
            if not nh:
                continue  # skip empty headers
            if target in nh or nh in target:
                return headers[i]
    return None


# ---------------------------------------------------------------------------
# Zip-level XLSX parsing
# ---------------------------------------------------------------------------

def _parse_zip_xlsx(content: bytes, dry_run: bool) -> list[dict]:
    """
    Parse the FHFA HPI zip-level XLSX file.

    Expected columns (FHFA may vary naming slightly):
      zip5 / ZIP Code / Five-Digit ZIP Code
      yr / Year
      qtr / Quarter
      index_nsa / Index (NSA) / HPI
      annual_chg / Annual Change (%) / 1-Year Change
      yr5_chg / Five-Year Change (%) / 5-Year Change
      yr10_chg / Ten-Year Change (%) / 10-Year Change
    """
    if not HAS_OPENPYXL:
        raise ImportError(
            "openpyxl is required for ZIP-level XLSX parsing. "
            "Install with: pip install openpyxl"
        )

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)

    # Find header row — skip title rows until we find one with multiple
    # non-empty cells containing column-name keywords like "zip", "year", etc.
    # (FHFA XLSX has a title row with a single merged cell before the headers)
    headers: list[str] = []
    for row in rows_iter:
        non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if len(non_empty) < 3:
            continue  # skip title rows (single merged cell) and blanks
        candidate = [str(c) if c is not None else "" for c in row]
        headers = candidate
        break

    if not headers:
        raise ValueError("ZIP XLSX: could not find header row")

    print(f"  ZIP XLSX headers: {headers[:10]}")

    # Map columns
    zip_col = _find_col(headers, ["zip5", "zip code", "five-digit zip", "zip"])
    year_col = _find_col(headers, ["year", "yr"])
    qtr_col = _find_col(headers, ["quarter", "qtr"])
    index_col = _find_col(headers, ["index_nsa", "index (nsa)", "hpi", "index nsa", "index"])
    annual_col = _find_col(headers, [
        "annual_chg", "annual change", "1-year change", "1yr", "annual_change",
        "1_year_change", "1year",
    ])
    yr5_col = _find_col(headers, [
        "yr5_chg", "five-year change", "5-year change", "5yr", "5_year_change",
    ])
    yr10_col = _find_col(headers, [
        "yr10_chg", "ten-year change", "10-year change", "10yr", "10_year_change",
    ])

    if not zip_col or not year_col or not index_col:
        raise ValueError(
            f"ZIP XLSX: missing required columns. Found: {headers}. "
            f"zip={zip_col}, year={year_col}, qtr={qtr_col}, index={index_col}"
        )

    zip_i = headers.index(zip_col)
    year_i = headers.index(year_col)
    qtr_i = headers.index(qtr_col) if qtr_col else None
    index_i = headers.index(index_col)
    annual_i = headers.index(annual_col) if annual_col else None
    yr5_i = headers.index(yr5_col) if yr5_col else None
    yr10_i = headers.index(yr10_col) if yr10_col else None

    # Accumulate all rows per zip: {zip5: [(year, qtr, index, annual, yr5, yr10), ...]}
    zip_data: dict[str, list[tuple]] = {}
    row_count = 0

    for row in rows_iter:
        row_count += 1
        if dry_run and row_count > 50000:
            print("  Dry-run: stopping after 50,000 data rows.")
            break

        zip5 = row[zip_i]
        year = row[year_i]
        qtr = row[qtr_i] if qtr_i is not None else 4  # annual data defaults to Q4
        index_val = row[index_i]

        # Skip rows with missing key fields
        if zip5 is None or year is None or index_val is None:
            continue

        # Normalize zip to 5-digit string (Excel may store as int)
        zip5_str = str(zip5).strip().zfill(5)
        if not zip5_str.isdigit() or len(zip5_str) != 5:
            continue

        try:
            yr = int(year)
            qt = int(qtr)
            idx = float(index_val)
        except (TypeError, ValueError):
            continue

        annual = None
        yr5 = None
        yr10 = None

        if annual_i is not None and row[annual_i] is not None:
            try:
                annual = float(row[annual_i])
            except (TypeError, ValueError):
                pass
        if yr5_i is not None and row[yr5_i] is not None:
            try:
                yr5 = float(row[yr5_i])
            except (TypeError, ValueError):
                pass
        if yr10_i is not None and row[yr10_i] is not None:
            try:
                yr10 = float(row[yr10_i])
            except (TypeError, ValueError):
                pass

        if zip5_str not in zip_data:
            zip_data[zip5_str] = []
        zip_data[zip5_str].append((yr, qt, idx, annual, yr5, yr10))

    wb.close()
    print(f"  Parsed {row_count} data rows covering {len(zip_data)} ZIP codes.")

    return _build_zip_records(zip_data)


def _build_zip_records(zip_data: dict[str, list[tuple]]) -> list[dict]:
    """
    For each ZIP, take the most recent quarter. Compute change % from
    the time series if pre-computed values are missing.
    """
    records = []
    for zip5, entries in zip_data.items():
        # Sort by (year, quarter) descending
        entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
        latest = entries[0]
        yr, qt, idx_val, annual, yr5, yr10 = latest
        period = f"{yr}Q{qt}"

        # Compute missing changes from time series
        if annual is None:
            annual = _compute_change(entries, 0, 4)   # 4 quarters back = 1 year
        if yr5 is None:
            yr5 = _compute_change(entries, 0, 20)     # 20 quarters = 5 years
        if yr10 is None:
            yr10 = _compute_change(entries, 0, 40)    # 40 quarters = 10 years

        records.append({
            "region_type": "zip",
            "region_id": zip5,
            "hpi_index_value": round(idx_val, 2),
            "hpi_1yr_change": round(annual, 4) if annual is not None else None,
            "hpi_5yr_change": round(yr5, 4) if yr5 is not None else None,
            "hpi_10yr_change": round(yr10, 4) if yr10 is not None else None,
            "hpi_period": period,
        })

    return records


def _compute_change(
    entries: list[tuple],
    current_idx: int,
    n_quarters_back: int,
) -> float | None:
    """
    Compute pct change between entries[current_idx] and the entry
    n_quarters_back periods earlier (entries is sorted newest-first).
    Returns None if insufficient history.
    """
    if len(entries) <= n_quarters_back:
        return None
    cur_val = entries[current_idx][2]   # index value
    old_val = entries[n_quarters_back][2]
    if old_val == 0:
        return None
    return round((cur_val - old_val) / old_val * 100, 4)


# ---------------------------------------------------------------------------
# Metro CSV parsing
# ---------------------------------------------------------------------------

def _parse_metro_csv(content: bytes, dry_run: bool) -> list[dict]:
    """
    Parse the FHFA HPI metro-level CSV file.

    Expected columns:
      CBSA Code / cbsa / cbsa_code
      Metropolitan Area / metro_name / name
      Year / yr / year
      Quarter / qtr / quarter
      Index (NSA) / index_nsa / hpi
      Annual Change (%) / annual_chg / 1yr_change
      Five-Year Change (%) / yr5_chg
      Ten-Year Change (%) / yr10_chg (if available)
    """
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))

    # Find header row
    headers: list[str] = []
    header_lineno = 0
    for lineno, row in enumerate(csv.reader(io.StringIO(text))):
        non_empty = [c for c in row if c.strip()]
        if non_empty:
            headers = row
            header_lineno = lineno
            break

    if not headers:
        raise ValueError("Metro CSV: could not find header row")

    print(f"  Metro CSV headers: {headers[:10]}")

    cbsa_col = _find_col(headers, ["cbsa", "cbsa_code", "cbsa code"])
    name_col = _find_col(headers, ["metropolitan area", "metro_name", "metro", "name"])
    year_col = _find_col(headers, ["year", "yr"])
    qtr_col = _find_col(headers, ["quarter", "qtr"])
    index_col = _find_col(headers, ["index_nsa", "index (nsa)", "hpi", "index nsa", "index"])
    annual_col = _find_col(headers, [
        "annual_chg", "annual change", "1-year change", "1yr", "annual_change",
    ])
    yr5_col = _find_col(headers, ["yr5_chg", "five-year change", "5-year change", "5yr"])
    yr10_col = _find_col(headers, ["yr10_chg", "ten-year change", "10-year change", "10yr"])

    # Headerless CSV fallback: FHFA's new download has no header row.
    # Fixed column order: metro_name, cbsa_code, year, quarter, index_nsa, annual_change
    if not cbsa_col or not year_col or not qtr_col or not index_col:
        print("  No header row detected — using positional column mapping.")
        name_i = 0
        cbsa_i = 1
        year_i = 2
        qtr_i = 3
        index_i = 4
        annual_i = 5 if len(headers) > 5 else None
        yr5_i = None
        yr10_i = None
        header_lineno = -1  # re-read from start since "header" is data
    else:
        cbsa_i = headers.index(cbsa_col)
        name_i = headers.index(name_col) if name_col else None
        year_i = headers.index(year_col)
        qtr_i = headers.index(qtr_col)
        index_i = headers.index(index_col)
        annual_i = headers.index(annual_col) if annual_col else None
        yr5_i = headers.index(yr5_col) if yr5_col else None
        yr10_i = headers.index(yr10_col) if yr10_col else None

    # Re-read and skip to data rows
    metro_data: dict[str, list[tuple]] = {}
    metro_names: dict[str, str] = {}
    row_count = 0

    lines = text.splitlines()
    data_reader = csv.reader(lines[header_lineno + 1:])
    for row in data_reader:
        if not any(c.strip() for c in row):
            continue
        row_count += 1
        if dry_run and row_count > 5000:
            print("  Dry-run: stopping after 5,000 metro rows.")
            break

        if len(row) <= max(cbsa_i, year_i, qtr_i, index_i):
            continue

        cbsa = row[cbsa_i].strip()
        year = row[year_i].strip()
        qtr = row[qtr_i].strip()
        index_val = row[index_i].strip()

        if not cbsa or not year or not qtr or not index_val:
            continue

        # Store metro name for readability
        if name_i is not None and len(row) > name_i:
            metro_names[cbsa] = row[name_i].strip()

        try:
            yr = int(year)
            qt = int(qtr)
            idx = float(index_val)
        except (TypeError, ValueError):
            continue

        annual = None
        yr5 = None
        yr10 = None

        if annual_i is not None and len(row) > annual_i and row[annual_i].strip():
            try:
                annual = float(row[annual_i].strip())
            except ValueError:
                pass
        if yr5_i is not None and len(row) > yr5_i and row[yr5_i].strip():
            try:
                yr5 = float(row[yr5_i].strip())
            except ValueError:
                pass
        if yr10_i is not None and len(row) > yr10_i and row[yr10_i].strip():
            try:
                yr10 = float(row[yr10_i].strip())
            except ValueError:
                pass

        if cbsa not in metro_data:
            metro_data[cbsa] = []
        metro_data[cbsa].append((yr, qt, idx, annual, yr5, yr10))

    print(f"  Parsed {row_count} metro data rows covering {len(metro_data)} CBSAs.")

    return _build_metro_records(metro_data, metro_names)


def _build_metro_records(
    metro_data: dict[str, list[tuple]],
    metro_names: dict[str, str],
) -> list[dict]:
    """For each CBSA, take the most recent quarter."""
    records = []
    for cbsa, entries in metro_data.items():
        entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
        latest = entries[0]
        yr, qt, idx_val, annual, yr5, yr10 = latest
        period = f"{yr}Q{qt}"

        if annual is None:
            annual = _compute_change(entries, 0, 4)
        if yr5 is None:
            yr5 = _compute_change(entries, 0, 20)
        if yr10 is None:
            yr10 = _compute_change(entries, 0, 40)

        records.append({
            "region_type": "metro",
            "region_id": cbsa,
            "hpi_index_value": round(idx_val, 2),
            "hpi_1yr_change": round(annual, 4) if annual is not None else None,
            "hpi_5yr_change": round(yr5, 4) if yr5 is not None else None,
            "hpi_10yr_change": round(yr10, 4) if yr10 is not None else None,
            "hpi_period": period,
            "metro_name": metro_names.get(cbsa),
        })

    return records


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download(url: str, label: str) -> bytes:
    print(f"Downloading {label} from:\n  {url}")
    resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
    resp.raise_for_status()

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        chunks.append(chunk)
        total += len(chunk)
        if total % (5 * 1024 * 1024) < 65536:
            print(f"  Downloaded {total // (1024 * 1024)} MB...", end="\r", flush=True)

    content = b"".join(chunks)
    print(f"  Downloaded {len(content) // 1024:,} KB total.")
    return content


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _write_staging(records: list[dict], output_path: Path, source_key: str, source_url: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging: dict[str, Any] = {
        "source": source_key,
        "source_url": source_url,
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
        description="Ingest FHFA House Price Index (HPI) data by ZIP and metro."
    )
    parser.add_argument(
        "--source",
        choices=["zip", "metro", "all"],
        default="all",
        help="Which FHFA HPI source to ingest: zip, metro, or all (default: all).",
    )
    parser.add_argument(
        "--zip-output",
        type=Path,
        default=ZIP_OUTPUT_PATH,
        help=f"Output path for zip-level staging file (default: {ZIP_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--metro-output",
        type=Path,
        default=METRO_OUTPUT_PATH,
        help=f"Output path for metro-level staging file (default: {METRO_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse data but do not write output files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not HAS_OPENPYXL and args.source in ("zip", "all"):
        print(
            "ERROR: openpyxl is required for ZIP-level XLSX parsing.\n"
            "Install with: pip install openpyxl",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.source in ("zip", "all"):
        print("\n=== FHFA HPI — ZIP Level ===")
        try:
            content = _download(ZIP_URL, "FHFA HPI zip-level XLSX")
            records = _parse_zip_xlsx(content, args.dry_run)
            print(f"Total ZIP HPI records: {len(records)}")
            if records:
                print(f"  Sample: {json.dumps(records[0])}")
            if not args.dry_run:
                _write_staging(records, args.zip_output, "hpi_zip", ZIP_URL)
        except Exception as exc:
            print(f"ERROR: ZIP-level ingest failed — {exc}", file=sys.stderr)
            sys.exit(1)

    if args.source in ("metro", "all"):
        print("\n=== FHFA HPI — Metro Level ===")
        try:
            content = _download(METRO_URL, "FHFA HPI metro-level CSV")
            records = _parse_metro_csv(content, args.dry_run)
            print(f"Total metro HPI records: {len(records)}")
            if records:
                print(f"  Sample: {json.dumps(records[0])}")
            if not args.dry_run:
                _write_staging(records, args.metro_output, "hpi_metro", METRO_URL)
        except Exception as exc:
            print(f"ERROR: Metro-level ingest failed — {exc}", file=sys.stderr)
            sys.exit(1)

    if not args.dry_run:
        print("\nDone.")
    else:
        print("\nDry-run mode: no files written.")


if __name__ == "__main__":
    main()
