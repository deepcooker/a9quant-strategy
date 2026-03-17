#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.project_config import load_project_config_json, save_project_config_json, update_runtime_state
except Exception:  # pragma: no cover
    from project_config import load_project_config_json, save_project_config_json, update_runtime_state  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "TASKS"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_repo_path(raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip())
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def get_task_registry() -> dict[str, Any]:
    config = load_project_config_json()
    return dict(config.get("task_registry", {}) or {})


def get_runtime_state() -> dict[str, Any]:
    config = load_project_config_json()
    return dict(config.get("runtime_state", {}) or {})


def get_queue_path() -> Path:
    registry = get_task_registry()
    raw_path = str(registry.get("queue_json_file", "TASKS/QUEUE.json")).strip()
    return _resolve_repo_path(raw_path)


def load_queue() -> dict[str, Any]:
    return _read_json(get_queue_path())


def save_queue(payload: dict[str, Any]) -> None:
    path = get_queue_path()
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_status(value: str, default: str = "pending") -> str:
    raw = str(value).strip().lower()
    if raw in {"completed", "complete", "done", "closed"}:
        return "completed"
    if raw in {"active", "in_progress", "in-progress", "working"}:
        return "active"
    if raw in {"draft", "pending", "open", ""}:
        return default
    return raw


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value).strip().lower()).strip("-")
    return text or "task"


def load_task(task_json_file: str) -> dict[str, Any]:
    return _read_json(_resolve_repo_path(task_json_file))


def save_task(task_json_file: str, payload: dict[str, Any]) -> None:
    path = _resolve_repo_path(task_json_file)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_active_task_path() -> Path:
    runtime_state = get_runtime_state()
    task_json_file = str(runtime_state.get("current_task_json_file", "")).strip()
    if task_json_file:
        return _resolve_repo_path(task_json_file)
    registry = get_task_registry()
    fallback = str(registry.get("active_task_json_file", "")).strip()
    if not fallback:
        raise FileNotFoundError("active task json file is not configured")
    return _resolve_repo_path(fallback)


def load_active_task() -> dict[str, Any]:
    return _read_json(get_active_task_path())


def set_active_task(task_json_file: str, task_id: str, task_md_file: str, run_id: str, status: str = "active") -> None:
    config = load_project_config_json()
    task_registry = config.setdefault("task_registry", {})
    task_registry["active_task_json_file"] = task_json_file
    save_project_config_json(config)
    required = dict(config.get("required", {}) or {})
    project_id = str(required.get("project_id", config.get("project_id", ""))).strip()
    update_runtime_state(project_id, run_id, task_md_file, status, task_id, task_json_file)


def find_queue_item_by_run_id(run_id: str) -> dict[str, Any] | None:
    for item in list(load_queue().get("items", []) or []):
        if str(item.get("run_id", "")).strip() == run_id:
            return dict(item)
    return None


def find_next_open_queue_item() -> dict[str, Any] | None:
    for item in list(load_queue().get("items", []) or []):
        status = str(item.get("status", "")).strip().lower()
        if status in {"pending", "open", ""}:
            return dict(item)
    return None


def mark_queue_item_status(queue_id: str, status: str, picked_at: str | None = None) -> dict[str, Any]:
    queue_payload = load_queue()
    for item in list(queue_payload.get("items", []) or []):
        if str(item.get("queue_id", "")).strip() != queue_id:
            continue
        item["status"] = status
        item["picked_at"] = picked_at
        save_queue(queue_payload)
        return dict(item)
    raise KeyError(f"queue_id not found: {queue_id}")


def reconcile_task_queue_truth() -> dict[str, Any]:
    runtime_state = get_runtime_state()
    active_task_json_file = str(runtime_state.get("current_task_json_file", "")).strip()
    active_task_id = str(runtime_state.get("current_task_id", "")).strip()
    active_run_id = str(runtime_state.get("current_run_id", "")).strip()
    normalized_tasks: list[str] = []
    completed_tasks: list[str] = []
    pending_tasks: list[str] = []

    for path in sorted(TASKS_DIR.glob("TASK-*.json")):
        task_json_file = str(path.relative_to(REPO_ROOT))
        payload = load_task(task_json_file)
        task_id = str(payload.get("task_id", "")).strip()
        top_status = normalize_status(str(payload.get("status", "")).strip(), "pending")
        summary_status = normalize_status(str((payload.get("task_summary", {}) or {}).get("status", "")).strip(), "")

        next_status = top_status
        if summary_status == "completed":
            next_status = "completed"
        elif task_json_file == active_task_json_file or task_id == active_task_id:
            next_status = "active"
        elif top_status == "active":
            next_status = "pending"

        if next_status != str(payload.get("status", "")).strip():
            payload["status"] = next_status
            payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            save_task(task_json_file, payload)
            write_task_md(str(payload.get("artifacts", {}).get("task_md_file", "")).strip() or task_json_file.replace(".json", ".md"), payload)
            normalized_tasks.append(task_id or task_json_file)

        if next_status == "completed":
            completed_tasks.append(task_id or task_json_file)
        elif next_status == "pending":
            pending_tasks.append(task_id or task_json_file)

    queue_payload = load_queue()
    normalized_queue_items: list[str] = []
    for item in list(queue_payload.get("items", []) or []):
        queue_id = str(item.get("queue_id", "")).strip()
        task_json_file = str(item.get("task_json_file", "")).strip()
        task_id = str(item.get("task_id", "")).strip()
        task_status = "pending"
        if task_json_file:
            task_status = normalize_status(str(load_task(task_json_file).get("status", "")).strip(), "pending")

        next_queue_status = normalize_status(str(item.get("status", "")).strip(), "pending")
        if task_json_file == active_task_json_file or task_id == active_task_id:
            next_queue_status = "active"
        elif task_status == "completed":
            next_queue_status = "completed"
        else:
            next_queue_status = "pending"

        if next_queue_status != str(item.get("status", "")).strip():
            item["status"] = next_queue_status
            normalized_queue_items.append(queue_id or task_id or task_json_file)
        if next_queue_status != "active":
            item["picked_at"] = item.get("picked_at")
    save_queue(queue_payload)

    if active_task_json_file and active_task_id and active_run_id:
        active_task = load_task(active_task_json_file)
        active_task_md_file = str(active_task.get("artifacts", {}).get("task_md_file", "")).strip() or active_task_json_file.replace(".json", ".md")
        set_active_task(
            active_task_json_file,
            active_task_id,
            active_task_md_file,
            active_run_id,
            normalize_status(str(active_task.get("status", "")).strip(), "active"),
        )

    return {
        "action": "reconcile_task_queue_truth",
        "active_task_id": active_task_id,
        "active_task_json_file": active_task_json_file,
        "normalized_tasks": normalized_tasks,
        "normalized_queue_items": normalized_queue_items,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
    }


