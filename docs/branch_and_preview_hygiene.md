# Branch and Preview Hygiene

Keep this workflow short and predictable so demo links, preview deployments, and git branches do not get confused.

## Demo-safe branch
- Treat `main` as the only demo-safe branch.
- Anything shared with stakeholders or used in a live walkthrough should come from `main`, not from a short-lived task branch.
- If a preview deployment must be shown externally, confirm it was built from a branch that is already approved to merge or is a direct mirror of `main`.

## Short-lived agent branches
- Create one focused branch per task.
- Delete the branch after the PR is merged or explicitly abandoned.
- Do not keep old agent branches around once a newer branch or merged PR supersedes them; stale branches make it harder to know which preview is current.

## How preview deployments should be used
- Use preview deployments for internal review, QA, and handoff verification.
- Use them to confirm that `/health`, `/score`, frontend mode labels, and deploy/readiness checks behave as expected before merge.
- Do not treat a preview as the canonical demo environment unless the team has explicitly decided to demo that preview.

## Avoiding GitHub branch vs preview confusion
- A GitHub branch name is not the same thing as the active Vercel preview someone is looking at.
- When sharing a preview, always include:
  - the branch name,
  - the commit SHA,
  - and whether the preview is intended for internal review or stakeholder demo use.
- When a newer preview replaces an older one, say so explicitly in the PR or handoff note.
- Before any demo, verify that the open URL matches the intended branch and commit, not just a similarly named preview from earlier work.
