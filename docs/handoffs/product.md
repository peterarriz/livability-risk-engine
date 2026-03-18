# Product Lane Handoff Guide

## Mission
Keep Product work focused on scope clarity, scoring guidance, and demo-readiness without expanding the MVP.

## Completed in this handoff
- Added score interpretation bands so the 0–100 output has practical user-facing meaning.
- Added confidence language guidance, including evidence-quality drivers and API label mapping.
- Added a fixed MVP disruption taxonomy and clarified how the narrower API severity fields map to it.
- Added scoring assumptions v1 so Product, Data, and App can distinguish heuristics from known source facts.
- Added a concrete v1 weighting rubric covering base project weights, distance decay, time weighting, aggregation, and severity-alignment guardrails.
- Added explicit score-band threshold guidance and dominant-signal tie-break rules so Data and App can explain outputs consistently.
- Decided that buyer-facing `traffic` language should explicitly include curb and parking access when those impacts are materially part of the story.
- Added a Product QA checklist for trust, calibration, explanation tone, and category consistency reviews.
- Clarified the API contract so `disruption_score`, `confidence`, and `severity` are more interpretable without changing the response shape.

## Still open
- Review explanation copy across the QA addresses to confirm tone matches the documented score bands.

## Next 3 product actions
1. Review the 18 QA addresses against the new QA checklist and record any score-band or explanation-tone mismatches.
2. Approve one final mocked example response whose score band, confidence, severity, top risks, and explanation all align.
3. Convert the wording decision into one or more approved buyer-facing example responses that App can mirror in demos.

## What to hand off to other lanes
- To **Data**: keep the dominant-signal framing aligned with the score-band interpretation, confidence drivers, and severity mapping notes.
- To **App**: preserve the minimal response shape, but render score/confidence as user-facing trust signals rather than raw technical fields.

## Review checklist
- Does the task stay inside the Chicago MVP scope?
- Does it avoid changing the scoring model beyond documenting Product decisions?
- Is the next Product task specific enough for a human or AI agent to execute without guessing?
