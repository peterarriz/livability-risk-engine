# Product Lane Handoff Guide

## Mission
Keep Product work focused on scope clarity, scoring guidance, and demo-readiness without expanding the MVP.

## Completed in this handoff
- Tightened the MVP `/score` response contract to a minimal demo-ready shape.
- Added deterministic explanation generation rules for plain-English output.
- Added a grouped set of 18 plausible Chicago QA/demo addresses.

## Still open
- Finalize scoring-weight guidance for v1 so severity and headline score thresholds are easier to defend.
- Review the explanation copy across the QA addresses to catch awkward or repetitive phrasing.
- Freeze the final severity label rules for noise, traffic, and dust before broader App/Data integration.

## Next 3 product actions
1. Review explanation copy against the 18 QA addresses and note any implausible cases.
2. Freeze severity label rules so App and backend can render them without interpretation.
3. Approve one final mocked example response for demo reviewers and smoke tests.

## What to hand off to other lanes
- To **Data**: keep the dominant-signal framing aligned with the minimal response fields and severity categories.
- To **App**: implement only the fields in the tightened contract and keep explanation/top-risk rendering simple.

## Review checklist
- Does the task stay inside the Chicago MVP scope?
- Does it avoid changing the scoring model beyond documenting Product decisions?
- Is the next Product task specific enough for a human or AI agent to execute without guessing?
