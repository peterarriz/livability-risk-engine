# Data Lane Handoff Guide

## Mission
Keep ingestion, normalization, and data-quality work moving while preserving the documented project schema and Chicago-only MVP scope.

## How Data maintains task flow
1. Keep Data tasks in `ops/TASKS.yaml` current, especially status, dependencies, and `notes_for_next_agent`.
2. Update `ops/lane_state.yaml` when Data is blocked on Product contracts or App integration needs.
3. When Data has fewer than three actionable tasks, run `python ops/generate_tasks.py` from the repo root.
4. Run `python ops/review_tasks.py` after task edits so duplicate or malformed task entries do not accumulate.

## What to hand off to other lanes
- To **Product**: source caveats, missing fields, and any limits that affect confidence or explanation language.
- To **App**: canonical field names, query constraints, and data freshness expectations needed for the `/score` experience.

## Source freshness checks (data-010)

Run before scoring or reviewing data quality:

```bash
python backend/ingest/check_freshness.py
```

Thresholds (from `docs/05_data_sources_chicago.md`):
- Building permits: staging file must be ≤ 26 hours old.
- Street closures: staging file must be ≤ 26 hours old.

Exit code 0 = all required sources fresh. Exit code 1 = one or more stale or missing.

Use `--json` for machine-readable output in review automation.

---

## Daily refresh steps (data-011)

Run in this order to keep the scoring engine populated with fresh data.

### Step 1 — Ingest building permits

```bash
python backend/ingest/building_permits.py
```

Output: `data/raw/building_permits.json` — raw permit records from the last 90 days.

### Step 2 — Ingest street closures

```bash
python backend/ingest/street_closures.py
```

Output: `data/raw/street_closures.json` — active and upcoming closure records.

### Step 3 — Fill missing coordinates (geocode-fill)

Geocodes staging records that have address text but no lat/lon, writing
the results back to the same JSON files before the DB load.

```bash
python backend/ingest/geocode_fill.py
```

Use `--dry-run` to see how many records would be filled without writing.
Use `--max-fill N` to limit API calls during testing.

### Step 4 — Load into canonical DB

Requires `POSTGRES_HOST` (and other `POSTGRES_*` vars) to be set.

```bash
python backend/ingest/load_projects.py --prune-days 90
```

`--prune-days 90` removes completed records older than 90 days from the
`projects` table, keeping it focused on the near-term scoring window.
Use `--dry-run` to validate normalization and see the prune count without
touching the DB.

### Step 5 — Verify freshness

```bash
python backend/ingest/check_freshness.py
```

### Step 6 — Review DB summary

```bash
python backend/ingest/db_summary.py
```

Prints counts by source, status, and impact_type. Share output with App
as a QA artifact after the first successful live-data load.

### Failure handling

| Failure | Action |
|---------|--------|
| Socrata API returns HTTP 429 or 503 | Wait 60s and retry; if persisting, note in `ops/lane_state.yaml` as a blocker. |
| Staging file written but record_count is 0 | Check the Socrata `$where` filter date logic; re-run with `--days-back 180` to widen the window. |
| `geocode_fill.py` shows high failed count | Addresses may be ambiguous or missing street number; check a sample with `geocode.py` directly. High failure rates for closures (street-only addresses) are expected. |
| DB upsert fails | Check `POSTGRES_*` env vars; run with `--dry-run` to confirm normalization is clean before re-attempting. |
| `check_freshness.py` reports stale after refresh | Re-run the relevant ingest script; the `ingested_at` timestamp is written at the end of a successful run. |

Handoff to App: once both sources are loaded, the `/score` endpoint returns live data automatically. App does not need to be restarted.

---

## Normalization QA checks (data-012)

These checks verify that normalized Project records are ready for the scoring engine.
Field names match `docs/04_api_contracts.md` and the canonical schema in `db/schema.sql`.

### Required field checks

| Field | Expected | Check |
|-------|----------|-------|
| `project_id` | Non-empty string matching `source:source_id` | `assert project_id == f"{source}:{source_id}"` |
| `source` | `"chicago_permits"` or `"chicago_closures"` | Allowlist check |
| `source_id` | Non-empty string | `assert source_id` |
| `impact_type` | One of: `closure_full`, `closure_multi_lane`, `closure_single_lane`, `demolition`, `construction`, `light_permit` | Allowlist check |
| `status` | One of: `active`, `planned`, `completed`, `unknown` | Allowlist check |
| `severity_hint` | One of: `HIGH`, `MEDIUM`, `LOW` | Allowlist check |
| `latitude` | Float in `[41.6445, 42.0230]` (Chicago bounding box) | Range check |
| `longitude` | Float in `[-87.9401, -87.5240]` (Chicago bounding box) | Range check |
| `start_date` | `date` or `None`; if both set, `start_date <= end_date` | Date ordering check |
| `end_date` | `date` or `None` | Type check |

### Run QA against staging files (dry-run mode)

```bash
python backend/ingest/load_projects.py --dry-run
```

Dry-run prints a sample project dict for each source. Any normalization error is printed with a `WARN:` prefix and increments the error counter.

### Interpreting QA output for App

The load summary printed by `load_projects.py` is the canonical QA report shared with App. Key fields:

- **Normalized**: records that passed normalization without errors.
- **Skipped (status)**: completed records excluded from scoring; expected and not a concern.
- **Skipped (no coords)**: records without lat/lon that cannot participate in radius queries. A high number here signals a geocoding gap.
- **Skipped (no source_id)**: records with a missing source key; these are a data quality issue and should be investigated.
- **Errors**: normalization failures; should be zero on clean data.

Share the summary block (copy-paste from terminal or redirect to a file) with App if the error or skipped-no-coords counts look unexpected.

---

## Review checklist
- Does the task preserve the canonical schema in `docs/04_api_contracts.md`?
- Does it avoid introducing new data sources outside the MVP unless explicitly documented as backlog?
- Is the next step deterministic enough that another agent can rerun or review it?
- Are staging files within freshness thresholds before reviewing scoring output?
- Does the load summary show zero errors and an acceptable skipped-no-coords rate?
