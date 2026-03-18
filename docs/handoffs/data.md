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

## Review checklist
- Does the task preserve the canonical schema in `docs/04_api_contracts.md`?
- Does it avoid introducing new data sources outside the MVP unless explicitly documented as backlog?
- Is the next step deterministic enough that another agent can rerun or review it?
