#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CONFIG_FILE = REPO_ROOT / "tools" / "project_config.json"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOGGER_NAME = "qf.project_config"
logger = logging.getLogger(LOGGER_NAME)

TOOLS_DIR_NAME = "tools"
DOCS_DIR_NAME = "docs"
AGENTS_FILE_NAME = "AGENTS.md"
PROJECT_GUIDE_FILE_NAME = "docs/PROJECT_GUIDE.md"
LEARN_BASELINE_PROMPT_FILE_NAME = "tools/prompts/learnbaseline_prompt.md"
OWNER_FILES = [
    "docs/PROJECT_GUIDE.md",
    "AGENTS.md",
    "docs/WORKFLOW.md",
]
GUIDE_QUESTION_RE = re.compile(r"^###\s+Q(?P<num>\d+)\.\s*(?P<title>.+?)\s*$", re.M)
GUIDE_SECTION_RE = re.compile(r"^####\s+(?P<title>.+?)\s*$", re.M)

GIT_REMOTE_NAME = "origin"
GIT_USER_NAME = ""
GIT_USER_EMAIL = ""
GIT_AUTH_CHECK_COMMAND = "gh auth status"

CODEX_BIN = "codex"
CODEX_AUTH_MODE = "chatgpt"
CODEX_ACCOUNT_LABEL = ""
CODEX_HOME = "~/.codex"
CODEX_LOGIN_STATUS_COMMAND = "codex login status"
APP_SERVER_SUBCOMMAND = "app-server"
APP_SERVER_SESSION_ENV_KEYS = (
    "CODEX_SESSION_ID",
    "OPENAI_SESSION_ID",
    "APP_SERVER_SESSION_ID",
)
CODEX_CLIENT_NAME = "test-app"
CODEX_CLIENT_VERSION = "0.1.0"
CODEX_CAPABILITIES = {"experimentalApi": True}

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_MODE = "default"
DEFAULT_EFFORT = "low"
DEFAULT_TIMEOUT_SEC = 60
PLAN_TIMEOUT_SEC = 1200
DEFAULT_THREAD_NAME = "test-thread"
DEFAULT_THREAD_SEARCH_LIMIT = 10
DEFAULT_TURN_TEXT = "你好"
LEARN_INIT_THREAD_NAME = "learn-init-thread"
LEARN_INIT_EFFORT = "low"


# project_config 中文：统一把“中文说明 + 字段名 + 值”格式化成单行日志输出。
def format_field(label_cn: str, field_name: str, value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return f"{label_cn}-{field_name}: {text or '(未配置)'}"


# project_config 中文：把配置里的路径字段统一解析为绝对路径；已是绝对路径就直接使用，相对路径则相对给定根路径解析。
def resolve_config_path(raw_path: str, base_root: Path) -> Path:
    candidate = Path(str(raw_path))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_root / candidate).resolve()


# project_config 中文：按顺序去重列表，保持第一次出现的顺序。
def ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


# project_config 中文：把 guide 里的占位符路径解析为当前项目/运行态的真实路径。
def resolve_dynamic_path(raw_path: str, project_id: str, current_run_id: str) -> str:
    path = str(raw_path or "").strip()
    if not path:
        return ""
    if ("<RUN_ID>" in path or "<CURRENT_RUN_ID>" in path) and not current_run_id:
        return ""
    path = path.replace("<PROJECT_ID>", project_id)
    path = path.replace("<CURRENT_PROJECT_ID>", project_id)
    path = path.replace("<RUN_ID>", current_run_id)
    path = path.replace("<CURRENT_RUN_ID>", current_run_id)
    return path


# project_config 中文：把 markdown 列表/段落块收成干净的文本行列表。
def normalize_list_block(lines: list[str]) -> list[str]:
    result: list[str] = []
    for raw in lines:
        value = str(raw).strip()
        if not value:
            continue
        if value.startswith("- "):
            value = value[2:].strip()
        result.append(value)
    return result


def extract_backtick_tokens(text: str) -> list[str]:
    return [token.strip() for token in re.findall(r"`([^`]+)`", str(text or "")) if token.strip()]


def is_valid_required_file_path(raw_path: str, project_root: Path) -> bool:
    candidate = str(raw_path or "").strip()
    if not candidate:
        return False
    if any(marker in candidate for marker in ("同上", "owner docs", "owner doc", "foundation 仓", "本项目 7 份")):
        return False
    if "\n" in candidate or "\r" in candidate:
        return False
    if " / " in candidate or " | " in candidate or "，" in candidate or "," in candidate:
        return False
    try:
        resolved = resolve_config_path(candidate, project_root)
    except Exception:
        return False
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return False
    return resolved.exists() and resolved.is_file()


