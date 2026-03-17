#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.common_helpers import first_line
    from tools.project_config import (
        PROJECT_CONFIG_FILE,
        ProjectConfig,
        RuntimeState,
        get_app_server_session_id,
        load_project_config,
        load_project_config_json,
        load_runtime_state,
        load_unified_config,
        validate_project_config,
        validate_required_json_fields,
    )
    from tools.result_schema import ERR_CONFIG_BASE, ERR_RUNTIME_BASE, err, ok
except Exception:  # pragma: no cover
    from common_helpers import first_line  # type: ignore
    from project_config import (  # type: ignore
        PROJECT_CONFIG_FILE,
        ProjectConfig,
        RuntimeState,
        get_app_server_session_id,
        load_project_config,
        load_project_config_json,
        load_runtime_state,
        load_unified_config,
        validate_project_config,
        validate_required_json_fields,
    )
    from result_schema import ERR_CONFIG_BASE, ERR_RUNTIME_BASE, err, ok  # type: ignore


INIT_LOG_FILE = Path("init.log")
LOGGER_NAME = "qf.init"
GIT_SUBPROCESS_TIMEOUT_SEC = 15
logger = logging.getLogger(LOGGER_NAME)


@dataclass
class CmdResult:
    rc: int
    stdout: str
    stderr: str


@dataclass
class InitArgs:
    log_enabled: bool


@dataclass
class InitContext:
    cfg: ProjectConfig
    runtime_state: RuntimeState
    unified_config: dict[str, object]
    config_errors: list[str]
    run_id: str
    task_file: str
    task_status: str


@dataclass
class InitStepResult:
    reasons: list[str]
    status: dict[str, str]


INIT_DEFAULT_AGENTS_CONTENT = ""

INIT_DEFAULT_README_CONTENT = """# README

项目入口说明由 owner 后续补充。
"""

INIT_DEFAULT_TODO_CONTENT = """# TODO

后续待办由 owner 后续补充。
"""

INIT_DEFAULT_PROJECT_GUIDE_CONTENT = ""

INIT_DEFAULT_WORKFLOW_CONTENT = ""

INIT_DEFAULT_ENTITIES_CONTENT = ""

INIT_DEFAULT_FILE_INDEX_CONTENT = ""

INIT_DEFAULT_PROJECT_BOOTSTRAP_PROTOCOL_CONTENT = ""

INIT_DEFAULT_TOOLS_METHOD_FLOW_MAP_CONTENT = ""

INIT_DEFAULT_QUEUE_JSON_CONTENT = """{
  "items": []
}
"""

INIT_DEFAULT_TASK_SCHEMA_CONTENT = """{}
"""

INIT_DEFAULT_QUEUE_SCHEMA_CONTENT = """{}
"""

INIT_DEFAULT_PROJECT_CONFIG_TEMPLATE_CONTENT = """{
  "required": {
    "project_id": "your-project-id",
    "project_root": "/abs/path/to/your-project"
  },
  "git": {
    "remote_url": "https://github.com/your-org/your-project.git",
    "github_login": "your-github-login"
  },
  "bootstrap_state": {
    "is_inited": "N",
    "initialized_at": "",
    "initialized_by": "",
    "bootstrap_source": ""
  },
  "runtime_state": {
    "current_project_id": "your-project-id",
    "current_run_id": "",
    "current_task_id": "",
    "current_task_file": "",
    "current_task_json_file": "",
    "current_status": "",
    "current_updated_at": ""
  },
  "task_registry": {
    "active_task_json_file": "",
    "queue_json_file": "TASKS/QUEUE.json",
    "task_md_is_legacy_view": true,
    "queue_md_is_legacy_view": true
  },
  "session_registry": {
    "learn_session_baseline": {},
    "fork_current_session": {},
    "init_project_session": {
      "thread_id": "",
      "thread_path": "",
      "status": "",
      "updated_at": "",
      "source": "",
      "model": "",
      "effort": "",
      "phase": "",
      "can_write_owner_docs": false,
      "must_read_next": [],
      "why_not_ready": []
    },
    "current_summary": {
      "baseline_refresh_input_type": "",
      "baseline_refresh_input_ref": ""
    }
  }
}
"""


