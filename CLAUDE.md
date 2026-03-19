## Project: Livability Risk Engine — Chicago MVP

### Stack
- Backend: FastAPI (Python), lives in backend/
- Frontend: Next.js (TypeScript), lives in frontend/
- Database: Postgres + PostGIS (not yet live)
- Deployed: Vercel (frontend), backend not yet hosted

### Your Lane: Data Only
- Only work on data-related tasks: database, ingest pipelines, scoring engine, API endpoints, data models, and connecting the data layer to the frontend via the /score endpoint
- Do NOT touch frontend components, UI, styling, or layout
- Do NOT modify frontend/src/components/ or any .tsx/.css files unless connecting an API response shape

### Task Naming Convention
Continue from where we left off. Last completed tasks:
- data-013 (DB loader) — DONE
- app-008 (live scoring wired to /score) — DONE
- Next data task should be data-014

### Autonomous Task Creation
- Proactively identify new data-related tasks
- Create a GitHub issue for each new task before executing it
- Use the format: [data-NNN] Short description
- Add each task to TASKS.yaml with status, priority, and notes_for_next_agent
- After completing each data task via GitHub Actions, before finishing, always create the next GitHub issue using the [data-NNN] naming convention with a description and @claude in the body, and add the task to TASKS.yaml

### Current Priority: Go Live
The data pipeline is built but the database is not running. Priority tasks:
1. Audit what's needed to connect to a live Postgres+PostGIS instance
2. Plan and document the database hosting options (Railway, Supabase, Render, etc.)
3. Once DB is live: run ingest pipeline, validate /score returns real data, remove demo fallback from backend/app/main.py and frontend/src/lib/api.ts

### Documentation Rules
- Every change must reference a TASKS.yaml task ID
- Every PR title must follow the format: [data-NNN] description
- Always populate notes_for_next_agent in TASKS.yaml before closing a task
- Create a new branch per task

### What NOT to do
- Do not work on app lane or product lane tasks
- Do not touch the map view (app-007, intentionally backlog)
- Do not modify frontend UI components