def extract_required_file_paths(
    item: str,
    project_root: Path,
    project_id: str,
    current_run_id: str,
) -> list[str]:
    raw_value = str(item or "").strip()
    if not raw_value:
        return []
    resolved_item = resolve_dynamic_path(raw_value, project_id, current_run_id)
    candidates = extract_backtick_tokens(resolved_item) or [resolved_item]
    results: list[str] = []
    for candidate in candidates:
        value = resolve_dynamic_path(candidate, project_id, current_run_id)
        if not is_valid_required_file_path(value, project_root):
            continue
        results.append(value)
    return ordered_unique(results)


# project_config 中文：读取 baseline 学习提示词固定前言；提示词文件是可维护资产，不继续写死在 Python 长字符串里。
def load_learnbaseline_prompt_preamble() -> str:
    prompt_file = resolve_config_path(LEARN_BASELINE_PROMPT_FILE_NAME, REPO_ROOT)
    return prompt_file.read_text(encoding="utf-8").strip()


# project_config 中文：从 PROJECT_GUIDE 解析学习问题清单与必查文件，供 baseline 学习 prompt 动态补全。
def parse_project_guide_prompt_inputs(project_root: Path, project_id: str, current_run_id: str) -> tuple[list[dict[str, str]], list[str]]:
    guide_path = resolve_config_path(PROJECT_GUIDE_FILE_NAME, project_root)
    if not guide_path.exists():
        return [], list(OWNER_FILES)
    text = guide_path.read_text(encoding="utf-8")
    matches = list(GUIDE_QUESTION_RE.finditer(text))
    questions: list[dict[str, str]] = []
    required_files: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].splitlines()
        qid = f"Q{match.group('num')}"
        title = match.group("title").strip()
        sections: dict[str, list[str]] = {}
        current_section = ""
        for raw in block[1:]:
            sec_match = GUIDE_SECTION_RE.match(raw.strip())
            if sec_match:
                current_section = sec_match.group("title").strip()
                sections[current_section] = []
                continue
            if current_section:
                sections[current_section].append(raw)
        must_read_files: list[str] = []
        for item in normalize_list_block(sections.get("必查文件", [])):
            must_read_files.extend(
                extract_required_file_paths(
                    item,
                    project_root,
                    project_id,
                    current_run_id,
                )
            )
        must_read_files = ordered_unique(must_read_files)
        questions.append({"question_id": qid, "title": title})
        required_files.extend(must_read_files)
    return questions, ordered_unique(OWNER_FILES + required_files)


# project_config 中文：构建 baseline 学习要求的 JSON 输出 schema 文本。
def build_learn_output_schema_lines() -> list[str]:
    return [
        "{",
        '  "mainline": "<string>",',
        '  "current_stage": "<string>",',
        '  "next_step": "<string>",',
        '  "files_read": ["<path1>", "<path2>"],',
        '  "plan_protocol": {',
        '    "goal": "<string>",',
        '    "non_goal": "<string>",',
        '    "evidence": ["<path>#<section>: <concrete fact>"],',
        '    "alternatives": ["<alt1>", "<alt2>"],',
        '    "rebuttal": "<string>",',
        '    "decision_stop_condition": "<string>"',
        "  },",
        '  "oral_restate": {',
        '    "project_understanding": "<string>",',
        '    "constitution_workflow": "<string>",',
        '    "evidence_chain": "<string>",',
        '    "session_continuity": "<string>",',
        '    "current_focus": "<string>",',
        '    "next_action": "<string>"',
        "  },",
        '  "guide_oral": [',
        '    {',
        '      "question_id": "Q1",',
        '      "question": "<question title>",',
        '      "answer": "<1-2 sentence oral answer>",',
        '      "standard_alignment": "aligned|partial|drifted",',
        '      "evidence": ["<path>#<section>: <concrete fact>"],',
        '      "drift_note": "<short difference or none>",',
        '      "return_to_mainline": "<how this question returns to mainline>"',
        '    }',
        '  ],',
        '  "anchor_realign": {',
        '    "question_id": "<Q1..Qn from PROJECT_GUIDE>",',
        '    "status": "on_track|drifted",',
        '    "drift_detail": "<what drift happened or none>",',
        '    "return_to_mainline": "<how to return to mainline now>"',
        '  }',
        "}",
    ]