# init_tools_01 中文：解析 init 命令行参数，当前只允许 -log。
def init_tools_01_parse_args(argv: list[str]) -> InitArgs:
    log_enabled = False
    for arg in argv:
        if arg == "-log":
            log_enabled = True
            continue
        print(f"ERROR: unknown init option: {arg}", file=sys.stderr)
        print("Usage: python3 tools/init.py [-log]", file=sys.stderr)
        raise SystemExit(2)
    return InitArgs(log_enabled=log_enabled)


# init_tools_02 中文：按标准 logging 格式初始化 init 日志器。
def init_tools_02_build_logger(log_enabled: bool) -> logging.Logger:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_enabled:
        file_handler = logging.FileHandler(INIT_LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


# init_tools_03 中文：关闭并清理 init 日志器。
def init_tools_03_close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


# init_tools_04 中文：执行直接命令并返回结构化结果。
def init_tools_04_run_cmd(args: list[str], cwd: Path | None = None) -> CmdResult:
    try:
        cp = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
        return CmdResult(rc=int(cp.returncode), stdout=cp.stdout or "", stderr=cp.stderr or "")
    except subprocess.TimeoutExpired as exc:
        return CmdResult(rc=124, stdout=exc.stdout or "", stderr=exc.stderr or "")


# init_tools_05 中文：通过 shell 执行命令字符串并返回结构化结果。
def init_tools_05_run_shell(cmd: str, cwd: Path | None = None) -> CmdResult:
    try:
        cp = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
            timeout=GIT_SUBPROCESS_TIMEOUT_SEC,
        )
        return CmdResult(rc=int(cp.returncode), stdout=cp.stdout or "", stderr=cp.stderr or "")
    except subprocess.TimeoutExpired as exc:
        return CmdResult(rc=124, stdout=exc.stdout or "", stderr=exc.stderr or "")


# init_tools_06 中文：从 project_config 统一出口读取完整项目配置视图中的结构化项目配置。
def init_tools_06_load_project_config() -> ProjectConfig:
    return load_project_config()


# init_tools_07 中文：从 project_config 统一出口读取完整统一配置 JSON。
def init_tools_07_load_unified_config() -> dict[str, object]:
    return load_unified_config()


# init_tools_08 中文：统一输出单条 init 日志。
def init_tools_08_log(logger: logging.Logger, message: str) -> None:
    logger.info(message)


# init_tools_09 中文：格式化步骤标题日志。
def init_tools_09_log_step(logger: logging.Logger, index: int, total: int, title: str, desc: str) -> None:
    logger.info(f"==================== INIT_STEP[{index}/{total}] {title} ====================")
    logger.info(f"INIT_STEP_DESC: {desc}")


# init_tools_10 中文：确保目录存在，不存在时自动创建并设为标准目录权限。
def init_tools_10_ensure_dir(path: Path) -> str:
    if path.exists():
        return "ok"
    path.mkdir(parents=True, exist_ok=True, mode=0o755)
    os.chmod(path, 0o755)
    return "created"


# init_tools_11 中文：确保文件存在，不存在时写入最小骨架并设为标准文件权限。
def init_tools_11_ensure_file(path: Path, content: str) -> str:
    if path.exists():
        return "ok"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o644)
    return "created"


# init_tools_14 中文：确保 project_config 模板和最小配置存在，避免新项目第一次运行 init 就因缺配置失败。
def init_tools_14_ensure_project_config_bootstrap() -> None:
    template_path = PROJECT_CONFIG_FILE.with_name("project_config.template.json")
    init_tools_11_ensure_file(template_path, INIT_DEFAULT_PROJECT_CONFIG_TEMPLATE_CONTENT)
    if PROJECT_CONFIG_FILE.exists():
        return
    project_root = Path.cwd().resolve()
    project_id = project_root.name
    config = json.loads(template_path.read_text(encoding="utf-8"))
    required = config.setdefault("required", {})
    required["project_id"] = project_id
    required["project_root"] = str(project_root)
    bootstrap_state = config.setdefault("bootstrap_state", {})
    bootstrap_state["is_inited"] = "N"
    bootstrap_state["initialized_at"] = ""
    bootstrap_state["initialized_by"] = ""
    bootstrap_state["bootstrap_source"] = ""
    runtime_state = config.setdefault("runtime_state", {})
    runtime_state["current_project_id"] = project_id
    runtime_state["current_run_id"] = ""
    runtime_state["current_task_id"] = ""
    runtime_state["current_task_file"] = ""
    runtime_state["current_task_json_file"] = ""
    runtime_state["current_status"] = ""
    runtime_state["current_updated_at"] = ""
    PROJECT_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(PROJECT_CONFIG_FILE, 0o644)


