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
