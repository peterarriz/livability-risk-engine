#!/usr/bin/env python3
"""Shared helpers for the task-ops workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _split_key_value(content: str) -> tuple[str, str]:
    key, value = content.split(":", 1)
    return key.strip(), value.strip()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_mapping(lines: list[str], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        current_indent = _indent_of(line)
        if current_indent < indent or line[current_indent:].startswith("- "):
            break
        key, value = _split_key_value(line[current_indent:])
        index += 1
        if value:
            result[key] = _parse_scalar(value)
            continue
        if index >= len(lines):
            result[key] = ""
            continue
        next_indent = _indent_of(lines[index])
        next_content = lines[index][next_indent:]
        if next_indent < current_indent or (next_indent == current_indent and not next_content.startswith("- ")):
            result[key] = ""
            continue
        child_indent = current_indent if next_content.startswith("- ") else current_indent + 2
        result[key], index = _parse_block(lines, index, child_indent)
    return result, index


def _parse_list_item_mapping(
    lines: list[str], index: int, item_indent: int, first_content: str
) -> tuple[dict[str, Any], int]:
    item: dict[str, Any] = {}
    key, value = _split_key_value(first_content)
    item[key] = _parse_scalar(value) if value else ""
    index += 1
    while index < len(lines):
        line = lines[index]
        current_indent = _indent_of(line)
        if current_indent <= item_indent:
            break
        key, value = _split_key_value(line[current_indent:])
        index += 1
        if value:
            item[key] = _parse_scalar(value)
            continue
        if index >= len(lines):
            item[key] = ""
            continue
        next_indent = _indent_of(lines[index])
        next_content = lines[index][next_indent:]
        if next_indent < current_indent or (next_indent == current_indent and not next_content.startswith("- ")):
            item[key] = ""
            continue
        child_indent = current_indent if next_content.startswith("- ") else current_indent + 2
        item[key], index = _parse_block(lines, index, child_indent)
    return item, index


def _parse_list(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        current_indent = _indent_of(line)
        if current_indent < indent or not line[current_indent:].startswith("- "):
            break
        content = line[current_indent + 2 :]
        if not content:
            index += 1
            value, index = _parse_block(lines, index, current_indent + 2)
            result.append(value)
            continue
        if ":" in content:
            value, index = _parse_list_item_mapping(lines, index, current_indent, content)
            result.append(value)
            continue
        result.append(_parse_scalar(content))
        index += 1
    return result, index


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    if lines[index][_indent_of(lines[index]) :].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def load_yaml(path: Path) -> dict[str, Any]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line.rstrip() for line in raw_lines if line.strip()]
    data, index = _parse_block(lines, 0, 0)
    if index != len(lines):
        raise ValueError(f"Failed to parse all content in {path}")
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    needs_quotes = any(token in text for token in [": ", "#", "[", "]", "{", "}"]) or text.startswith(("-", "?", "@", "!", "&", "*", "%"))
    if text == "":
        return '""'
    if needs_quotes:
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_yaml(item, indent + 2))
            elif item == []:
                lines.append(f"{prefix}{key}: []")
            elif item == {}:
                lines.append(f"{prefix}{key}: {{}}")
            else:
                lines.append(f"{prefix}{key}: {_format_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict) and item:
                first_key = next(iter(item))
                first_value = item[first_key]
                if isinstance(first_value, (dict, list)) and first_value:
                    lines.append(f"{prefix}- {first_key}:")
                    lines.extend(_dump_yaml(first_value, indent + 4))
                elif first_value == []:
                    lines.append(f"{prefix}- {first_key}: []")
                else:
                    lines.append(f"{prefix}- {first_key}: {_format_scalar(first_value)}")
                remaining = {key: value for key, value in item.items() if key != first_key}
                if remaining:
                    lines.extend(_dump_yaml(remaining, indent + 2))
            elif isinstance(item, list) and item:
                lines.append(f"{prefix}-")
                lines.extend(_dump_yaml(item, indent + 2))
            elif item == []:
                lines.append(f"{prefix}- []")
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines
    return [f"{prefix}{_format_scalar(value)}"]


def dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text("\n".join(_dump_yaml(payload)) + "\n", encoding="utf-8")


def normalize_title(title: str) -> str:
    return " ".join(title.split()).strip().lower()
