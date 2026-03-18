# Livability Risk Engine

Chicago-only MVP for returning a near-term construction disruption risk score for a single address via a JSON API and minimal demo UI.

## Mocked `/score` smoke check

Use these steps when App needs a quick confirmation that the mocked backend/frontend flow still matches the documented contract before real data wiring.

### 1. Start the mocked FastAPI backend

```bash
cd backend
uvicorn app.main:app --reload
```

Expected result:
- The server starts on `http://127.0.0.1:8000`.
- `GET /score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL` returns the mocked JSON contract fields: `address`, `disruption_score`, `confidence`, `severity`, `top_risks`, and `explanation`.

### 2. Smoke check the API response directly

```bash
curl "http://127.0.0.1:8000/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL"
```

Confirm that:
- `disruption_score` is an integer from 0 to 100.
- `severity` contains `noise`, `traffic`, and `dust`.
- `top_risks` is an ordered list of up to 3 display-ready strings.

### 3. Start the Next.js demo frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Expected result:
- The demo starts on `http://127.0.0.1:3000`.
- Submitting the default Chicago address renders the same mocked score, severity snapshot, top risks, and explanation returned by the API.

### 4. Record handoff notes if the smoke check fails

Capture:
- whether the failure is backend-only, frontend-only, or integration-related;
- the exact command used;
- and the contract field that drifted from `docs/04_api_contracts.md`.

## Task Ops

Use the task-ops workflow to keep Product, Data, and App queues stocked with small, reviewable tasks.

### Commands
- `python ops/generate_tasks.py` generates the next dependency-ready tasks for any lane below its target queue size.
- `python ops/generate_tasks.py --dry-run` previews what would be added without editing `ops/TASKS.yaml`.
- `python ops/review_tasks.py` validates task fields, duplicate IDs or titles, lane ownership, and dependency references.

### Teammate workflow
1. Finish a task by updating its row in `ops/TASKS.yaml`: set `status`, refresh `notes_for_next_agent`, and keep `files`, `dependencies`, and `acceptance_criteria` accurate.
2. Update `ops/lane_state.yaml` whenever your lane focus, blockers, or ready-queue target changes.
3. Run `python ops/generate_tasks.py` to top up any lane that has dropped below its actionable queue target.
4. Run `python ops/review_tasks.py` before committing so obvious task hygiene issues are caught early.