# project_config 中文：把固定提示词文件和动态学习上下文拼成 baseline 学习 prompt。
def build_learnbaseline_prompt_text(project_root: Path, project_id: str, runtime_state: dict[str, Any]) -> str:
    preamble = load_learnbaseline_prompt_preamble()
    current_run_id = str(runtime_state.get("current_run_id", "")).strip()
    current_task_json_file = str(runtime_state.get("current_task_json_file", "")).strip()
    current_task_file = str(runtime_state.get("current_task_file", "")).strip()
    guide_questions, required_files = parse_project_guide_prompt_inputs(project_root, project_id, current_run_id)
    extra_files = [path for path in required_files if path not in OWNER_FILES]
    lines = [
        preamble,
        "",
        "以下是本轮学习同频的动态上下文，请按这些上下文执行基线学习：",
        f"PROJECT_ID: {project_id}",
        f"CURRENT_RUN_ID: {current_run_id or '(none)'}",
        f"CURRENT_TASK_JSON_FILE: {current_task_json_file or '(none)'}",
        f"CURRENT_TASK_FILE: {current_task_file or '(none)'}",
        "",
        "Owner files:",
    ]
    for path in OWNER_FILES:
        lines.append(f"- {path}")
    lines.extend(
        [
            "",
            "Additional required files to read with tools/view.sh:",
        ]
    )
    for path in extra_files:
        lines.append(f"- {path}")
    lines.extend(["", "PROJECT_GUIDE question ids to answer in order:"])
    for item in guide_questions:
        lines.append(f"- {item['question_id']}: {item['title']}")
    lines.extend(
        [
            "",
            "Output requirements:",
            "- Read owner files first in this order: docs/PROJECT_GUIDE.md -> AGENTS.md -> docs/WORKFLOW.md.",
            "- Then read the additional required files listed above.",
            "- For all file reads inside this learning session, use the explicit command form: python3 tools/view.sh <path> --from <start> --to <end>.",
            "- Do not call ./tools/view.sh directly.",
            "- If a file is short, you may still use python3 tools/view.sh with a single chunk that covers the needed range.",
            "- If python3 tools/view.sh fails with a sandbox or bwrap / namespace error, rerun the exact same command with escalated permissions instead of changing tools or stopping the learning flow.",
            "- Use PROJECT_GUIDE as the source of truth for question order and must-read mapping.",
            "- Then answer every PROJECT_GUIDE question in order (Q1..Qn).",
            "- Do not skip any question.",
            "- Keep every answer concise but complete: target 1-2 sentences per question.",
            "- Reply with JSON only. Any prose before or after the JSON object is a failure.",
            "- JSON must follow this schema exactly:",
        ]
    )
    lines.extend(build_learn_output_schema_lines())
    return "\n".join(lines).strip()


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str
    project_root: Path
    tools_dir: Path
    docs_dir: Path
    agents_file: Path
    project_guide_file: Path
    git_repo_path: Path
    git_remote_name: str
    git_remote_url: str
    github_login: str
    git_user_name: str
    git_user_email: str
    git_auth_check_command: str
    codex_bin: str
    codex_auth_mode: str
    codex_account_label: str
    codex_home: str
    codex_login_status_command: str
    app_server_subcommand: str
    app_server_session_env_keys: tuple[str, ...]
    codex_client_name: str
    codex_client_version: str
    codex_capabilities: dict[str, Any]
    default_model: str
    default_mode: str
    default_effort: str
    default_timeout_sec: int
    plan_timeout_sec: int
    default_thread_name: str
    default_thread_search_limit: int
    default_turn_text: str
    learn_init_thread_name: str
    learn_init_effort: str
    learn_init_turn_text: str


@dataclass(frozen=True)
class RuntimeState:
    current_project_id: str
    current_run_id: str
    current_task_id: str
    current_task_file: str
    current_task_json_file: str
    current_status: str
    current_updated_at: str


# project_config 中文：读取原始项目配置 JSON。
def load_project_config_json() -> dict[str, Any]:
    return json.loads(PROJECT_CONFIG_FILE.read_text(encoding="utf-8"))