def init_tools_15_ensure_target_project_config_bootstrap(project_root: Path) -> tuple[str, str]:
    tools_dir = project_root / "tools"
    template_path = tools_dir / "project_config.template.json"
    template_status = init_tools_11_ensure_file(template_path, INIT_DEFAULT_PROJECT_CONFIG_TEMPLATE_CONTENT)
    config_path = tools_dir / "project_config.json"
    if config_path.exists():
        return template_status, "ok"
    project_id = project_root.name
    config = json.loads(template_path.read_text(encoding="utf-8"))
    required = config.setdefault("required", {})
    required["project_id"] = project_id
    required["project_root"] = str(project_root)
    bootstrap_state = config.setdefault("bootstrap_state", {})
    bootstrap_state["is_inited"] = "N"
    bootstrap_state["initialized_at"] = ""
    bootstrap_state["initialized_by"] = ""
    bootstrap_state["bootstrap_source"] = ""
    runtime_state = config.setdefault("runtime_state", {})
    runtime_state["current_project_id"] = project_id
    runtime_state["current_run_id"] = ""
    runtime_state["current_task_id"] = ""
    runtime_state["current_task_file"] = ""
    runtime_state["current_task_json_file"] = ""
    runtime_state["current_status"] = ""
    runtime_state["current_updated_at"] = ""
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(config_path, 0o644)
    return template_status, "created"


# 1001 中文：第一步，读取并校验项目配置文件。
def init_step_01_load_context(logger: logging.Logger) -> InitContext:
    init_tools_09_log_step(logger, 1, 5, "读取配置文件", "调用 project_config.py 读取统一配置、校验必填字段，并打印完整配置JSON。")
    init_tools_14_ensure_project_config_bootstrap()
    cfg = init_tools_06_load_project_config()
    raw_config = load_project_config_json()
    unified_config = init_tools_07_load_unified_config()
    runtime_state = RuntimeState(
        current_project_id="",
        current_run_id="",
        current_task_id="",
        current_task_file="",
        current_task_json_file="",
        current_status="",
        current_updated_at="",
    )
    errors = list(
        dict.fromkeys(
            validate_required_json_fields(raw_config)
            + validate_project_config(cfg, allow_bootstrap_missing=True)
        )
    )
    run_id = runtime_state.current_run_id
    task_file = runtime_state.current_task_file
    task_status = runtime_state.current_status or "active"
    init_tools_08_log(logger, f"INIT_CONFIG_STATUS: {'ok' if not errors else 'invalid'}")
    if errors:
        for error in errors:
            init_tools_08_log(logger, f"INIT_CONFIG_ERROR: {error}")
    init_tools_08_log(logger, "INIT_UNIFIED_CONFIG_JSON_START")
    for line in json.dumps(unified_config, ensure_ascii=False, indent=2).splitlines():
        init_tools_08_log(logger, line)
    init_tools_08_log(logger, "INIT_UNIFIED_CONFIG_JSON_END")
    return InitContext(
        cfg=cfg,
        runtime_state=runtime_state,
        unified_config=unified_config,
        config_errors=errors,
        run_id=run_id,
        task_file=task_file,
        task_status=task_status,
    )


# init_tools_12 中文：在配置读取完成后，加载当前 runtime_state 作为后续步骤上下文。
def init_tools_12_load_runtime_state(context: InitContext, logger: logging.Logger) -> InitContext:
    runtime_state = load_runtime_state()
    context.runtime_state = runtime_state
    context.run_id = runtime_state.current_run_id
    context.task_file = runtime_state.current_task_file
    context.task_status = runtime_state.current_status or "active"
    init_tools_08_log(logger, f"INIT_RUNTIME_PROJECT_ID: {runtime_state.current_project_id or '(none)'}")
    init_tools_08_log(logger, f"INIT_RUN_ID: {context.run_id or '(none)'}")
    init_tools_08_log(logger, f"INIT_TASK_FILE: {context.task_file or '(none)'}")
    init_tools_08_log(logger, f"INIT_TASK_STATUS: {context.task_status}")
    return context


