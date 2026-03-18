#!/usr/bin/env python3
"""Shared helpers for the task-ops workflow."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    script = (
        'require "yaml"; require "json"; '
        'data = YAML.load_file(ARGV[0], aliases: true); '
        'STDOUT.write(JSON.generate(data))'
    )
    result = subprocess.run(
        ["ruby", "-e", script, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    script = (
        'require "yaml"; require "json"; '
        'data = JSON.parse(File.read(ARGV[0])); '
        'yaml = YAML.dump(data, line_width: -1); '
        'yaml = yaml.sub(/\A---\\s*\n/, ""); '
        'File.write(ARGV[1], yaml)'
    )
    json_payload = json.dumps(payload)
    temp_json_path = path.with_suffix(path.suffix + ".tmp.json")
    temp_json_path.write_text(json_payload, encoding="utf-8")
    try:
        subprocess.run(
            ["ruby", "-e", script, str(temp_json_path), str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        temp_json_path.unlink(missing_ok=True)


def normalize_title(title: str) -> str:
    return " ".join(title.split()).strip().lower()