def append_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    queue_payload = load_queue()
    items = list(queue_payload.get("items", []) or [])
    queue_id = str(item.get("queue_id", "")).strip()
    if queue_id and any(str(existing.get("queue_id", "")).strip() == queue_id for existing in items):
        raise ValueError(f"queue_id already exists: {queue_id}")
    items.append(item)
    queue_payload["items"] = items
    save_queue(queue_payload)
    return item


def task_paths_for_slug(slug: str) -> tuple[str, str]:
    task_json_file = f"TASKS/TASK-{slug}.json"
    task_md_file = f"TASKS/TASK-{slug}.md"
    return task_json_file, task_md_file


def find_task_id_for_run(run_id: str) -> str:
    runtime_state = get_runtime_state()
    if str(runtime_state.get("current_run_id", "")).strip() == run_id:
        current_task_id = str(runtime_state.get("current_task_id", "")).strip()
        if current_task_id:
            return current_task_id
        current_task_json_file = str(runtime_state.get("current_task_json_file", "")).strip()
        if current_task_json_file:
            return str(load_task(current_task_json_file).get("task_id", "")).strip()
    queue_item = find_queue_item_by_run_id(run_id)
    if queue_item:
        task_id = str(queue_item.get("task_id", "")).strip()
        if task_id:
            return task_id
        task_json_file = str(queue_item.get("task_json_file", "")).strip()
        if task_json_file:
            return str(load_task(task_json_file).get("task_id", "")).strip()
    return ""


def pick_next() -> dict[str, Any]:
    item = find_next_open_queue_item()
    if not item:
        raise RuntimeError("no open queue item found in TASKS/QUEUE.json")
    queue_id = str(item.get("queue_id", "")).strip()
    task_id = str(item.get("task_id", "")).strip()
    task_json_file = str(item.get("task_json_file", "")).strip()
    task_md_file = str(item.get("task_md_file", "")).strip()
    run_id = str(item.get("run_id", "")).strip()
    if not task_id or not task_json_file or not task_md_file or not run_id:
        raise RuntimeError(f"queue item is incomplete: {queue_id or '(missing queue_id)'}")
    picked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated_item = mark_queue_item_status(queue_id, "active", picked_at)
    set_active_task(task_json_file, task_id, task_md_file, run_id, "active")
    return {
        "action": "next",
        "queue_id": queue_id,
        "task_id": task_id,
        "task_json_file": task_json_file,
        "task_md_file": task_md_file,
        "run_id": run_id,
        "queue_status": str(updated_item.get("status", "")).strip(),
        "picked_at": str(updated_item.get("picked_at", "")).strip(),
    }


