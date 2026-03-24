## Project: Livability Risk Engine — Chicago MVP

### Stack
- Backend: FastAPI (Python) — `backend/`
- Frontend: Next.js (TypeScript) — `frontend/`
- Database: Postgres on Railway (live, no PostGIS — uses haversine queries)
- Deployed: Vercel (frontend), Railway (backend)

### Your Lane: Data Only
- Only work on: database, ingest pipelines, scoring engine, API endpoints, data models, `/score` endpoint
- Do NOT touch: frontend components, UI, styling, layout, `frontend/src/components/`, any `.tsx/.css` files (unless changing an API response shape)

### Task Registry
- Active and backlog tasks: **TASKS.yaml** (read this to find what to work on)
- Completed tasks: **TASKS_ARCHIVE.yaml** (do NOT read unless debugging a regression)
- Next task ID to create: check the highest `id` in TASKS.yaml and increment

### Autonomous Task Creation
- Create a GitHub issue before executing each new task
- Use the format: `[data-NNN] Short description`, @claude in the body
- Add each task to TASKS.yaml with status, priority, and notes_for_next_agent
- After completing a task, create the next GitHub issue and add it to TASKS.yaml before closing

### Documentation Rules
- Every change must reference a TASKS.yaml task ID
- Every PR title: `[data-NNN] description`
- Always populate `notes_for_next_agent` before closing a task
- Create a new branch per task

### What NOT to do
- Do not work on app lane or product lane tasks
- Do not touch the map view (app-007, intentionally backlog)
- Do not modify frontend UI components
