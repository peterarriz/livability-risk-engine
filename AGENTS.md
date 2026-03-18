# AGENTS.md

## Repo purpose
Livability Risk Engine is a Chicago-only MVP for producing a near-term construction disruption risk score for a single address. The MVP output is a JSON API response with `address`, `disruption_score`, `confidence`, `severity`, `top_risks`, and `explanation`. Work in this repo should improve delivery of that MVP only.

## Scope constraints
- Do not expand beyond the Chicago MVP.
- Do not add multi-city support, user accounts, billing, mobile apps, or real-time traffic feeds.
- Do not redesign scoring logic; only implement or document the already-approved rule-based model.
- Do not change the API contract unless a reviewed cross-lane decision explicitly requires a naming alignment.

## Read first: source-of-truth docs
Before making changes, read the docs that govern the task you are touching:
1. `docs/00_project_brief.md`
2. `docs/01_mvp_scope.md`
3. `docs/04_api_contracts.md`
4. `docs/06_team_working_agreement.md`
5. `ops/TASKS.yaml`
6. Lane handoff doc for the lane you are working in:
   - `docs/handoffs/product.md`
   - `docs/handoffs/data.md`
   - `docs/handoffs/app.md`

## 3-lane workflow
- **product**: scope, success criteria, scoring guidance, explanations, stakeholder validation.
- **data**: ingestion, normalization, schema alignment, data quality, geospatial/query work.
- **app**: FastAPI backend, `/score` endpoint, frontend demo, integration flow.

Stay in your lane unless a cross-lane edit is required to complete the task safely.

## Task system
### Pick a task
- `ops/TASKS.yaml` is the source of truth.
- Prefer a task in your lane with `status: ready`.
- Respect `dependencies` before starting work.
- If no suitable `ready` task exists, check `ops/lane_state.yaml` and the relevant handoff doc before changing anything.

### Update a task
- Keep these fields accurate: `id`, `lane`, `type`, `title`, `owner`, `status`, `priority`, `files`, `dependencies`, `acceptance_criteria`, `notes_for_next_agent`.
- When work finishes, mark the task `done` and tighten `notes_for_next_agent` for the next human or agent.
- If work is blocked, use `status: blocked` and record the blocker clearly.

### Generate tasks
- Run from repo root: `python ops/generate_tasks.py`
- Preview only: `python ops/generate_tasks.py --dry-run`
- Generation is deterministic and lane-aware. Do not hand-add speculative tasks when the existing templates/state already cover the next step.

### Review tasks
- Run from repo root: `python ops/review_tasks.py`
- Use it before committing task-board edits.
- Treat review failures as real workflow issues, not optional warnings.

## Strict rules
- Do not break `docs/04_api_contracts.md` silently.
- Do not redesign scoring weights, decay, or severity logic unless the task explicitly calls for approved Product work.
- Do not expand MVP scope in code, docs, or task templates.
- Avoid cross-lane edits unless they are necessary for correctness, contract alignment, or a documented handoff.
- Do not rewrite existing work just to change style or structure.

## File ownership guidance
Use these ownership defaults unless a task explicitly spans lanes:
- **product-owned**
  - `docs/00_project_brief.md`
  - `docs/01_mvp_scope.md`
  - `docs/03_scoring_model.md`
  - `docs/04_api_contracts.md` (shared review with App)
  - `docs/handoffs/product.md`
- **data-owned**
  - `docs/05_data_sources_chicago.md`
  - `db/`
  - `backend/ingest/`
  - `backend/models/`
  - `backend/scoring/`
  - `docs/handoffs/data.md`
- **app-owned**
  - `backend/app/`
  - `frontend/`
  - `docs/handoffs/app.md`
- **shared workflow docs**
  - `README.md`
  - `docs/06_team_working_agreement.md`
  - `ops/TASKS.yaml`
  - `ops/task_templates.yaml`
  - `ops/lane_state.yaml`
  - `ops/generate_tasks.py`
  - `ops/review_tasks.py`

## Coding and tooling preferences
- Backend: Python.
- API framework: FastAPI.
- Frontend: Next.js.
- Workflow/config files: YAML.
- Prefer minimal dependencies and straightforward scripts.
- Prefer localized, reviewable changes over broad refactors.

## Definition of Done
A task is done only when all of the following are true:
- The task acceptance criteria are satisfied.
- Any touched source-of-truth docs are updated.
- `ops/TASKS.yaml` is updated with the correct final status and handoff note.
- The change respects MVP scope, scoring boundaries, and API contract rules.
- Relevant checks were run and recorded in the PR or handoff.

## Anti-patterns to avoid
- Overengineering the workflow or adding new meta-systems.
- Creating large vague tasks instead of small actionable ones.
- Breaking contracts silently and expecting downstream lanes to adapt.
- Rewriting existing docs/code/tasks unnecessarily.
- Mixing Product, Data, and App work in one change without a clear reason.

## Practical operating guidance for AI agents
- Start with the task and the lane handoff doc.
- Make the smallest change that completes the task correctly.
- Preserve traceability: update task metadata and leave clear `notes_for_next_agent`.
- If the lane queue is low, generate tasks with the existing workflow instead of inventing ad hoc backlog items.
- If you must touch another lane's artifact, explain why in the task update and keep the edit minimal.
