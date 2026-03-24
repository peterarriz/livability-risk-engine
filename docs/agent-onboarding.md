# Agent Onboarding — Livability Risk Engine
**Last updated:** 2026-03-24

This document is for any Claude agent (or partner agent) picking up work on the `peterarriz/livability-risk-engine` repository. Read this before touching any files.

---

## Repository Overview

| Layer | Technology | Location |
|---|---|---|
| Backend API | FastAPI (Python) | `backend/` |
| Frontend | Next.js (TypeScript) | `frontend/` |
| Database | Postgres on Railway (no PostGIS — haversine queries) | Railway |
| Deployed | Vercel (frontend), Railway (backend) | — |

---

## Agent Lane: Data Only

You are scoped to the **data lane** only. This means:

**Work on:** database, ingest pipelines, scoring engine, API endpoints, data models, `/score` endpoint.

**Do not touch:** `frontend/src/components/`, any `.tsx` or `.css` files, UI layout, or styling — unless you are changing an API response shape that the frontend consumes.

---

## Task File Structure (Critical — Read This First)

As of 2026-03-24, the task registry has been split into two files to reduce token overhead:

### `TASKS.yaml` — Your Working File
- Contains **backlog and in-progress tasks only**
- Read this at the start of every session to find what to work on
- ~109 lines. Fast to read.
- The `notes_for_next_agent` field on each task gives you the context you need to pick up where the last agent left off

### `TASKS_ARCHIVE.yaml` — Completed Work
- Contains all **done tasks** (data-001 through data-057+)
- **Do not read this file** unless you are debugging a regression or need to understand how a specific past feature was implemented
- ~400 lines of historical context that is not needed for new work

### Why This Split Exists
Prior to 2026-03-24, all tasks (active and completed) lived in a single `TASKS.yaml` file that had grown to ~18,000 tokens. Every agent session was loading the full history unnecessarily. The split reduces per-session token overhead by ~90%.

---

## How to Pick Up a Task

1. Read `TASKS.yaml` — find the highest-priority `backlog` task
2. Create a GitHub issue before starting: format `[data-NNN] Short description`, @claude in the body
3. Update the task status to `in-progress` in `TASKS.yaml`
4. Create a new branch: `claude/<short-description>-<id>`
5. Do the work
6. Before closing: populate `notes_for_next_agent` in `TASKS.yaml`, create the next GitHub issue, add the next task to `TASKS.yaml`
7. Open a PR titled `[data-NNN] description` and push

---

## Key Files Reference

| File | Purpose |
|---|---|
| `TASKS.yaml` | Active task registry — read every session |
| `TASKS_ARCHIVE.yaml` | Completed tasks — read only for regression debugging |
| `CLAUDE.md` | Project instructions — always read at session start |
| `db/schema.sql` | Postgres schema — idempotent, safe to re-apply |
| `backend/app/main.py` | FastAPI app, all endpoints |
| `backend/scoring/query.py` | Scoring engine — haversine radius query, compute_score() |
| `backend/models/project.py` | Project dataclass and all normalizers |
| `backend/ingest/load_projects.py` | DB loader — upserts normalized records |
| `run_pipeline.py` | Pipeline orchestrator — runs all ingest steps |
| `scripts/apply_schema.sh` | Applies db/schema.sql to Railway (idempotent) |
| `.github/workflows/ingest.yml` | Daily ingest cron (06:00 UTC) |

---

## Live Infrastructure

| Service | URL / Location |
|---|---|
| Railway backend | `https://livability-risk-engine-production-2bad.up.railway.app` |
| Vercel frontend | `https://livability-risk-engine.vercel.app` |
| DATABASE_URL | GitHub secret — injected at runtime |
| ANTHROPIC_API_KEY | Railway env var — powers signal card rewriter |

---

## What Not to Do

- Do not read `TASKS_ARCHIVE.yaml` on every session — only when debugging
- Do not work on `app-` or `product-` lane tasks
- Do not touch the map view (task `app-007`, intentionally backlog)
- Do not modify frontend UI components
- Do not push to `main` directly — always open a PR
