# Product Lane Handoff Guide

## Mission
Keep Product work focused on scope clarity, scoring guidance, and demo-readiness without expanding the MVP.

## How Product maintains task flow
1. Update the Product task in `ops/TASKS.yaml` as soon as status or acceptance criteria change.
2. Refresh `notes_for_next_agent` with the next concrete question, decision, or artifact needed.
3. If Product has fewer than three actionable items, run `python ops/generate_tasks.py` from the repo root.
4. If the generated queue is not the right next work, adjust `ops/lane_state.yaml` or `ops/task_templates.yaml` and rerun the generator.

## What to hand off to other lanes
- To **Data**: source priorities, scoring assumptions, and any confidence or explanation requirements that affect schema or ingest logic.
- To **App**: response wording, demo acceptance expectations, and any user-facing explanation constraints.

## Review checklist
- Does the task stay inside the Chicago MVP scope?
- Does it avoid changing the scoring model beyond documenting Product decisions?
- Is the next Product task specific enough for a human or AI agent to execute without guessing?
