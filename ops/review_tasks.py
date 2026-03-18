#!/usr/bin/env python3
"""Validate task board structure and catch duplicate task definitions."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import sys

from task_ops_common import load_yaml, normalize_title

ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "ops" / "TASKS.yaml"
LANE_STATE_PATH = ROOT / "ops" / "lane_state.yaml"
REQUIRED_FIELDS = [
    "id",
    "lane",
    "type",
    "title",
    "owner",
    "status",
    "priority",
    "files",
    "dependencies",
    "acceptance_criteria",
    "notes_for_next_agent",
]
VALID_LANES = {"product", "data", "app"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_STATUSES = {"ready", "in_progress", "blocked", "backlog", "done"}


def main() -> int:
    errors: list[str] = []
    payload = load_yaml(TASKS_PATH)
    lane_state = load_yaml(LANE_STATE_PATH)
    tasks = payload.get("tasks", [])

    if not isinstance(tasks, list):
        errors.append("ops/TASKS.yaml: tasks must be a list")
        tasks = []

    ids = Counter()
    titles = Counter()
    known_ids = set()
    focus_ids = set()
    for lane_details in lane_state.get("lanes", {}).values():
        focus_ids.update(lane_details.get("current_focus", []))

    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            errors.append(f"task #{index}: task entry must be a mapping")
            continue

        for field in REQUIRED_FIELDS:
            if field not in task:
                errors.append(f"task {task.get('id', '#'+str(index))}: missing field '{field}'")

        task_id = task.get("id")
        lane = task.get("lane")
        title = task.get("title")
        known_ids.add(task_id)

        if task_id:
            ids[task_id] += 1
        if lane and title:
            titles[(lane, normalize_title(title))] += 1
        if lane and lane not in VALID_LANES:
            errors.append(f"task {task_id}: invalid lane '{lane}'")
        if task.get("owner") and lane and task["owner"] != lane:
            errors.append(f"task {task_id}: owner '{task['owner']}' should match lane '{lane}'")
        if task.get("status") and task["status"] not in VALID_STATUSES:
            errors.append(f"task {task_id}: invalid status '{task['status']}'")
        if task.get("priority") and task["priority"] not in VALID_PRIORITIES:
            errors.append(f"task {task_id}: invalid priority '{task['priority']}'")
        if not isinstance(task.get("files", []), list):
            errors.append(f"task {task_id}: files must be a list")
        if not isinstance(task.get("dependencies", []), list):
            errors.append(f"task {task_id}: dependencies must be a list")
        if not isinstance(task.get("acceptance_criteria", []), list):
            errors.append(f"task {task_id}: acceptance_criteria must be a list")
        if not isinstance(task.get("notes_for_next_agent", ""), str):
            errors.append(f"task {task_id}: notes_for_next_agent must be a string")

    for task in tasks:
        task_id = task.get("id")
        for dependency in task.get("dependencies", []):
            if dependency not in known_ids:
                errors.append(f"task {task_id}: unknown dependency '{dependency}'")

    for task_id, count in ids.items():
        if count > 1:
            errors.append(f"duplicate task id: {task_id}")
    for (lane, title), count in titles.items():
        if count > 1:
            errors.append(f"duplicate task title in lane '{lane}': {title}")
    for focus_id in sorted(focus_ids):
        if focus_id not in known_ids:
            errors.append(f"lane_state current_focus references unknown task '{focus_id}'")

    if errors:
        print("Task review failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Task review passed for {len(tasks)} task(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