# project_config 中文：校验原始 project_config.json 的必填字段是否真的填写。
def validate_required_json_fields(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = dict(raw.get("required", {}) or {})
    if not str(required.get("project_id", "")).strip():
        errors.append("必填字段为空-required.project_id")
    if not str(required.get("project_root", "")).strip():
        errors.append("必填字段为空-required.project_root")
    return errors


# project_config 中文：把更新后的项目配置 JSON 回写到磁盘。
def save_project_config_json(config: dict[str, Any]) -> None:
    PROJECT_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# project_config 中文：把最小 JSON、系统常量、运行时状态和会话注册表拼成统一的大配置视图。
def load_unified_config() -> dict[str, Any]:
    raw = load_project_config_json()
    required = dict(raw.get("required", {}) or {})
    git = dict(raw.get("git", {}) or {})
    bootstrap_state = dict(raw.get("bootstrap_state", {}) or {})
    project_id = str(required.get("project_id", raw.get("project_id", ""))).strip()
    project_root = resolve_config_path(str(required.get("project_root", raw.get("project_root", ""))), REPO_ROOT)
    runtime_state = dict(raw.get("runtime_state", {}) or {})
    session_registry = dict(raw.get("session_registry", {}) or {})
    return {
        "required": {
            "project_id": project_id,
            "project_root": str(project_root),
        },
        "project_id": project_id,
        "project_root": str(project_root),
        "tools_dir": str(resolve_config_path(TOOLS_DIR_NAME, project_root)),
        "docs_dir": str(resolve_config_path(DOCS_DIR_NAME, project_root)),
        "agents_file": str(resolve_config_path(AGENTS_FILE_NAME, project_root)),
        "project_guide_file": str(resolve_config_path(PROJECT_GUIDE_FILE_NAME, project_root)),
        "learnbaseline_prompt_file": str(resolve_config_path(LEARN_BASELINE_PROMPT_FILE_NAME, REPO_ROOT)),
        "git": {
            "repo_path": str(project_root),
            "remote_name": GIT_REMOTE_NAME,
            "remote_url": str(git.get("remote_url", "")).strip(),
            "github_login": str(git.get("github_login", "")).strip(),
            "git_user_name": GIT_USER_NAME,
            "git_user_email": GIT_USER_EMAIL,
            "auth_check_command": GIT_AUTH_CHECK_COMMAND,
        },
        "bootstrap_state": {
            "is_inited": str(bootstrap_state.get("is_inited", "N")).strip().upper() or "N",
            "initialized_at": str(bootstrap_state.get("initialized_at", "")).strip(),
            "initialized_by": str(bootstrap_state.get("initialized_by", "")).strip(),
            "bootstrap_source": str(bootstrap_state.get("bootstrap_source", "")).strip(),
        },
        "codex": {
            "bin": CODEX_BIN,
            "auth_mode": CODEX_AUTH_MODE,
            "account_label": CODEX_ACCOUNT_LABEL,
            "home": str(Path(CODEX_HOME).expanduser()),
            "login_status_command": CODEX_LOGIN_STATUS_COMMAND,
            "app_server_subcommand": APP_SERVER_SUBCOMMAND,
            "app_server_session_env_keys": list(APP_SERVER_SESSION_ENV_KEYS),
            "client_name": CODEX_CLIENT_NAME,
            "client_version": CODEX_CLIENT_VERSION,
            "capabilities": dict(CODEX_CAPABILITIES),
        },
        "runtime_defaults": {
            "default_model": DEFAULT_MODEL,
            "default_mode": DEFAULT_MODE,
            "default_effort": DEFAULT_EFFORT,
            "default_timeout_sec": DEFAULT_TIMEOUT_SEC,
            "plan_timeout_sec": PLAN_TIMEOUT_SEC,
            "default_thread_name": DEFAULT_THREAD_NAME,
            "default_thread_search_limit": DEFAULT_THREAD_SEARCH_LIMIT,
            "default_turn_text": DEFAULT_TURN_TEXT,
            "learn_init_thread_name": LEARN_INIT_THREAD_NAME,
            "learn_init_effort": LEARN_INIT_EFFORT,
            "learn_init_turn_text": build_learnbaseline_prompt_text(project_root, project_id, runtime_state),
        },
        "runtime_state": runtime_state,
        "session_registry": session_registry,
    }


# project_config 中文：把 JSON 配置转换成代码里可直接使用的结构化对象。
def load_project_config() -> ProjectConfig:
    unified = load_unified_config()
    project_root = Path(str(unified["project_root"]))
    git = dict(unified["git"])
    codex = dict(unified["codex"])
    runtime_defaults = dict(unified["runtime_defaults"])
    return ProjectConfig(
        project_id=str(unified["project_id"]),
        project_root=project_root,
        tools_dir=Path(str(unified["tools_dir"])),
        docs_dir=Path(str(unified["docs_dir"])),
        agents_file=Path(str(unified["agents_file"])),
        project_guide_file=Path(str(unified["project_guide_file"])),
        git_repo_path=Path(str(git["repo_path"])),
        git_remote_name=str(git["remote_name"]),
        git_remote_url=str(git["remote_url"]),
        github_login=str(git["github_login"]),
        git_user_name=str(git["git_user_name"]),
        git_user_email=str(git["git_user_email"]),
        git_auth_check_command=str(git["auth_check_command"]),
        codex_bin=str(codex["bin"]),
        codex_auth_mode=str(codex["auth_mode"]),
        codex_account_label=str(codex["account_label"]),
        codex_home=str(codex["home"]),
        codex_login_status_command=str(codex["login_status_command"]),
        app_server_subcommand=str(codex["app_server_subcommand"]),
        app_server_session_env_keys=tuple(str(x) for x in codex["app_server_session_env_keys"]),
        codex_client_name=str(codex["client_name"]),
        codex_client_version=str(codex["client_version"]),
        codex_capabilities=dict(codex["capabilities"]),
        default_model=str(runtime_defaults["default_model"]),
        default_mode=str(runtime_defaults["default_mode"]),
        default_effort=str(runtime_defaults["default_effort"]),
        default_timeout_sec=int(runtime_defaults["default_timeout_sec"]),
        plan_timeout_sec=int(runtime_defaults["plan_timeout_sec"]),
        default_thread_name=str(runtime_defaults["default_thread_name"]),
        default_thread_search_limit=int(runtime_defaults["default_thread_search_limit"]),
        default_turn_text=str(runtime_defaults["default_turn_text"]),
        learn_init_thread_name=str(runtime_defaults["learn_init_thread_name"]),
        learn_init_effort=str(runtime_defaults["learn_init_effort"]),
        learn_init_turn_text=str(runtime_defaults["learn_init_turn_text"]),
    )


# project_config 中文：把 JSON 里的 runtime_state 转成结构化运行状态对象。
def load_runtime_state() -> RuntimeState:
    raw = load_unified_config().get("runtime_state", {}) or {}
    return RuntimeState(
        current_project_id=str(raw.get("current_project_id", "")).strip(),
        current_run_id=str(raw.get("current_run_id", "")).strip(),
        current_task_id=str(raw.get("current_task_id", "")).strip(),
        current_task_file=str(raw.get("current_task_file", "")).strip(),
        current_task_json_file=str(raw.get("current_task_json_file", "")).strip(),
        current_status=str(raw.get("current_status", "")).strip(),
        current_updated_at=str(raw.get("current_updated_at", "")).strip(),
    )


# project_config 中文：读取项目 bootstrap_state，判断当前项目是否已完成首轮初始化接入。
def get_bootstrap_state() -> dict[str, Any]:
    return dict(load_unified_config().get("bootstrap_state", {}) or {})


# project_config 中文：判断当前项目是否已完成初始化接入。
def is_project_inited() -> bool:
    return str(get_bootstrap_state().get("is_inited", "N")).strip().upper() == "Y"


# project_config 中文：统一打印关键项目配置，便于后续各入口做中文参数确认。
def describe_project_config(cfg: ProjectConfig) -> list[str]:
    return [
        format_field("当前项目ID", "project_id", cfg.project_id),
        format_field("项目根目录", "project_root", cfg.project_root),
        format_field("tools目录", "tools_dir", cfg.tools_dir),
        format_field("docs目录", "docs_dir", cfg.docs_dir),
        format_field("宪法文件路径", "agents_file", cfg.agents_file),
        format_field("PROJECT_GUIDE路径", "project_guide_file", cfg.project_guide_file),
        format_field("Codex可执行命令", "codex_bin", cfg.codex_bin),
        format_field("app-server子命令", "app_server_subcommand", cfg.app_server_subcommand),
        format_field(
            "app-server会话环境变量候选",
            "app_server_session_env_keys",
            ", ".join(cfg.app_server_session_env_keys),
        ),
        format_field("Codex客户端名称", "codex_client_name", cfg.codex_client_name),
        format_field("Codex客户端版本", "codex_client_version", cfg.codex_client_version),
        format_field("默认模型", "default_model", cfg.default_model),
        format_field("默认模式", "default_mode", cfg.default_mode),
        format_field("默认推理强度", "default_effort", cfg.default_effort),
        format_field("默认超时时间(秒)", "default_timeout_sec", cfg.default_timeout_sec),
        format_field("Plan模式超时时间(秒)", "plan_timeout_sec", cfg.plan_timeout_sec),
        format_field("默认线程名", "default_thread_name", cfg.default_thread_name),
        format_field("默认线程搜索数量", "default_thread_search_limit", cfg.default_thread_search_limit),
        format_field("默认普通对话输入", "default_turn_text", cfg.default_turn_text),
        format_field("学习基线线程名", "learn_init_thread_name", cfg.learn_init_thread_name),
        format_field("学习基线推理强度", "learn_init_effort", cfg.learn_init_effort),
        format_field("学习基线固定提示词", "learn_init_turn_text", cfg.learn_init_turn_text),
    ]


# project_config 中文：统一打印当前运行状态，后续其他脚本应优先从这里读取。
def describe_runtime_state(state: RuntimeState) -> list[str]:
    return [
        format_field("当前项目ID", "current_project_id", state.current_project_id),
        format_field("当前运行ID", "current_run_id", state.current_run_id),
        format_field("当前任务ID", "current_task_id", state.current_task_id),
        format_field("当前任务JSON文件", "current_task_json_file", state.current_task_json_file),
        format_field("当前任务文件", "current_task_file", state.current_task_file),
        format_field("当前状态", "current_status", state.current_status),
        format_field("当前状态更新时间", "current_updated_at", state.current_updated_at),
    ]


# project_config 中文：统一打印 Git 账户与校验命令相关配置。
def describe_git_account_config(cfg: ProjectConfig) -> list[str]:
    return [
        format_field("Git仓库路径", "git_account.repo_path", cfg.git_repo_path),
        format_field("Git远端名称", "git_account.remote_name", cfg.git_remote_name),
        format_field("Git远端地址", "git_account.remote_url", cfg.git_remote_url),
        format_field("GitHub登录名", "git_account.github_login", cfg.github_login),
        format_field("Git用户名", "git_account.git_user_name", cfg.git_user_name),
        format_field("Git邮箱", "git_account.git_user_email", cfg.git_user_email),
        format_field("Git认证检查命令", "git_account.auth_check_command", cfg.git_auth_check_command),
    ]


# project_config 中文：统一打印 Codex 账户与运行时相关配置。
def describe_codex_account_config(cfg: ProjectConfig) -> list[str]:
    return [
        format_field("Codex可执行命令", "codex_bin", cfg.codex_bin),
        format_field("Codex认证模式", "codex_account.auth_mode", cfg.codex_auth_mode),
        format_field("Codex账户标识", "codex_account.account_label", cfg.codex_account_label),
        format_field("Codex HOME目录", "codex_account.codex_home", cfg.codex_home),
        format_field("Codex登录状态检查命令", "codex_account.login_status_command", cfg.codex_login_status_command),
    ]


# project_config 中文：把会话注册表转换成逐字段中文说明，便于 if main 单独查看。
def describe_session_registry(registry: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if not registry:
        return ["会话注册表为空"]
    for slot, raw in registry.items():
        item = dict(raw or {})
        lines.append(format_field("会话槽位", "session_registry.slot", slot))
        lines.append(format_field("  线程ID", f"{slot}.thread_id", item.get("thread_id", "")))
        lines.append(format_field("  线程文件路径", f"{slot}.thread_path", item.get("thread_path", "")))
        lines.append(format_field("  会话状态", f"{slot}.status", item.get("status", "")))
        lines.append(format_field("  更新时间", f"{slot}.updated_at", item.get("updated_at", "")))
        lines.append(format_field("  来源", f"{slot}.source", item.get("source", "")))
        lines.append(format_field("  模型", f"{slot}.model", item.get("model", "")))
        lines.append(format_field("  推理强度", f"{slot}.effort", item.get("effort", "")))
        if "forked_from_thread_id" in item:
            lines.append(format_field("  Fork来源线程ID", f"{slot}.forked_from_thread_id", item.get("forked_from_thread_id", "")))
    return lines


# project_config 中文：校验关键项目配置非空和路径存在性。
def validate_project_config(cfg: ProjectConfig, allow_bootstrap_missing: bool = False) -> list[str]:
    errors: list[str] = []
    if not cfg.project_id.strip():
        errors.append("必填字段为空-required.project_id")
    if not cfg.project_root.exists():
        errors.append(f"项目根目录不存在-required.project_root: {cfg.project_root}")
    if not cfg.tools_dir.exists() and not allow_bootstrap_missing:
        errors.append(f"tools目录不存在-tools_dir: {cfg.tools_dir}")
    if not cfg.docs_dir.exists() and not allow_bootstrap_missing:
        errors.append(f"docs目录不存在-docs_dir: {cfg.docs_dir}")
    if not cfg.agents_file.is_file() and not allow_bootstrap_missing:
        errors.append(f"宪法文件不存在-agents_file: {cfg.agents_file}")
    if not cfg.project_guide_file.is_file() and not allow_bootstrap_missing:
        errors.append(f"PROJECT_GUIDE不存在-project_guide_file: {cfg.project_guide_file}")
    if not cfg.codex_bin.strip():
        errors.append("Codex命令为空-codex_bin")
    if not cfg.git_repo_path.exists():
        errors.append(f"Git仓库路径不存在-git.repo_path: {cfg.git_repo_path}")
    if not cfg.git_remote_name.strip():
        errors.append("Git远端名称为空-git.remote_name")
    if not cfg.git_remote_url.strip():
        errors.append("Git远端地址为空-git.remote_url")
    if not cfg.git_auth_check_command.strip():
        errors.append("Git认证检查命令为空-git.auth_check_command")
    if not cfg.codex_login_status_command.strip():
        errors.append("Codex登录检查命令为空-codex.login_status_command")
    if not cfg.codex_auth_mode.strip():
        errors.append("Codex认证模式为空-codex.auth_mode")
    return errors


# project_config 中文：校验 runtime_state 的关键字段是否完整且与 project_id 语义一致。
def validate_runtime_state(cfg: ProjectConfig, state: RuntimeState) -> list[str]:
    errors: list[str] = []
    if not state.current_project_id:
        errors.append("运行时项目ID为空-runtime_state.current_project_id")
    elif state.current_project_id != cfg.project_id:
        errors.append(
            "运行时项目ID不一致-runtime_state.current_project_id: "
            f"{state.current_project_id} != {cfg.project_id}"
        )
    if not state.current_run_id:
        errors.append("运行时运行ID为空-runtime_state.current_run_id")
    if state.current_task_id and not state.current_task_json_file:
        errors.append("运行时任务JSON文件为空-runtime_state.current_task_json_file")
    if not state.current_status:
        errors.append("运行时状态为空-runtime_state.current_status")
    if not state.current_updated_at:
        errors.append("运行时更新时间为空-runtime_state.current_updated_at")
    return errors


# project_config 中文：从配置 registry 读取指定 session 槽位。
def get_session_registry(slot: str) -> dict[str, Any]:
    registry = load_unified_config().get("session_registry", {})
    return dict(registry.get(slot, {}) or {})


# project_config 中文：读取指定 session 槽位里的 thread_id。
def get_session_thread_id(slot: str) -> str:
    return str(get_session_registry(slot).get("thread_id", "")).strip()


# project_config 中文：读取指定 session 槽位里的 thread_path。
def get_session_thread_path(slot: str) -> str:
    return str(get_session_registry(slot).get("thread_path", "")).strip()


# project_config 中文：要求指定 session 槽位必须已有 thread_id，否则抛出明确错误。
def require_session_thread_id(slot: str, next_command: str) -> str:
    thread_id = get_session_thread_id(slot)
    if not thread_id:
        raise ValueError(f"会话槽位为空-{slot}.thread_id，请先执行: {next_command}")
    return thread_id


# project_config 中文：按配置里的候选环境变量顺序读取当前 app-server session_id。
def get_app_server_session_id(cfg: ProjectConfig) -> str:
    import os

    for key in cfg.app_server_session_env_keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


# project_config 中文：按点号路径读取常用配置字段，供 shell 脚本统一取值。
def get_config_value(key: str) -> str:
    current: Any = load_unified_config()
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return ""
    if isinstance(current, (dict, list)):
        return json.dumps(current, ensure_ascii=False)
    return str(current)


# project_config 中文：把 learn baseline 或当前 fork session 的 thread 信息写入配置 registry。
def update_session_registry(slot: str, thread_id: str, thread_path: str, status: str, source: str, model: str, effort: str, forked_from_thread_id: str = "") -> None:
    config = load_project_config_json()
    registry = config.setdefault("session_registry", {})
    record = registry.setdefault(slot, {})
    record["thread_id"] = thread_id
    record["thread_path"] = thread_path
    record["status"] = status
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    record["source"] = source
    record["model"] = model
    record["effort"] = effort
    if forked_from_thread_id:
        record["forked_from_thread_id"] = forked_from_thread_id
    elif "forked_from_thread_id" in record:
        record["forked_from_thread_id"] = ""
    save_project_config_json(config)


def update_init_project_session(
    status: str,
    source: str,
    model: str,
    effort: str,
    payload: dict[str, Any] | None = None,
) -> None:
    config = load_project_config_json()
    registry = config.setdefault("session_registry", {})
    record = registry.setdefault("init_project_session", {})
    if not str(record.get("thread_id", "")).strip():
        record["thread_id"] = f"init-project-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    record["thread_path"] = "phase1_local_runtime"
    record["status"] = status
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    record["source"] = source
    record["model"] = model
    record["effort"] = effort
    if payload is not None:
        record["phase"] = str(payload.get("phase", "")).strip()
        record["session_execution_instruction"] = str(payload.get("session_execution_instruction", "")).strip()
        record["operator_notes"] = str(payload.get("operator_notes", "")).strip()
        record["answered_questions"] = list(payload.get("answered_questions", []) or [])
        record["unclear_questions"] = list(payload.get("unclear_questions", []) or [])
        record["customer_followups"] = list(payload.get("customer_followups", []) or [])
        record["document_priority_understanding"] = str(payload.get("document_priority_understanding", "")).strip()
        record["current_project_understanding"] = str(payload.get("current_project_understanding", "")).strip()
        record["ready_for_doc_write"] = bool(payload.get("ready_for_doc_write", False))
        record["must_read_next"] = list(payload.get("must_read_next", []) or [])
        record["implementation_gaps"] = list(payload.get("implementation_gaps", []) or [])
    save_project_config_json(config)


def update_bootstrap_state(
    is_inited: str,
    initialized_by: str = "",
    bootstrap_source: str = "",
    initialized_at: str = "",
) -> None:
    config = load_project_config_json()
    state = config.setdefault("bootstrap_state", {})
    normalized = str(is_inited).strip().upper()
    state["is_inited"] = "Y" if normalized == "Y" else normalized
    state["initialized_by"] = str(initialized_by).strip()
    state["bootstrap_source"] = str(bootstrap_source).strip()
    state["initialized_at"] = str(initialized_at).strip() or datetime.now(timezone.utc).isoformat()
    save_project_config_json(config)


# project_config 中文：写回 current_summary 去噪摘要，供 baseline refresh 作为唯一输入来源。
def update_current_summary(
    thread_id: str,
    thread_path: str,
    status: str,
    source: str,
    model: str,
    effort: str,
    summary_text: str,
    summary_turn_id: str = "",
    baseline_refresh_text: str = "",
    baseline_refresh_turn_id: str = "",
    baseline_refresh_input_type: str = "",
    baseline_refresh_input_ref: str = "",
) -> None:
    config = load_project_config_json()
    registry = config.setdefault("session_registry", {})
    record = registry.setdefault("current_summary", {})
    record["thread_id"] = thread_id
    record["thread_path"] = thread_path
    record["status"] = status
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    record["source"] = source
    record["model"] = model
    record["effort"] = effort
    record["summary_text"] = summary_text
    record["summary_turn_id"] = summary_turn_id
    if baseline_refresh_text:
        record["baseline_refresh_text"] = baseline_refresh_text
    elif "baseline_refresh_text" not in record:
        record["baseline_refresh_text"] = ""
    if baseline_refresh_turn_id:
        record["baseline_refresh_turn_id"] = baseline_refresh_turn_id
    elif "baseline_refresh_turn_id" not in record:
        record["baseline_refresh_turn_id"] = ""
    if baseline_refresh_input_type:
        record["baseline_refresh_input_type"] = baseline_refresh_input_type
    elif "baseline_refresh_input_type" not in record:
        record["baseline_refresh_input_type"] = ""
    if baseline_refresh_input_ref:
        record["baseline_refresh_input_ref"] = baseline_refresh_input_ref
    elif "baseline_refresh_input_ref" not in record:
        record["baseline_refresh_input_ref"] = ""
    save_project_config_json(config)


# project_config 中文：清空指定 session 槽位，供重新建立 baseline 或 current session 时显式重置。
def clear_session_registry(slot: str) -> None:
    config = load_project_config_json()
    registry = config.setdefault("session_registry", {})
    record = registry.setdefault(slot, {})
    record["thread_id"] = ""
    record["thread_path"] = ""
    record["status"] = ""
    record["updated_at"] = ""
    record["source"] = ""
    record["model"] = ""
    record["effort"] = ""
    if "phase" in record:
        record["phase"] = ""
    if "session_execution_instruction" in record:
        record["session_execution_instruction"] = ""
    if "operator_notes" in record:
        record["operator_notes"] = ""
    if "answered_questions" in record:
        record["answered_questions"] = []
    if "unclear_questions" in record:
        record["unclear_questions"] = []
    if "customer_followups" in record:
        record["customer_followups"] = []
    if "document_priority_understanding" in record:
        record["document_priority_understanding"] = ""
    if "current_project_understanding" in record:
        record["current_project_understanding"] = ""
    if "ready_for_doc_write" in record:
        record["ready_for_doc_write"] = False
    if "must_read_next" in record:
        record["must_read_next"] = []
    if "implementation_gaps" in record:
        record["implementation_gaps"] = []
    if "forked_from_thread_id" in record:
        record["forked_from_thread_id"] = ""
    save_project_config_json(config)


# project_config 中文：把当前运行状态统一写回配置，后续可替代分散 state 读取。
def update_runtime_state(
    current_project_id: str,
    current_run_id: str,
    current_task_file: str,
    current_status: str,
    current_task_id: str = "",
    current_task_json_file: str = "",
) -> None:
    config = load_project_config_json()
    runtime_state = config.setdefault("runtime_state", {})
    runtime_state["current_project_id"] = current_project_id
    runtime_state["current_run_id"] = current_run_id
    runtime_state["current_task_id"] = current_task_id
    runtime_state["current_task_file"] = current_task_file
    runtime_state["current_task_json_file"] = current_task_json_file
    runtime_state["current_status"] = current_status
    runtime_state["current_updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_project_config_json(config)


# project_config 中文：CLI 方式写入 runtime_state，供 shell 脚本统一更新状态。
def set_runtime_state_from_cli(argv: list[str]) -> int:
    if len(argv) not in {4, 5, 6}:
        print(
            "错误: --set-runtime 需要 4 到 6 个值: <project_id> <run_id> <task_file> <status> [task_id] [task_json_file]",
            file=sys.stderr,
        )
        return 2
    task_id = argv[4] if len(argv) >= 5 else ""
    task_json_file = argv[5] if len(argv) == 6 else ""
    update_runtime_state(argv[0], argv[1], argv[2], argv[3], task_id, task_json_file)
    return 0


# project_config 中文：直接运行本文件时，打印配置摘要、校验结果和当前 session registry，便于单文件测试。
def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--get":
        print(get_config_value(sys.argv[2]))
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "--set-runtime":
        return set_runtime_state_from_cli(sys.argv[2:])
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    cfg = load_project_config()
    state = load_runtime_state()
    logger.info("项目配置摘要开始")
    for line in describe_project_config(cfg):
        logger.info(line)
    logger.info("运行状态配置开始")
    for line in describe_runtime_state(state):
        logger.info(line)
    logger.info("运行状态配置结束")
    logger.info("Git 账户配置开始")
    for line in describe_git_account_config(cfg):
        logger.info(line)
    logger.info("Git 账户配置结束")
    logger.info("Codex 账户配置开始")
    for line in describe_codex_account_config(cfg):
        logger.info(line)
    logger.info("Codex 账户配置结束")
    logger.info("项目配置摘要结束")
    errors = validate_project_config(cfg)
    errors.extend(validate_runtime_state(cfg, state))
    logger.info("项目配置校验结果: %s", "通过" if not errors else "失败")
    if errors:
        for item in errors:
            logger.info("项目配置校验错误: %s", item)
    logger.info("项目会话注册表开始")
    for line in describe_session_registry(load_project_config_json().get("session_registry", {})):
        logger.info(line)
    logger.info("项目会话注册表结束")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
