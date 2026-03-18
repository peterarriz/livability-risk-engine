# Team Working Agreement

## 3-lane structure
- **Product lane**: Defines success criteria, prioritizes scope, validates score output with stakeholders.
- **Data lane**: Owns ingestion pipelines, schema design, data quality checks, and source onboarding.
- **App lane**: Owns API design, backend scaffold, frontend demo, and deployment pipeline.

## Ownership rules
- Each lane owns its artifacts and must review cross-lane changes that affect shared contracts (for example API schema or DB schema).
- Any change to `docs/04_api_contracts.md` requires sign-off from Product + App.
- Any change to canonical schema in the DB must be reviewed by Data + App.
- Do not change the MVP scope or redesign scoring logic through task generation; generated tasks must stay inside the documented MVP.

## Task system: source of truth
- `ops/TASKS.yaml` is the source of truth for lane work. Every task now includes `id`, `lane`, `type`, `title`, `owner`, `status`, `priority`, `files`, `dependencies`, `acceptance_criteria`, and `notes_for_next_agent`.
- Use `status: ready` or `status: in_progress` for actionable work. Use `status: backlog` for queued but not yet actionable work, `status: blocked` when waiting on another lane, and `status: done` when complete.
- `ops/task_templates.yaml` contains the deterministic task templates that can be promoted into the queue.
- `ops/lane_state.yaml` records the ready-queue target, lane focus, and the situations that require lane-state updates.

## How tasks are generated
- Run `python ops/generate_tasks.py` from the repo root.
- The generator reads `ops/TASKS.yaml`, `ops/task_templates.yaml`, and `ops/lane_state.yaml`.
- For each lane, it counts actionable tasks using the statuses listed in `ops/lane_state.yaml`.
- If a lane has fewer actionable tasks than its `ready_queue_target`, the script appends the next template for that lane whose dependencies are already in a dependency-ready status (`ready`, `in_progress`, or `done` by default).
- The generator is deterministic and auditable: it does not invent tasks, it only instantiates prewritten templates in file order.
- Duplicate tasks are skipped by both `id` and per-lane `title`, so rerunning the command is safe.
- Optional review command: run `python ops/review_tasks.py` to validate task shape and detect duplicate IDs or titles.

## When `lane_state` should be updated
- Update `ops/lane_state.yaml` whenever a lane changes focus, becomes blocked, or needs a different ready-queue target.
- Update it when a human lead decides a different task should stay in the short-term queue.
- Update it when another lane dependency materially changes the next-best work for that lane.
- Keep the state lightweight: current focus, blockers, and queue expectations only.

## How humans should use the system
1. Review `ops/TASKS.yaml` before starting work and pick a `ready` task in your lane.
2. When you finish a task, mark it `done`, tighten `notes_for_next_agent`, and update any files or acceptance criteria that changed during the work.
3. If your lane's focus or blockers changed, update `ops/lane_state.yaml` before generating more tasks.
4. If your lane's actionable queue drops below target, run `python ops/generate_tasks.py` from the repo root.
5. Before opening a PR, run `python ops/review_tasks.py` so the task board stays clean and reviewable.

## How AI agents should use the system
- AI agents should treat `ops/TASKS.yaml` as the canonical backlog and must preserve task history instead of rewriting it wholesale.
- When an AI agent completes work, it should update the relevant task entry, refresh `notes_for_next_agent`, and only generate more tasks when the lane queue is low.
- AI agents must keep generation lane-aware: do not add App tasks for Product work, and do not bypass documented dependencies.
- AI agents can draft task templates, but humans should review template additions because templates directly control future generated work.
- Do not rely on agent judgment alone to create new MVP scope; add or edit templates explicitly so changes remain auditable in git.

## Branching strategy
- Branch off `main` for each task: `lane/task-short-description` (for example `data/permit-ingest`).
- Keep branches small and focused; merge to `main` via PR only when passing CI and review.
- Use `main` as the deployable branch; no direct pushes to `main`.

## Pull request expectations
- Title: `[lane] short summary` (for example `[app] implement /score endpoint`).
- Description: What changed, why, how to test, and any manual steps.
- Include a checklist in the PR description for affected lanes.
- Assign at least one reviewer outside of the author's primary lane.

## Handoff requirements
- When a task is complete, update the relevant docs in `/docs` and the matching task entry in `ops/TASKS.yaml`.
- For handoffs between lanes, add or refresh the lane-specific note in `docs/handoffs/` and keep `notes_for_next_agent` current in the task entry.
- If additional ready work is needed after a handoff, run `python ops/generate_tasks.py` and commit the resulting task-board change with the handoff.

## Rules for AI agent usage
- AI agents can generate drafts (code, docs, tests), but humans must review and approve before merging.
- Document AI-produced outputs in PRs if required by team process.
- Do not rely on AI-generated content for security-sensitive logic. Human review is required.
