#!/usr/bin/env python3
"""Generate lane-aware tasks from deterministic YAML templates."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from task_ops_common import dump_yaml, load_yaml, normalize_title

ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "ops" / "TASKS.yaml"
TEMPLATES_PATH = ROOT / "ops" / "task_templates.yaml"
LANE_STATE_PATH = ROOT / "ops" / "lane_state.yaml"


def build_task(template: dict[str, Any], defaults: dict[str, Any], lane: str) -> dict[str, Any]:
    return {
        "id": template["id"],
        "lane": lane,
        "type": template.get("type", defaults.get("type", "chore")),
        "title": template["title"],
        "owner": lane if defaults.get("owner_from_lane", True) else template.get("owner", lane),
        "status": template.get("status", defaults.get("status", "ready")),
        "priority": template.get("priority", defaults.get("priority", "medium")),
        "files": template.get("files", defaults.get("files", [])),
        "dependencies": template.get("dependencies", defaults.get("dependencies", [])),
        "acceptance_criteria": template.get(
            "acceptance_criteria", defaults.get("acceptance_criteria", [])
        ),
        "notes_for_next_agent": template.get(
            "notes_for_next_agent", defaults.get("notes_for_next_agent", "")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing files.")
    args = parser.parse_args()

    tasks_doc = load_yaml(TASKS_PATH)
    templates_doc = load_yaml(TEMPLATES_PATH)
    lane_state_doc = load_yaml(LANE_STATE_PATH)

    tasks = tasks_doc.setdefault("tasks", [])
    defaults = templates_doc.get("defaults", {})
    actionable_statuses = set(lane_state_doc.get("settings", {}).get("actionable_statuses", ["ready", "in_progress"]))
    dependency_ready_statuses = set(
        lane_state_doc.get("settings", {}).get("dependency_ready_statuses", ["ready", "in_progress", "done"])
    )

    existing_ids = {task["id"] for task in tasks}
    existing_titles = {normalize_title(task["title"]) for task in tasks}
    task_status_by_id = {task["id"]: task.get("status") for task in tasks}
    generated: list[dict[str, Any]] = []

    for lane, lane_config in templates_doc.get("lanes", {}).items():
        lane_state = lane_state_doc.get("lanes", {}).get(lane, {})
        ready_target = lane_state.get("ready_queue_target", lane_config.get("ready_queue_target", 0))
        ready_count = sum(
            1
            for task in tasks
            if task.get("lane") == lane and task.get("status") in actionable_statuses
        )

        for template in lane_config.get("templates", []):
            if ready_count >= ready_target:
                break

            task_id = template["id"]
            title_key = normalize_title(template["title"])
            dependencies = template.get("dependencies", defaults.get("dependencies", []))

            if task_id in existing_ids or title_key in existing_titles:
                continue
            if not all(task_status_by_id.get(dep) in dependency_ready_statuses for dep in dependencies):
                continue

            task = build_task(template, defaults, lane)
            tasks.append(task)
            generated.append(task)
            existing_ids.add(task_id)
            existing_titles.add(title_key)
            task_status_by_id[task_id] = task["status"]
            if task["status"] in actionable_statuses:
                ready_count += 1

    if args.dry_run:
        print(f"Would add {len(generated)} task(s).")
    else:
        if generated:
            dump_yaml(TASKS_PATH, tasks_doc)
        print(f"Added {len(generated)} task(s).")

    for task in generated:
        print(f"- {task['lane']}: {task['id']} - {task['title']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
