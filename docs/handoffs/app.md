# App Lane Handoff Guide

## Mission
Ship the smallest usable API and demo frontend that matches the documented contract and can be reviewed quickly.

## How App maintains task flow
1. Work from `ready` App tasks in `ops/TASKS.yaml` and keep `notes_for_next_agent` updated after each change.
2. Update `ops/lane_state.yaml` when App is blocked on Data output or Product contract decisions.
3. When the actionable App queue drops below target, run `python ops/generate_tasks.py` from the repo root.
4. Use `python ops/review_tasks.py` before handing off work so task metadata stays clean.

## What to hand off to other lanes
- To **Product**: wording mismatches, confidence-display questions, and demo-flow feedback.
- To **Data**: field mismatches, missing query behavior, and timing constraints from the `/score` flow.

## Review checklist
- Does the task preserve the documented `/score` request and response contract?
- Does it avoid turning the frontend demo into a broader product redesign?
- Is the next App task specific enough to implement with a small, reviewable PR?

## Current state (2026-03-19)
- All app tasks through `app-018` are done.
- `app-008` (connect frontend to real backend) is complete: the backend now uses the live scoring path when `POSTGRES_HOST` is set, with a graceful demo fallback when it is not.
- `app-019`–`app-024` add observability, mode transparency, and this runbook.
- `app-007` (map view) remains backlog — defer unless demo polish is explicitly prioritised.

## 30-second broker demo flow (high-risk + low-risk)

Use this exact sequence in live demos, investor calls, and YC-style interviews.

### Setup
- Open `/app`.
- Narrate the positioning in one line: **“Helps brokers spot disruption risk before tenant tours and lease commitments.”**

### Step 1 (0:00–0:15) — High-risk address
- Enter: **1600 W Chicago Ave, Chicago, IL**.
- What appears on screen:
  - Elevated score band (high-risk profile).
  - Top drivers prioritize lane/closure + construction signals.
  - Severity shows stronger traffic/access friction.
  - Map highlights nearby signals around the address.
- Broker decision:
  - “I won’t schedule a peak-hour tenant tour until we validate access windows and loading conditions.”

### Step 2 (0:15–0:30) — Low-risk address
- Enter: **11900 S Morgan St, Chicago, IL**.
- What appears on screen:
  - Low score band with limited near-term disruption signals.
  - Drivers are weaker/minimal; severity remains low.
  - Map shows sparse nearby disruption context.
- Broker decision:
  - “This is safer for near-term touring and move-in timing, so we can prioritize it in this week’s showing plan.”

### Why this lands in interviews
- Same workflow, two outcomes, immediate action difference.
- Shows the product is not just analytics — it changes broker behavior in under 30 seconds.

## Mocked `/score` smoke-check handoff
- Start the mocked backend with `cd backend && uvicorn app.main:app --reload`.
- Verify the contract directly with `curl "http://127.0.0.1:8000/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL"`.
- Start the frontend with `cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev`.
- Confirm the submitted default address renders the same score payload fields the backend returns.
- If the smoke check fails, note the exact command, failing layer, and contract mismatch before handing off.

---

## Internal validation runbook (app-024)

For post-deploy live-score review, also use `docs/live_score_validation.md` for the 5-address smoke-test set and review table template.
Use `docs/deploy_readiness_checklist.md` to confirm whether the deployed app is truly live or still falling back to demo mode.

Use this runbook to validate the full app/backend path in under 10 minutes.
Written for operators, not developers — no source code knowledge required.

### Prerequisites
```bash
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload
# Backend now running at http://127.0.0.1:8000
```

---

### Step 1 — Check /health

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

`/health` is public liveness only. It should respond quickly and should not
attempt a DB connection.

**Expected when the DB is not configured**:
```json
{
  "status": "ok",
  "mode": "unconfigured",
  "db_configured": false
}
```

**Expected when the DB is configured**:
```json
{
  "status": "ok",
  "mode": "live",
  "db_configured": true
}
```