# 1002 中文：第二步，检查项目路径和关键 owner docs。
def init_step_02_check_project_files(context: InitContext, logger: logging.Logger) -> InitStepResult:
    init_tools_09_log_step(logger, 2, 5, "确保项目骨架存在", "项目根目录必须存在；缺失时自动创建最小标准协议骨架。")
    reasons: list[str] = []
    status: dict[str, str] = {}

    if context.cfg.project_root.exists():
        status["PROJECT_ROOT"] = "ok"
    else:
        status["PROJECT_ROOT"] = "missing_root"
        reasons.append("MISSING_PROJECT_ROOT")

    if status["PROJECT_ROOT"] == "ok":
        status["TOOLS_DIR"] = init_tools_10_ensure_dir(context.cfg.tools_dir)
        status["DOCS_DIR"] = init_tools_10_ensure_dir(context.cfg.docs_dir)
        status["TASKS_DIR"] = init_tools_10_ensure_dir(context.cfg.project_root / "TASKS")
        status["REPORTS_DIR"] = init_tools_10_ensure_dir(context.cfg.project_root / "reports")
        status["CHATLOGS_DIR"] = init_tools_10_ensure_dir(context.cfg.project_root / "chatlogs")
        status["APPSERVER_LOG_DIR"] = init_tools_10_ensure_dir(context.cfg.project_root / "appserver_log")
        status["AGENTS_FILE"] = init_tools_11_ensure_file(context.cfg.agents_file, INIT_DEFAULT_AGENTS_CONTENT)
        status["README_FILE"] = init_tools_11_ensure_file(context.cfg.project_root / "README.md", INIT_DEFAULT_README_CONTENT)
        status["TODO_FILE"] = init_tools_11_ensure_file(context.cfg.project_root / "todo.md", INIT_DEFAULT_TODO_CONTENT)
        status["PROJECT_GUIDE_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_guide_file,
            INIT_DEFAULT_PROJECT_GUIDE_CONTENT,
        )
        status["WORKFLOW_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "docs/WORKFLOW.md",
            INIT_DEFAULT_WORKFLOW_CONTENT,
        )
        status["ENTITIES_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "docs/ENTITIES.md",
            INIT_DEFAULT_ENTITIES_CONTENT,
        )
        status["FILE_INDEX_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "docs/FILE_INDEX.md",
            INIT_DEFAULT_FILE_INDEX_CONTENT,
        )
        status["PROJECT_BOOTSTRAP_PROTOCOL_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "docs/PROJECT_BOOTSTRAP_PROTOCOL.md",
            INIT_DEFAULT_PROJECT_BOOTSTRAP_PROTOCOL_CONTENT,
        )
        status["TOOLS_METHOD_FLOW_MAP_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "docs/TOOLS_METHOD_FLOW_MAP.md",
            INIT_DEFAULT_TOOLS_METHOD_FLOW_MAP_CONTENT,
        )
        status["QUEUE_JSON_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "TASKS/QUEUE.json",
            INIT_DEFAULT_QUEUE_JSON_CONTENT,
        )
        status["TASK_SCHEMA_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "TASKS/_SCHEMA.task.json",
            INIT_DEFAULT_TASK_SCHEMA_CONTENT,
        )
        status["QUEUE_SCHEMA_FILE"] = init_tools_11_ensure_file(
            context.cfg.project_root / "TASKS/_SCHEMA.queue.json",
            INIT_DEFAULT_QUEUE_SCHEMA_CONTENT,
        )
        template_status, config_status = init_tools_15_ensure_target_project_config_bootstrap(context.cfg.project_root)
        status["PROJECT_CONFIG_TEMPLATE_FILE"] = template_status
        status["PROJECT_CONFIG_FILE"] = config_status

    init_tools_08_log(logger, f"INIT_PROJECT_PATH_STATUS: {status['PROJECT_ROOT']}")
    init_tools_08_log(logger, f"INIT_TOOLS_DIR_STATUS: {status['TOOLS_DIR']}")
    init_tools_08_log(logger, f"INIT_DOCS_DIR_STATUS: {status['DOCS_DIR']}")
    init_tools_08_log(logger, f"INIT_TASKS_DIR_STATUS: {status['TASKS_DIR']}")
    init_tools_08_log(logger, f"INIT_REPORTS_DIR_STATUS: {status['REPORTS_DIR']}")
    init_tools_08_log(logger, f"INIT_CHATLOGS_DIR_STATUS: {status['CHATLOGS_DIR']}")
    init_tools_08_log(logger, f"INIT_APPSERVER_LOG_DIR_STATUS: {status['APPSERVER_LOG_DIR']}")
    init_tools_08_log(logger, f"INIT_AGENTS_STATUS: {status['AGENTS_FILE']}")
    init_tools_08_log(logger, f"INIT_README_STATUS: {status['README_FILE']}")
    init_tools_08_log(logger, f"INIT_TODO_STATUS: {status['TODO_FILE']}")
    init_tools_08_log(logger, f"INIT_PROJECT_GUIDE_STATUS: {status['PROJECT_GUIDE_FILE']}")
    init_tools_08_log(logger, f"INIT_WORKFLOW_STATUS: {status['WORKFLOW_FILE']}")
    init_tools_08_log(logger, f"INIT_ENTITIES_STATUS: {status['ENTITIES_FILE']}")
    init_tools_08_log(logger, f"INIT_FILE_INDEX_STATUS: {status['FILE_INDEX_FILE']}")
    init_tools_08_log(logger, f"INIT_PROJECT_BOOTSTRAP_PROTOCOL_STATUS: {status['PROJECT_BOOTSTRAP_PROTOCOL_FILE']}")
    init_tools_08_log(logger, f"INIT_TOOLS_METHOD_FLOW_MAP_STATUS: {status['TOOLS_METHOD_FLOW_MAP_FILE']}")
    init_tools_08_log(logger, f"INIT_QUEUE_JSON_STATUS: {status['QUEUE_JSON_FILE']}")
    init_tools_08_log(logger, f"INIT_TASK_SCHEMA_STATUS: {status['TASK_SCHEMA_FILE']}")
    init_tools_08_log(logger, f"INIT_QUEUE_SCHEMA_STATUS: {status['QUEUE_SCHEMA_FILE']}")
    init_tools_08_log(logger, f"INIT_PROJECT_CONFIG_TEMPLATE_STATUS: {status['PROJECT_CONFIG_TEMPLATE_FILE']}")
    init_tools_08_log(logger, f"INIT_PROJECT_CONFIG_STATUS: {status['PROJECT_CONFIG_FILE']}")
    return InitStepResult(reasons=reasons, status=status)