def write_task_md(task_md_file: str, payload: dict[str, Any]) -> None:
    path = Path(task_md_file)
    task_summary = dict(payload.get("task_summary", {}) or {})
    role_threads = dict(payload.get("role_threads", {}) or {})
    role_summaries = dict(payload.get("role_summaries", {}) or {})
    test_gate = dict(payload.get("test_gate", {}) or {})
    lines = [
        f"# TASK: {payload.get('title', '')}",
        "",
        f"RUN_ID: {payload.get('run_id', '')}",
        f"TASK_ID: {payload.get('task_id', '')}",
        f"PROJECT_ID: {payload.get('project_id', '')}",
        f"STATUS: {payload.get('status', '')}",
        f"PRIORITY: {payload.get('priority', '')}",
        "",
        "## Goal",
        str(payload.get("goal", "")).strip(),
        "",
        "## Scope",
    ]
    for item in list(payload.get("scope", []) or []):
        lines.append(f"- `{str(item).strip()}`")
    lines.extend(["", "## Non-goals"])
    for item in list(payload.get("non_goals", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.extend(["", "## Acceptance"])
    for item in list(payload.get("acceptance", []) or []):
        status = "x" if normalize_status(str(item.get("status", "")).strip(), "") == "completed" else " "
        lines.append(f"- [{status}] {str(item.get('text', '')).strip()}")
    lines.extend(["", "## Inputs"])
    for item in list(payload.get("inputs", []) or []):
        lines.append(f"- `{str(item).strip()}`")
    lines.extend(["", "## Role Threads"])
    for role in ["run-main", "dev", "test", "arch"]:
        record = dict(role_threads.get(role, {}) or {})
        lines.append(
            f"- `{role}`: status={str(record.get('status', '')).strip() or 'planned'}, "
            f"thread_id={str(record.get('thread_id', '')).strip() or '(none)'}"
        )
    lines.extend(["", "## Test Gate"])
    lines.append(f"- Status: {str(test_gate.get('status', '')).strip() or 'pending'}")
    lines.append(f"- Owner role: {str(test_gate.get('owner_role', '')).strip() or 'test'}")
    lines.append("")
    lines.append("### Required Axes")
    for item in list(test_gate.get("required_axes", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Evidence")
    for item in list(test_gate.get("evidence", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Blocking Issues")
    for item in list(test_gate.get("blocking_issues", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.extend(["", "## Role Summaries"])
    for role in ["run-main", "dev", "test", "arch"]:
        record = dict(role_summaries.get(role, {}) or {})
        lines.append(
            f"- `{role}`: status={str(record.get('status', '')).strip() or 'planned'}, "
            f"thread_id={str(record.get('thread_id', '')).strip() or '(none)'}"
        )
        summary_text = str(record.get("summary_text", "")).strip()
        if summary_text:
            lines.append(f"  summary: {summary_text}")
    lines.extend(["", "## Task Summary"])
    lines.append(f"- Status: {str(task_summary.get('status', '')).strip() or 'draft'}")
    lines.append("")
    lines.append("### Key Updates")
    for item in list(task_summary.get("key_updates", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Decisions")
    for item in list(task_summary.get("decisions", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Risks")
    for item in list(task_summary.get("risks", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Verification")
    for item in list(task_summary.get("verification", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    lines.append("### Next Steps")
    for item in list(task_summary.get("next_steps", []) or []):
        lines.append(f"- {str(item).strip()}")
    lines.append("")
    conflict_policy = dict(task_summary.get("conflict_policy", {}) or {})
    gap_summary = dict(task_summary.get("gap_summary", {}) or {})
    lines.append("### Conflict Policy")
    lines.append(f"- Priority order: {', '.join(list(conflict_policy.get('priority_order', []) or []))}")
    lines.append(f"- Merge rule: {str(conflict_policy.get('merge_rule', '')).strip()}")
    lines.append(f"- Escalation rule: {str(conflict_policy.get('escalation_rule', '')).strip()}")
    lines.append("")
    lines.append("### Gap Summary")
    for item in list(gap_summary.get("missing_roles", []) or []):
        lines.append(f"- missing_role: {str(item).strip()}")
    for item in list(gap_summary.get("open_gaps", []) or []):
        lines.append(f"- gap: {str(item).strip()}")
    lines.append("")
    escalation_policy = dict(task_summary.get("escalation_policy", {}) or {})
    escalation_summary = dict(task_summary.get("escalation_summary", {}) or {})
    run_main_resolution_policy = dict(task_summary.get("run_main_resolution_policy", {}) or {})
    run_main_resolution = dict(task_summary.get("run_main_resolution", {}) or {})
    lines.append("### Escalation Policy")
    for item in list(escalation_policy.get("must_escalate_if", []) or []):
        lines.append(f"- must_escalate_if: {str(item).strip()}")
    for item in list(escalation_policy.get("can_resolve_in_task_if", []) or []):
        lines.append(f"- can_resolve_in_task_if: {str(item).strip()}")
    lines.append("")
    lines.append("### Escalation Summary")
    lines.append(f"- needs_run_main: {str(escalation_summary.get('needs_run_main', False)).lower()}")
    for item in list(escalation_summary.get("reasons", []) or []):
        lines.append(f"- reason: {str(item).strip()}")
    lines.append("")
    lines.append("### Run-Main Resolution Policy")
    for item in list(run_main_resolution_policy.get("must_confirm_if", []) or []):
        lines.append(f"- must_confirm_if: {str(item).strip()}")
    for item in list(run_main_resolution_policy.get("can_close_if", []) or []):
        lines.append(f"- can_close_if: {str(item).strip()}")
    lines.append("")
    lines.append("### Run-Main Resolution")
    lines.append(f"- status: {str(run_main_resolution.get('status', '')).strip() or 'pending_ack'}")
    lines.append(f"- close_escalation: {str(run_main_resolution.get('close_escalation', False)).lower()}")
    for item in list(run_main_resolution.get("notes", []) or []):
        lines.append(f"- note: {str(item).strip()}")
    lines.append("")
    lines.append("### Role Summary Evidence")
    for item in list(task_summary.get("role_summary_evidence", []) or []):
        lines.append(f"- `{str(item).strip()}`")
    lines.append("")
    lines.append("### Source Threads")
    for item in list(task_summary.get("source_threads", []) or []):
        lines.append(f"- `{str(item).strip()}`")
    lines.extend(
        [
            "",
            "## Risks / Rollback",
            f"- Risks: {str(payload.get('risks', '')).strip()}",
            f"- Rollback plan: {str(payload.get('rollback_plan', '')).strip()}",
        ]
    )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def normalize_list(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        for part in raw.split(","):
            value = str(part).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
    return result


def validate_create_task_args(title: str, goal: str, scope: list[str], run_id: str, priority: str) -> None:
    if not title.strip():
        raise ValueError("title is required")
    if not goal.strip():
        raise ValueError("goal is required")
    if not normalize_list(scope):
        raise ValueError("at least one scope item is required")
    if not run_id.strip().startswith("run-"):
        raise ValueError("run_id must start with 'run-'")
    if priority.strip() not in {"P0", "P1", "P2", "P3"}:
        raise ValueError("priority must be one of: P0, P1, P2, P3")


def default_run_id(raw_run_id: str | None) -> str:
    candidate = str(raw_run_id or "").strip()
    if candidate:
        return candidate
    runtime_state = get_runtime_state()
    return str(runtime_state.get("current_run_id", "")).strip()


def default_role_threads() -> dict[str, dict[str, str]]:
    return {
        "run-main": {"thread_id": "", "thread_path": "", "status": "planned"},
        "dev": {"thread_id": "", "thread_path": "", "status": "planned"},
        "test": {"thread_id": "", "thread_path": "", "status": "planned"},
        "arch": {"thread_id": "", "thread_path": "", "status": "optional"},
    }


def default_role_summaries() -> dict[str, dict[str, str]]:
    return {
        "run-main": {"status": "planned", "thread_id": "", "thread_path": "", "summary_text": "", "summary_turn_id": "", "updated_at": ""},
        "dev": {"status": "planned", "thread_id": "", "thread_path": "", "summary_text": "", "summary_turn_id": "", "updated_at": ""},
        "test": {"status": "planned", "thread_id": "", "thread_path": "", "summary_text": "", "summary_turn_id": "", "updated_at": ""},
        "arch": {"status": "optional", "thread_id": "", "thread_path": "", "summary_text": "", "summary_turn_id": "", "updated_at": ""},
    }


def default_test_gate() -> dict[str, Any]:
    return {
        "status": "pending",
        "owner_role": "test",
        "required_axes": ["functional", "flow", "data", "non_functional"],
        "evidence": [],
        "blocking_issues": [],
        "updated_at": "",
    }


def create_task(
    title: str,
    goal: str,
    scope: list[str],
    run_id: str,
    queue: bool,
    activate: bool,
    priority: str,
    non_goals: list[str],
    inputs: list[str],
    acceptance_texts: list[str],
    risks: str,
    rollback_plan: str,
) -> dict[str, Any]:
    validate_create_task_args(title, goal, scope, run_id, priority)
    slug = slugify(title)
    task_id = f"task-{slug}"
    task_json_file, task_md_file = task_paths_for_slug(slug)
    if Path(task_json_file).exists() or Path(task_md_file).exists():
        raise FileExistsError(f"task already exists for slug: {slug}")
    acceptance_payload = [
        {"id": f"check-{idx+1}", "text": text, "status": "pending"}
        for idx, text in enumerate(normalize_list(acceptance_texts))
    ]
    if not acceptance_payload:
        acceptance_payload = [
            {"id": "verify", "text": "Command(s) pass: make verify", "status": "pending"},
            {"id": "evidence", "text": "reports/{RUN_ID}/summary.md and reports/{RUN_ID}/decision.md updated", "status": "pending"},
        ]
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "project_id": "quant-factory-os",
        "status": "active",
        "priority": priority,
        "title": title.strip(),
        "goal": goal.strip(),
        "scope": normalize_list(scope),
        "non_goals": normalize_list(non_goals),
        "acceptance": acceptance_payload,
        "inputs": normalize_list(inputs),
        "artifacts": {
            "task_md_file": task_md_file,
            "summary_file": f"reports/{run_id}/summary.md",
            "decision_file": f"reports/{run_id}/decision.md",
        },
        "task_summary": {
            "status": "draft",
            "key_updates": [],
            "decisions": [],
            "risks": [],
            "verification": [],
            "next_steps": [],
            "conflict_policy": {
                "priority_order": ["run-main", "test", "arch", "dev"],
                "merge_rule": "append_dedup",
                "escalation_rule": "if conflict remains, escalate to run-main",
            },
            "gap_summary": {"missing_roles": [], "open_gaps": [], "updated_at": ""},
            "escalation_policy": {
                "must_escalate_if": [
                    "run-main summary missing",
                    "test_gate not passed",
                    "blocking issue remains",
                ],
                "can_resolve_in_task_if": [
                    "only dev/arch detail alignment",
                    "no blocking issue",
                    "test gate already passed",
                ],
            },
            "escalation_summary": {"needs_run_main": False, "reasons": [], "updated_at": ""},
            "run_main_resolution_policy": {
                "must_confirm_if": ["escalation_summary.needs_run_main"],
                "can_close_if": [
                    "run-main summary exists",
                    "test_gate passed",
                    "no blocking issue remains",
                ],
            },
            "run_main_resolution": {
                "status": "pending_ack",
                "close_escalation": False,
                "notes": [],
                "updated_at": "",
            },
            "role_summary_evidence": [],
            "source_threads": [],
            "updated_at": "",
        },
        "role_threads": default_role_threads(),
        "role_summaries": default_role_summaries(),
        "test_gate": default_test_gate(),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "risks": risks.strip(),
        "rollback_plan": rollback_plan.strip(),
    }
    save_task(task_json_file, payload)
    write_task_md(task_md_file, payload)
    result: dict[str, Any] = {
        "action": "create",
        "task_id": task_id,
        "task_json_file": task_json_file,
        "task_md_file": task_md_file,
        "run_id": run_id,
    }
    if queue:
        queue_item = {
            "queue_id": f"queue-{slug}",
            "title": title,
            "run_id": run_id,
            "task_id": task_id,
            "task_json_file": task_json_file,
            "task_md_file": task_md_file,
            "status": "pending",
            "picked_at": None,
            "goal": payload["goal"],
            "scope": list(payload["scope"]),
            "acceptance": list(payload["acceptance"]),
        }
        append_queue_item(queue_item)
        result["queue_id"] = queue_item["queue_id"]
    if activate:
        set_active_task(task_json_file, task_id, task_md_file, run_id, "active")
        result["activated"] = True
    return result


def resolve_task_file_arg(task_json_file: str | None) -> str:
    candidate = str(task_json_file or "").strip()
    if candidate:
        return candidate
    return str(get_active_task_path().relative_to(REPO_ROOT)).strip()


def update_task_summary(
    task_json_file: str | None,
    status: str,
    key_updates: list[str],
    decisions: list[str],
    risks: list[str],
    verification: list[str],
    next_steps: list[str],
    role_summary_evidence: list[str],
    source_threads: list[str],
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    summary = dict(payload.get("task_summary", {}) or {})
    summary["status"] = str(status).strip() or str(summary.get("status", "")).strip() or "draft"
    summary["key_updates"] = normalize_list(key_updates) if key_updates else list(summary.get("key_updates", []) or [])
    summary["decisions"] = normalize_list(decisions) if decisions else list(summary.get("decisions", []) or [])
    summary["risks"] = normalize_list(risks) if risks else list(summary.get("risks", []) or [])
    summary["verification"] = normalize_list(verification) if verification else list(summary.get("verification", []) or [])
    summary["next_steps"] = normalize_list(next_steps) if next_steps else list(summary.get("next_steps", []) or [])
    existing_role_summary_evidence = list(summary.get("role_summary_evidence", []) or [])
    existing_source_threads = list(summary.get("source_threads", []) or [])
    if role_summary_evidence:
        summary["role_summary_evidence"] = normalize_list(existing_role_summary_evidence + normalize_list(role_summary_evidence))
    else:
        summary["role_summary_evidence"] = existing_role_summary_evidence
    if source_threads:
        summary["source_threads"] = normalize_list(existing_source_threads + normalize_list(source_threads))
    else:
        summary["source_threads"] = existing_source_threads
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "update_task_summary",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "task_summary": summary,
    }


def refresh_task_gap_summary(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    test_gate = default_test_gate()
    test_gate.update(dict(payload.get("test_gate", {}) or {}))
    summary = dict(payload.get("task_summary", {}) or {})
    conflict_policy = dict(summary.get("conflict_policy", {}) or {})
    if not conflict_policy:
        conflict_policy = {
            "priority_order": ["run-main", "test", "arch", "dev"],
            "merge_rule": "append_dedup",
            "escalation_rule": "if conflict remains, escalate to run-main",
        }

    missing_roles: list[str] = []
    open_gaps: list[str] = []
    for role in ["run-main", "dev", "test"]:
        record = dict(role_summaries.get(role, {}) or {})
        if not str(record.get("summary_text", "")).strip():
            missing_roles.append(role)
            open_gaps.append(f"{role} summary missing")
    if str(test_gate.get("status", "")).strip().lower() not in {"passed", "done", "completed"}:
        open_gaps.append(f"test_gate={str(test_gate.get('status', '')).strip() or 'pending'}")
    blocking_issues = list(test_gate.get("blocking_issues", []) or [])
    for item in blocking_issues:
        text = str(item).strip()
        if text:
            open_gaps.append(text)

    gap_summary = {
        "missing_roles": normalize_list(missing_roles),
        "open_gaps": normalize_list(open_gaps),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    summary["conflict_policy"] = conflict_policy
    summary["gap_summary"] = gap_summary
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "refresh_task_gap_summary",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "conflict_policy": conflict_policy,
        "gap_summary": gap_summary,
    }


def refresh_task_escalation(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    summary = dict(payload.get("task_summary", {}) or {})
    gap_summary = dict(summary.get("gap_summary", {}) or {})
    test_gate = default_test_gate()
    test_gate.update(dict(payload.get("test_gate", {}) or {}))
    escalation_policy = dict(summary.get("escalation_policy", {}) or {})
    if not escalation_policy:
        escalation_policy = {
            "must_escalate_if": [
                "run-main summary missing",
                "test_gate not passed",
                "blocking issue remains",
            ],
            "can_resolve_in_task_if": [
                "only dev/arch detail alignment",
                "no blocking issue",
                "test gate already passed",
            ],
        }

    reasons: list[str] = []
    open_gaps = list(gap_summary.get("open_gaps", []) or [])
    for item in open_gaps:
        text = str(item).strip()
        if text == "run-main summary missing":
            reasons.append(text)
        if text.startswith("test_gate=") and text != "test_gate=passed":
            reasons.append(text)
    for item in list(test_gate.get("blocking_issues", []) or []):
        text = str(item).strip()
        if text:
            reasons.append(text)
    needs_run_main = bool(reasons)
    escalation_summary = {
        "needs_run_main": needs_run_main,
        "reasons": normalize_list(reasons),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    summary["escalation_policy"] = escalation_policy
    summary["escalation_summary"] = escalation_summary
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "refresh_task_escalation",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "escalation_policy": escalation_policy,
        "escalation_summary": escalation_summary,
    }


def get_run_main_resolution(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    summary = dict(payload.get("task_summary", {}) or {})
    return {
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "run_main_resolution_policy": dict(summary.get("run_main_resolution_policy", {}) or {}),
        "run_main_resolution": dict(summary.get("run_main_resolution", {}) or {}),
    }


def update_run_main_resolution(
    task_json_file: str | None,
    status: str,
    notes: list[str],
    close_escalation: bool,
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    summary = dict(payload.get("task_summary", {}) or {})
    resolution = dict(summary.get("run_main_resolution", {}) or {})
    resolution["status"] = str(status).strip() or str(resolution.get("status", "")).strip() or "pending_ack"
    resolution["notes"] = normalize_list(notes) if notes else list(resolution.get("notes", []) or [])
    resolution["close_escalation"] = bool(close_escalation)
    resolution["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    summary["run_main_resolution"] = resolution
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "update_run_main_resolution",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "run_main_resolution": resolution,
    }


def refresh_run_main_resolution(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    summary = dict(payload.get("task_summary", {}) or {})
    escalation_summary = dict(summary.get("escalation_summary", {}) or {})
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    test_gate = default_test_gate()
    test_gate.update(dict(payload.get("test_gate", {}) or {}))
    run_main_resolution_policy = dict(summary.get("run_main_resolution_policy", {}) or {})
    if not run_main_resolution_policy:
        run_main_resolution_policy = {
            "must_confirm_if": ["escalation_summary.needs_run_main"],
            "can_close_if": [
                "run-main summary exists",
                "test_gate passed",
                "no blocking issue remains",
            ],
        }

    run_main_summary = dict(role_summaries.get("run-main", {}) or {})
    run_main_text = str(run_main_summary.get("summary_text", "")).strip()
    test_gate_status = str(test_gate.get("status", "")).strip().lower()
    blocking_issues = normalize_list(list(test_gate.get("blocking_issues", []) or []))
    needs_run_main = bool(escalation_summary.get("needs_run_main", False))

    notes: list[str] = []
    if not needs_run_main:
        status = "not_needed"
        close = False
        notes.append("No active escalation requires run-main handling.")
    elif not run_main_text:
        status = "pending_ack"
        close = False
        notes.append("Waiting for run-main summary.")
    elif test_gate_status not in {"passed", "done", "completed"}:
        status = "acknowledged"
        close = False
        notes.append(f"run-main acknowledged; waiting for test_gate={test_gate_status or 'pending'}.")
    elif blocking_issues:
        status = "acknowledged"
        close = False
        notes.extend([f"blocking_issue: {item}" for item in blocking_issues])
    else:
        status = "closed"
        close = True
        notes.append("run-main confirmed and escalation can close.")

    resolution = {
        "status": status,
        "close_escalation": close,
        "notes": normalize_list(notes),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    summary["run_main_resolution_policy"] = run_main_resolution_policy
    summary["run_main_resolution"] = resolution
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "refresh_run_main_resolution",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "run_main_resolution_policy": run_main_resolution_policy,
        "run_main_resolution": resolution,
    }


def refresh_task_coordination(task_json_file: str | None, include_role_merge: bool = False) -> dict[str, Any]:
    merge_result: dict[str, Any] | None = None
    if include_role_merge:
        merge_result = merge_role_summaries_into_task_summary(task_json_file)
    gap_result = refresh_task_gap_summary(task_json_file)
    escalation_result = refresh_task_escalation(task_json_file)
    resolution_result = refresh_run_main_resolution(task_json_file)
    return {
        "action": "refresh_task_coordination",
        "task_json_file": resolve_task_file_arg(task_json_file),
        "task_id": str(gap_result.get("task_id", "")).strip(),
        "include_role_merge": bool(include_role_merge),
        "merge_result": merge_result,
        "gap_result": gap_result,
        "escalation_result": escalation_result,
        "resolution_result": resolution_result,
    }


def merge_role_summaries_into_task_summary(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    summary = dict(payload.get("task_summary", {}) or {})
    existing_evidence = normalize_list(list(summary.get("role_summary_evidence", []) or []))
    existing_sources = normalize_list(list(summary.get("source_threads", []) or []))
    merge_notes: list[str] = []

    for role in ["run-main", "dev", "test", "arch"]:
        record = dict(role_summaries.get(role, {}) or {})
        thread_id = str(record.get("thread_id", "")).strip()
        summary_turn_id = str(record.get("summary_turn_id", "")).strip()
        summary_text = str(record.get("summary_text", "")).strip()
        if not summary_text:
            continue
        if thread_id:
            existing_sources = normalize_list(existing_sources + [f"{role}:{thread_id}"])
        if summary_turn_id:
            existing_evidence = normalize_list(existing_evidence + [f"{role}:{summary_turn_id}"])
        merge_notes = normalize_list(merge_notes + [f"{role} summary merged"])

    summary["status"] = str(summary.get("status", "")).strip() or "draft"
    summary["source_threads"] = existing_sources
    summary["role_summary_evidence"] = existing_evidence
    summary["key_updates"] = normalize_list(list(summary.get("key_updates", []) or []) + merge_notes)
    summary["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["task_summary"] = summary
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "merge_role_summaries",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "merged_roles": merge_notes,
        "task_summary": summary,
    }


def normalize_role(role: str) -> str:
    candidate = str(role).strip().lower()
    if candidate not in {"run-main", "dev", "test", "arch"}:
        raise ValueError("role must be one of: run-main, dev, test, arch")
    return candidate


def get_role_threads(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_threads = default_role_threads()
    role_threads.update(dict(payload.get("role_threads", {}) or {}))
    return {
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "role_threads": role_threads,
    }


def get_role_summaries(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    return {
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "role_summaries": role_summaries,
    }


def update_role_thread(
    task_json_file: str | None,
    role: str,
    thread_id: str,
    thread_path: str,
    status: str,
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_threads = default_role_threads()
    role_threads.update(dict(payload.get("role_threads", {}) or {}))
    normalized_role = normalize_role(role)
    current = dict(role_threads.get(normalized_role, {}) or {})
    current["thread_id"] = str(thread_id).strip() or str(current.get("thread_id", "")).strip()
    current["thread_path"] = str(thread_path).strip() or str(current.get("thread_path", "")).strip()
    current["status"] = str(status).strip() or str(current.get("status", "")).strip() or "planned"
    role_threads[normalized_role] = current
    payload["role_threads"] = role_threads
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "update_role_thread",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "role": normalized_role,
        "role_thread": current,
    }


def update_role_summary(
    task_json_file: str | None,
    role: str,
    thread_id: str,
    thread_path: str,
    status: str,
    summary_text: str,
    summary_turn_id: str,
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    normalized_role = normalize_role(role)
    current = dict(role_summaries.get(normalized_role, {}) or {})
    current["status"] = str(status).strip() or str(current.get("status", "")).strip() or "planned"
    current["thread_id"] = str(thread_id).strip() or str(current.get("thread_id", "")).strip()
    current["thread_path"] = str(thread_path).strip() or str(current.get("thread_path", "")).strip()
    current["summary_text"] = str(summary_text).strip() or str(current.get("summary_text", "")).strip()
    current["summary_turn_id"] = str(summary_turn_id).strip() or str(current.get("summary_turn_id", "")).strip()
    current["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    role_summaries[normalized_role] = current
    payload["role_summaries"] = role_summaries
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "update_role_summary",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "role": normalized_role,
        "role_summary": current,
    }


def update_role_summary_with_task_links(
    task_json_file: str | None,
    role: str,
    thread_id: str,
    thread_path: str,
    status: str,
    summary_text: str,
    summary_turn_id: str,
) -> dict[str, Any]:
    role_result = update_role_summary(
        task_json_file,
        role,
        thread_id,
        thread_path,
        status,
        summary_text,
        summary_turn_id,
    )
    normalized_role = normalize_role(role)
    evidence_id = str(summary_turn_id).strip() or str(thread_id).strip()
    summary_result = update_task_summary(
        task_json_file,
        "",
        [],
        [],
        [],
        [],
        [],
        [f"{normalized_role}:{evidence_id}"] if evidence_id else [],
        [f"{normalized_role}:{str(thread_id).strip()}"] if str(thread_id).strip() else [],
    )
    return {
        "action": "update_role_summary_with_task_links",
        "task_json_file": role_result.get("task_json_file", ""),
        "task_id": role_result.get("task_id", ""),
        "role": normalized_role,
        "role_result": role_result,
        "task_summary_result": summary_result,
    }


def get_test_gate(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    test_gate = default_test_gate()
    test_gate.update(dict(payload.get("test_gate", {}) or {}))
    return {
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "test_gate": test_gate,
    }


def update_test_gate(
    task_json_file: str | None,
    status: str,
    required_axes: list[str],
    evidence: list[str],
    blocking_issues: list[str],
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    test_gate = default_test_gate()
    test_gate.update(dict(payload.get("test_gate", {}) or {}))
    test_gate["status"] = str(status).strip() or str(test_gate.get("status", "")).strip() or "pending"
    test_gate["owner_role"] = "test"
    test_gate["required_axes"] = normalize_list(required_axes) if required_axes else list(test_gate.get("required_axes", []) or [])
    test_gate["evidence"] = normalize_list(evidence) if evidence else list(test_gate.get("evidence", []) or [])
    test_gate["blocking_issues"] = normalize_list(blocking_issues) if blocking_issues else list(test_gate.get("blocking_issues", []) or [])
    test_gate["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["test_gate"] = test_gate
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_task(resolved, payload)
    task_md_file = str((payload.get("artifacts", {}) or {}).get("task_md_file", "")).strip()
    if task_md_file:
        write_task_md(task_md_file, payload)
    return {
        "action": "update_test_gate",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "test_gate": test_gate,
    }


def update_test_gate_from_test_summary(
    task_json_file: str | None,
    status: str,
    evidence_text: str | None = None,
    blocking_issues: list[str] | None = None,
) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    role_summaries = default_role_summaries()
    role_summaries.update(dict(payload.get("role_summaries", {}) or {}))
    test_summary = dict(role_summaries.get("test", {}) or {})
    summary_turn_id = str(test_summary.get("summary_turn_id", "")).strip()
    thread_id = str(test_summary.get("thread_id", "")).strip()
    auto_evidence: list[str] = []
    if summary_turn_id:
        auto_evidence.append(f"test-summary-turn:{summary_turn_id}")
    if thread_id:
        auto_evidence.append(f"test-thread:{thread_id}")
    if evidence_text and str(evidence_text).strip():
        auto_evidence.append(str(evidence_text).strip())
    gate_result = update_test_gate(
        resolved,
        str(status).strip().lower(),
        [],
        auto_evidence,
        list(blocking_issues or []),
    )
    return {
        "action": "update_test_gate_from_test_summary",
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "gate_result": gate_result,
    }


def get_task_summary(task_json_file: str | None) -> dict[str, Any]:
    resolved = resolve_task_file_arg(task_json_file)
    payload = load_task(resolved)
    return {
        "task_json_file": resolved,
        "task_id": str(payload.get("task_id", "")).strip(),
        "task_summary": dict(payload.get("task_summary", {}) or {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--pick-next", action="store_true")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--create-task", action="store_true")
    parser.add_argument("--active-task", action="store_true")
    parser.add_argument("--task-summary", action="store_true")
    parser.add_argument("--set-task-summary", action="store_true")
    parser.add_argument("--merge-role-summaries", action="store_true")
    parser.add_argument("--refresh-task-gaps", action="store_true")
    parser.add_argument("--refresh-task-escalation", action="store_true")
    parser.add_argument("--run-main-resolution", action="store_true")
    parser.add_argument("--set-run-main-resolution", action="store_true")
    parser.add_argument("--refresh-run-main-resolution", action="store_true")
    parser.add_argument("--role-threads", action="store_true")
    parser.add_argument("--set-role-thread", action="store_true")
    parser.add_argument("--role-summaries", action="store_true")
    parser.add_argument("--set-role-summary", action="store_true")
    parser.add_argument("--test-gate", action="store_true")
    parser.add_argument("--set-test-gate", action="store_true")
    parser.add_argument("--reconcile-task-queue-truth", action="store_true")
    parser.add_argument("--queue", action="store_true")
    parser.add_argument("--task-json-file")
    parser.add_argument("--run-id")
    parser.add_argument("--title")
    parser.add_argument("--goal")
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--priority", default="P1")
    parser.add_argument("--non-goal", action="append", default=[])
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument("--risks", default="")
    parser.add_argument("--rollback-plan", default="")
    parser.add_argument("--summary-status", default="")
    parser.add_argument("--key-update", action="append", default=[])
    parser.add_argument("--decision", action="append", default=[])
    parser.add_argument("--summary-risk", action="append", default=[])
    parser.add_argument("--verification", action="append", default=[])
    parser.add_argument("--next-step", action="append", default=[])
    parser.add_argument("--role-summary-evidence", action="append", default=[])
    parser.add_argument("--source-thread", action="append", default=[])
    parser.add_argument("--role", default="")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--thread-path", default="")
    parser.add_argument("--role-status", default="")
    parser.add_argument("--summary-text", default="")
    parser.add_argument("--summary-turn-id", default="")
    parser.add_argument("--gate-status", default="")
    parser.add_argument("--required-axis", action="append", default=[])
    parser.add_argument("--gate-evidence", action="append", default=[])
    parser.add_argument("--blocking-issue", action="append", default=[])
    parser.add_argument("--resolution-status", default="")
    parser.add_argument("--resolution-note", action="append", default=[])
    parser.add_argument("--close-escalation", action="store_true")
    args = parser.parse_args()

    if args.next or args.pick_next:
        result = pick_next()
    elif args.create or args.create_task:
        if not args.title or not args.goal or not args.scope:
            parser.error("--create requires --title, --goal, and at least one --scope")
            return 2
        run_id = default_run_id(args.run_id)
        if not run_id:
            parser.error("--create requires --run-id or an active runtime run")
            return 2
        result = create_task(
            args.title,
            args.goal,
            list(args.scope),
            run_id,
            args.queue,
            args.activate,
            str(args.priority),
            list(args.non_goal),
            list(args.input),
            list(args.acceptance),
            str(args.risks),
            str(args.rollback_plan),
        )
    elif args.active_task:
        result = load_active_task()
    elif args.task_summary:
        result = get_task_summary(args.task_json_file)
    elif args.set_task_summary:
        result = update_task_summary(
            args.task_json_file,
            str(args.summary_status),
            list(args.key_update),
            list(args.decision),
            list(args.summary_risk),
            list(args.verification),
            list(args.next_step),
            list(args.role_summary_evidence),
            list(args.source_thread),
        )
    elif args.merge_role_summaries:
        result = merge_role_summaries_into_task_summary(args.task_json_file)
    elif args.refresh_task_gaps:
        result = refresh_task_gap_summary(args.task_json_file)
    elif args.refresh_task_escalation:
        result = refresh_task_escalation(args.task_json_file)
    elif args.run_main_resolution:
        result = get_run_main_resolution(args.task_json_file)
    elif args.set_run_main_resolution:
        result = update_run_main_resolution(
            args.task_json_file,
            str(args.resolution_status),
            list(args.resolution_note),
            bool(args.close_escalation),
        )
    elif args.refresh_run_main_resolution:
        result = refresh_run_main_resolution(args.task_json_file)
    elif args.role_threads:
        result = get_role_threads(args.task_json_file)
    elif args.role_summaries:
        result = get_role_summaries(args.task_json_file)
    elif args.set_role_thread:
        result = update_role_thread(
            args.task_json_file,
            str(args.role),
            str(args.thread_id),
            str(args.thread_path),
            str(args.role_status),
        )
    elif args.set_role_summary:
        result = update_role_summary(
            args.task_json_file,
            str(args.role),
            str(args.thread_id),
            str(args.thread_path),
            str(args.role_status),
            str(args.summary_text),
            str(args.summary_turn_id),
        )
    elif args.test_gate:
        result = get_test_gate(args.task_json_file)
    elif args.set_test_gate:
        result = update_test_gate(
            args.task_json_file,
            str(args.gate_status),
            list(args.required_axis),
            list(args.gate_evidence),
            list(args.blocking_issue),
        )
    elif args.reconcile_task_queue_truth:
        result = reconcile_task_queue_truth()
    elif args.queue and not args.title:
        result = load_queue()
    elif args.task_json_file:
        result = load_task(args.task_json_file)
    elif args.run_id and not args.title:
        result = {"run_id": args.run_id, "task_id": find_task_id_for_run(args.run_id)}
    else:
        parser.error(
            "supported commands: --next, --create, --active-task, --task-summary, --set-task-summary, --merge-role-summaries, --refresh-task-gaps, --refresh-task-escalation, --run-main-resolution, --set-run-main-resolution, --refresh-run-main-resolution, --role-threads, --set-role-thread, --role-summaries, --set-role-summary, --test-gate, --set-test-gate, --reconcile-task-queue-truth, --queue, --task-json-file, or --run-id"
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