To check DB readiness, use the protected `/health/db` endpoint with
`X-Admin-Secret`, or run `scripts/demo_smoke_check.py` with `ADMIN_SECRET` set:

```bash
curl -s \
  -H "X-Admin-Secret: ${ADMIN_SECRET:?set ADMIN_SECRET}" \
  http://127.0.0.1:8000/health/db \
  | python3 -m json.tool
```

**Expected DB-readiness response when DB is reachable**:
```json
{
  "status": "ok",
  "db_configured": true,
  "db_connection": true,
  "last_ingest_status": null
}
```

If `/health/db` reports `db_connection: false`, do not proceed to a live demo.
The public `/health` endpoint can still be healthy while DB readiness is failing.

---

### Step 2 — Check /score

```bash
curl -s "http://127.0.0.1:8000/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" | python3 -m json.tool
```

**Expected in demo mode**: all approved demo response fields plus `"mode": "demo"` and `"fallback_reason": "db_not_configured"`.

**Expected in live mode**: scored response plus `"mode": "live"` and `"fallback_reason": null`.

Confirm the following fields are present in both modes:
- `disruption_score` — integer 0–100
- `confidence` — one of `HIGH | MEDIUM | LOW`
- `severity.noise`, `severity.traffic`, `severity.dust` — each `HIGH | MEDIUM | LOW`
- `top_risks` — list of 1–3 plain-English strings
- `explanation` — one short paragraph
- `mode` — `"live"` or `"demo"`
- `fallback_reason` — string or `null`

---

### Step 3 — Optional operator /debug/score check

Normal demo validation should use:

```bash
# From the repository root:
python3 scripts/demo_smoke_check.py --backend-url http://127.0.0.1:8000 --require-live
```

`/debug/score` is internal and requires `X-Admin-Secret`. Use it only when
an operator needs lower-level geocoding/project-count detail:

```bash
curl -s \
  -H "X-Admin-Secret: ${ADMIN_SECRET:?set ADMIN_SECRET}" \
  "http://127.0.0.1:8000/debug/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" \
  | python3 -m json.tool
```

**Expected in live mode**:
```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "mode": "live",
  "lat": <number>,
  "lon": <number>,
  "nearby_projects_count": <integer>,
  "nearby_projects_sample": [ ... up to 5 project summaries ... ],
  "score_result": { ... full score response ... },
  "fallback_reason": null
}
```

**In demo mode** (DB not configured): returns `mode: "demo"`, `lat: null`, `nearby_projects_count: null`.

Use `nearby_projects_count` to confirm data is present. A count of `0` for the approved demo address (`1600 W Chicago Ave`) when live suggests the ingest pipeline has not completed — check with the data lane.

---

### Step 4 — Check frontend mode badge

With the backend running and frontend started:
```bash
cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Submit `1600 W Chicago Ave, Chicago, IL`.

- In demo mode: a **"Demo scenario"** badge should appear below the form.
- In live mode: a **"Live data • Chicago"** badge should appear below the form.
- Open browser DevTools → Console. If `fallback_reason` is present in the backend response, it will be logged as `[LRE] backend fallback_reason: <reason>`.

---

### Failure triage

| Symptom | Likely cause | Fix path |
|---|---|---|
| `/health` returns 404 | Old backend version running | Restart with updated `main.py` |
| `db_configured: false` but `POSTGRES_HOST` is set | Env var not exported to process | Confirm `export POSTGRES_HOST=...` before starting uvicorn |
| `/health/db` reports `db_connection: false` with `db_configured: true` | DB not reachable | Check DB host/port, firewall, and credentials |
| `/score` returns `mode: "demo"` when live expected | Geocoding failed or DB query error | Run `scripts/demo_smoke_check.py`; use admin `/debug/score` only if deeper operator detail is needed |
| Frontend shows "Demo scenario" despite live backend | Backend returning demo fallback | Run the smoke script against the backend, then check console for `fallback_reason` |
| `nearby_projects_count: 0` in admin `/debug/score` | Ingest pipeline not run | Ask data lane to run `backend/ingest/` scripts against live DB |