# 1003 中文：第三步，检查 Codex、app-server 和当前 session。
def init_step_03_check_codex_runtime(context: InitContext, logger: logging.Logger) -> InitStepResult:
    init_tools_09_log_step(logger, 3, 5, "检查 Codex、app-server 和当前会话前提", "检查 codex CLI、app-server 能力、认证状态以及 session_id。")
    reasons: list[str] = []
    status: dict[str, str] = {}
    codex_available = init_tools_05_run_shell(f"command -v {context.cfg.codex_bin} >/dev/null 2>&1").rc == 0
    codex_version = "(not installed)"
    if codex_available:
        codex_version = first_line(init_tools_04_run_cmd([context.cfg.codex_bin, "--version"]).stdout, codex_version)
    else:
        reasons.append("CODEX_NOT_INSTALLED")

    app_server_status = "missing"
    if codex_available:
        probe = init_tools_04_run_cmd([context.cfg.codex_bin, "app-server", "--help"])
        app_server_status = "ok" if probe.rc == 0 else "unavailable"
        if app_server_status != "ok":
            reasons.append("APP_SERVER_UNAVAILABLE")

    session_id = get_app_server_session_id(context.cfg)

    codex_auth_status = "unknown"
    if codex_available and context.cfg.codex_login_status_command.strip():
        auth_probe = init_tools_05_run_shell(context.cfg.codex_login_status_command)
        codex_auth_status = "ready" if auth_probe.rc == 0 else "not_ready"

    status["CODEX_CLI_STATUS"] = "ok" if codex_available else "missing"
    status["CODEX_VERSION"] = codex_version
    status["CODEX_AUTH_STATUS"] = codex_auth_status
    status["APP_SERVER_STATUS"] = app_server_status
    status["APP_SERVER_SESSION_STATUS"] = "present" if session_id else "missing"
    status["APP_SERVER_SESSION_ID"] = session_id or "(none)"
    init_tools_08_log(logger, f"INIT_CODEX_CLI_STATUS: {status['CODEX_CLI_STATUS']}")
    init_tools_08_log(logger, f"INIT_CODEX_VERSION: {status['CODEX_VERSION']}")
    init_tools_08_log(logger, f"INIT_CODEX_AUTH_STATUS: {status['CODEX_AUTH_STATUS']}")
    init_tools_08_log(logger, f"INIT_APP_SERVER_STATUS: {status['APP_SERVER_STATUS']}")
    init_tools_08_log(logger, f"INIT_APP_SERVER_SESSION_STATUS: {status['APP_SERVER_SESSION_STATUS']}")
    init_tools_08_log(logger, f"INIT_APP_SERVER_SESSION_ID: {status['APP_SERVER_SESSION_ID']}")
    return InitStepResult(reasons=reasons, status=status)


