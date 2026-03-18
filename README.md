# Livability Risk Engine

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