# 1004 中文：第四步，检查 git 仓库、账号、远端和工作区。
def init_step_04_check_git_runtime(context: InitContext, logger: logging.Logger) -> InitStepResult:
    init_tools_09_log_step(logger, 4, 5, "检查 git 仓库、账号、远端和工作区状态", "检查 git 仓库、git 账号、remote 连通性和当前工作区阻塞情况。")
    reasons: list[str] = []
    status: dict[str, str] = {}
    diff_preview: list[str] = []

    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查 git 命令是否存在")
    git_available = init_tools_05_run_shell("command -v git >/dev/null 2>&1", cwd=context.cfg.git_repo_path).rc == 0
    if not git_available:
        reasons.append("GIT_NOT_INSTALLED")
        status["GIT_STATUS"] = "missing"
        return InitStepResult(reasons=reasons, status=status)

    status["GIT_STATUS"] = "ok"
    status["GIT_VERSION"] = first_line(init_tools_04_run_cmd(["git", "--version"], cwd=context.cfg.git_repo_path).stdout, "(missing)")

    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查当前目录是否为 git 仓库")
    repo_check = init_tools_04_run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=context.cfg.git_repo_path)
    repo_ok = repo_check.rc == 0
    status["GIT_REPO_STATUS"] = "ok" if repo_ok else "not_repo"
    if not repo_ok:
        reasons.append("GIT_REPO_INVALID")
        init_tools_08_log(logger, f"INIT_GIT_STATUS: {status['GIT_STATUS']}")
        init_tools_08_log(logger, f"INIT_GIT_VERSION: {status['GIT_VERSION']}")
        init_tools_08_log(logger, f"INIT_GIT_REPO_STATUS: {status['GIT_REPO_STATUS']}")
        return InitStepResult(reasons=reasons, status=status)

    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 读取当前分支")
    branch = first_line(init_tools_04_run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=context.cfg.git_repo_path).stdout, "unknown")
    configured_remote_url = context.cfg.git_remote_url.strip()
    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 读取 git remote")
    remote = first_line(init_tools_04_run_cmd(["git", "remote", "get-url", context.cfg.git_remote_name], cwd=context.cfg.git_repo_path).stdout, "(missing)")
    remote_ok = remote != "(missing)"
    gh_auth_status = "unknown"
    if context.cfg.git_auth_check_command.strip():
        init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查 GitHub 认证状态")
        auth_probe = init_tools_05_run_shell(context.cfg.git_auth_check_command, cwd=context.cfg.git_repo_path)
        if auth_probe.rc == 124:
            gh_auth_status = "timeout"
            reasons.append("GIT_AUTH_CHECK_TIMEOUT")
        else:
            gh_auth_status = "logged_in" if auth_probe.rc == 0 else "not_logged_in"

    connectivity_status = "skipped"
    if remote_ok:
        init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查 remote 连通性")
        probe = init_tools_05_run_shell(f"GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code {context.cfg.git_remote_name} HEAD >/dev/null 2>&1", cwd=context.cfg.git_repo_path)
        if probe.rc == 124:
            connectivity_status = "timeout"
            reasons.append("GIT_REMOTE_CONNECTIVITY_TIMEOUT")
        else:
            connectivity_status = "ok" if probe.rc == 0 else "failed"

    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查 git 操作状态")
    git_dir = Path(first_line(init_tools_04_run_cmd(["git", "rev-parse", "--git-dir"], cwd=context.cfg.git_repo_path).stdout, ".git"))
    git_operation = "none"
    if (git_dir / "MERGE_HEAD").is_file():
        git_operation = "merge_in_progress"
    elif (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir():
        git_operation = "rebase_in_progress"
    elif (git_dir / "CHERRY_PICK_HEAD").is_file():
        git_operation = "cherry_pick_in_progress"
    elif (git_dir / "REVERT_HEAD").is_file():
        git_operation = "revert_in_progress"

    init_tools_08_log(logger, "INIT_GIT_SUBSTEP: 检查工作区是否干净")
    worktree_dirty = init_tools_05_run_shell("! git diff --quiet || ! git diff --cached --quiet || [[ -n \"$(git ls-files --others --exclude-standard)\" ]]", cwd=context.cfg.git_repo_path).rc == 0
    staged_count = first_line(init_tools_05_run_shell("git diff --cached --name-only | wc -l | tr -d '[:space:]'", cwd=context.cfg.git_repo_path).stdout, "0")
    unstaged_count = first_line(init_tools_05_run_shell("git diff --name-only | wc -l | tr -d '[:space:]'", cwd=context.cfg.git_repo_path).stdout, "0")
    untracked_count = first_line(init_tools_05_run_shell("git ls-files --others --exclude-standard | wc -l | tr -d '[:space:]'", cwd=context.cfg.git_repo_path).stdout, "0")
    diff_preview = [line for line in init_tools_05_run_shell("git status --short | head -n 20", cwd=context.cfg.git_repo_path).stdout.splitlines() if line.strip()]

    if not remote_ok:
        reasons.append("GIT_REMOTE_MISSING")
    if gh_auth_status == "not_logged_in":
        reasons.append("GIT_AUTH_NOT_READY")
    if connectivity_status == "failed":
        reasons.append("GIT_REMOTE_CONNECTIVITY_FAILED")
    if git_operation != "none":
        reasons.append("GIT_OPERATION_IN_PROGRESS")
    if worktree_dirty:
        reasons.append("WORKTREE_DIRTY")

    status["GIT_BRANCH"] = branch
    status["GIT_REMOTE_CONFIG"] = configured_remote_url or "(missing)"
    status["GIT_REMOTE_ORIGIN"] = remote
    status["GIT_REMOTE_STATUS"] = "ok" if remote_ok else "missing"
    status["GIT_AUTH_STATUS"] = gh_auth_status
    status["GIT_CONNECTIVITY_STATUS"] = connectivity_status
    status["GIT_OPERATION"] = git_operation
    status["GIT_DIFF_SUMMARY"] = f"staged={staged_count},unstaged={unstaged_count},untracked={untracked_count}"

    init_tools_08_log(logger, f"INIT_GIT_STATUS: {status['GIT_STATUS']}")
    init_tools_08_log(logger, f"INIT_GIT_VERSION: {status['GIT_VERSION']}")
    init_tools_08_log(logger, f"INIT_GIT_REPO_STATUS: {status['GIT_REPO_STATUS']}")
    init_tools_08_log(logger, f"INIT_BRANCH: {status['GIT_BRANCH']}")
    init_tools_08_log(logger, f"INIT_REMOTE_CONFIG: {status['GIT_REMOTE_CONFIG']}")
    init_tools_08_log(logger, f"INIT_REMOTE_ORIGIN: {status['GIT_REMOTE_ORIGIN']}")
    init_tools_08_log(logger, f"INIT_GIT_REMOTE_STATUS: {status['GIT_REMOTE_STATUS']}")
    init_tools_08_log(logger, f"INIT_GIT_AUTH_STATUS: {status['GIT_AUTH_STATUS']}")
    init_tools_08_log(logger, f"INIT_GIT_CONNECTIVITY_STATUS: {status['GIT_CONNECTIVITY_STATUS']}")
    init_tools_08_log(logger, f"INIT_GIT_OPERATION: {status['GIT_OPERATION']}")
    init_tools_08_log(logger, f"INIT_DIFF_SUMMARY: {status['GIT_DIFF_SUMMARY']}")
    if diff_preview:
        init_tools_08_log(logger, "INIT_DIFF_FILES_START")
        for line in diff_preview:
            init_tools_08_log(logger, line)
        init_tools_08_log(logger, "INIT_DIFF_FILES_END")
    else:
        init_tools_08_log(logger, "INIT_DIFF_FILES: (clean or unavailable)")
    return InitStepResult(reasons=reasons, status=status)


# 1005 中文：第五步，汇总结果并给出最终状态和下一步动作。
def init_step_05_finalize(
    context: InitContext,
    project_result: InitStepResult,
    codex_result: InitStepResult,
    git_result: InitStepResult,
    logger: logging.Logger,
) -> dict[str, object]:
    init_tools_09_log_step(logger, 5, 5, "汇总自动化前置检查结果并给出下一步", "汇总前四步结果，输出最终状态、原因代码和下一步动作。")
    status, reason_codes, summary_block = init_tools_10_finalize_status(
        context,
        project_result.reasons + codex_result.reasons + git_result.reasons,
    )
    for line in summary_block.splitlines():
        init_tools_08_log(logger, line)
    init_tools_08_log(logger, f"INIT_STATUS: {status}")
    init_tools_08_log(logger, f"INIT_REASON_CODES: {reason_codes}")
    if status == "ready":
        return ok(
            {
                "status": status,
                "reason_codes": reason_codes,
                "project_id": context.cfg.project_id,
                "run_id": context.run_id,
                "task_file": context.task_file,
                "task_status": context.task_status,
            }
        )
    return err(
        ERR_RUNTIME_BASE + 1,
        f"init {status}: {reason_codes}",
        {
            "status": status,
            "reason_codes": reason_codes,
            "project_id": context.cfg.project_id,
            "run_id": context.run_id,
            "task_file": context.task_file,
            "task_status": context.task_status,
        },
    )


# init_tools_13 中文：汇总结果并计算最终状态。
def init_tools_10_finalize_status(context: InitContext, reasons: list[str]) -> tuple[str, str, str]:
    blocking_codes = {
        "MISSING_PROJECT_ROOT",
        "MISSING_AGENTS_FILE",
        "MISSING_PROJECT_GUIDE_FILE",
        "CODEX_NOT_INSTALLED",
        "APP_SERVER_UNAVAILABLE",
        "GIT_NOT_INSTALLED",
        "GIT_REPO_INVALID",
        "GIT_REMOTE_MISSING",
        "GIT_REMOTE_CONNECTIVITY_FAILED",
    }
    if not reasons:
        next_step = "python3 tools/learn.py"
        status = "ready"
    elif any(code in blocking_codes for code in reasons):
        next_step = "fix init blockers before learn"
        status = "blocked"
    elif reasons == ["WORKTREE_DIRTY"]:
        next_step = (
            "工作区有未提交改动；可运行 tools/gitclient.py --commit 提交当前改动，"
            "或运行 tools/gitclient.py --rollback-last / --rollback-commit <sha> 回滚后重跑 tools/init.py"
        )
        status = "needs_fix"
    else:
        next_step = "fix init warnings then rerun python3 tools/init.py"
        status = "needs_fix"
    summary = (
        f"INIT_RUN_CONTEXT: project_id={context.cfg.project_id},run_id={context.run_id or '(none)'},task={context.task_file or '(none)'},status={context.task_status}\n"
        f"INIT_NEXT: {next_step}"
    )
    return status, ",".join(reasons) if reasons else "none", summary


# 1006 中文：执行 init 主流程，main 只负责串起 5 个业务步骤。
def run_init(argv: list[str]) -> dict[str, object]:
    args = init_tools_01_parse_args(argv)
    logger = init_tools_02_build_logger(args.log_enabled)
    try:
        if args.log_enabled:
            init_tools_08_log(logger, f"INIT_LOG_FILE: {INIT_LOG_FILE}")
        context = init_step_01_load_context(logger)
        if context.config_errors:
            init_tools_08_log(logger, "==================== INIT_STEP[5/5] 汇总自动化前置检查结果并给出下一步 ====================")
            init_tools_08_log(logger, "INIT_STEP_DESC: 配置文件必填项不完整，停止后续检查。")
            init_tools_08_log(
                logger,
                f"INIT_RUN_CONTEXT: project_id={context.cfg.project_id or '(none)'},run_id=(none),task=(none),status=invalid_config",
            )
            init_tools_08_log(logger, "INIT_NEXT: 修复 tools/project_config.json 必填字段后重跑 python3 tools/init.py")
            init_tools_08_log(logger, "INIT_STATUS: blocked")
            init_tools_08_log(logger, "INIT_REASON_CODES: INVALID_PROJECT_CONFIG")
            return err(
                ERR_CONFIG_BASE + 1,
                "project_config invalid: INVALID_PROJECT_CONFIG",
                {"status": "blocked", "reason_codes": "INVALID_PROJECT_CONFIG"},
            )
        context = init_tools_12_load_runtime_state(context, logger)
        project_result = init_step_02_check_project_files(context, logger)
        codex_result = init_step_03_check_codex_runtime(context, logger)
        git_result = init_step_04_check_git_runtime(context, logger)
        return init_step_05_finalize(context, project_result, codex_result, git_result, logger)
    finally:
        if args.log_enabled:
            init_tools_08_log(logger, "INIT_LOG_END")
        init_tools_03_close_logger(logger)


def main(argv: list[str]) -> int:
    result = run_init(argv)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if int(result.get("err_code", 1)) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
