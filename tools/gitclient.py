#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.project_config import load_unified_config
    from tools.result_schema import ERR_CONFIG_BASE, ERR_RUNTIME_BASE, err, ok
    from tools.taskclient import load_active_task
except Exception:  # pragma: no cover
    from project_config import load_unified_config  # type: ignore
    from result_schema import ERR_CONFIG_BASE, ERR_RUNTIME_BASE, err, ok  # type: ignore
    from taskclient import load_active_task  # type: ignore


LOGGER_NAME = "qf.gitclient"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logger = logging.getLogger(LOGGER_NAME)

ERR_GIT_NOT_READY = ERR_RUNTIME_BASE + 1
ERR_GIT_DIRTY = ERR_RUNTIME_BASE + 2
ERR_GIT_NO_CHANGES = ERR_RUNTIME_BASE + 3
ERR_GIT_COMMAND_FAILED = ERR_RUNTIME_BASE + 4
ERR_GH_COMMAND_FAILED = ERR_RUNTIME_BASE + 5
ERR_INVALID_INPUT = ERR_CONFIG_BASE + 1
PR_MERGE_WAIT_TIMEOUT_SEC = 180
PR_MERGE_WAIT_INTERVAL_SEC = 3
PR_AUTO_MERGE_GRACE_SEC = 20


class GitClientError(RuntimeError):
    pass


# gitclient 中文：统一初始化日志，保证普通窗口直接运行时也有时间戳。
def build_logger() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


# gitclient 中文：读取统一配置，拿到 git 相关运行参数。
def load_git_context() -> dict[str, Any]:
    unified = load_unified_config()
    git_cfg = dict(unified["git"])
    required = dict(unified["required"])
    project_id = str(required.get("project_id", "")).strip()
    project_root = Path(str(required.get("project_root", ""))).resolve()
    repo_path = Path(str(git_cfg.get("repo_path", ""))).resolve()
    remote_name = str(git_cfg.get("remote_name", "")).strip()
    remote_url = str(git_cfg.get("remote_url", "")).strip()
    github_login = str(git_cfg.get("github_login", "")).strip()
    auth_check_command = str(git_cfg.get("auth_check_command", "")).strip()
    return {
        "project_id": project_id,
        "project_root": project_root,
        "repo_path": repo_path,
        "remote_name": remote_name,
        "remote_url": remote_url,
        "github_login": github_login,
        "auth_check_command": auth_check_command,
    }


# gitclient 中文：解析提交说明；优先用 --commit，其次 active task JSON 的 title/task_id，再回退到 runtime_state 与时间戳。
def resolve_active_task_message() -> str:
    try:
        task = load_active_task()
    except Exception:
        return ""
    title = str(task.get("title", "")).strip()
    task_id = str(task.get("task_id", "")).strip()
    if title and task_id:
        return f"{task_id}: {title}"
    if title:
        return title
    if task_id:
        return task_id
    return ""


def resolve_commit_message(raw_message: str | None) -> str:
    if raw_message is not None and str(raw_message).strip():
        return str(raw_message).strip()
    active_task_message = resolve_active_task_message()
    if active_task_message:
        return active_task_message
    unified = load_unified_config()
    runtime_state = dict(unified.get("runtime_state", {}))
    current_task_id = str(runtime_state.get("current_task_id", "")).strip()
    current_task_file = str(runtime_state.get("current_task_file", "")).strip()
    if current_task_file:
        return current_task_file
    if current_task_id:
        return current_task_id
    current_run_id = str(runtime_state.get("current_run_id", "")).strip()
    if current_run_id:
        return current_run_id
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"手动提交{ts}"


# gitclient 中文：执行 git 或 gh 命令，并返回原始执行结果。
def run_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    logger.info("GITCLIENT_CMD: %s", " ".join(args))
    return subprocess.run(args, cwd=str(cwd), text=True, capture_output=True)


# gitclient 中文：执行 shell 检查命令，主要用于 gh 认证状态。
def run_shell(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    logger.info("GITCLIENT_SHELL: %s", command)
    return subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, shell=True)


# gitclient 中文：把失败命令包装成统一错误结果。
def command_err(err_code: int, err_desc: str, proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return err(
        err_code,
        err_desc,
        {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        },
    )


# gitclient 中文：判断 gh pr merge 失败是否属于“需要改成 auto merge”的分支策略场景。
def should_queue_auto_merge(proc: subprocess.CompletedProcess[str]) -> bool:
    stderr = (proc.stderr or "").lower()
    return (
        ("not mergeable" in stderr and "--auto" in stderr)
        or "add the `--auto` flag" in stderr
        or "required status check" in stderr
        or "base branch policy prohibits the merge" in stderr
    )


# gitclient 中文：查询 PR 当前状态，供合并闭环判断使用。
def get_pr_state(pr_url: str, repo_path: Path) -> dict[str, Any]:
    proc = run_cmd(["gh", "pr", "view", pr_url, "--json", "state,mergedAt,mergeStateStatus,autoMergeRequest"], repo_path)
    if proc.returncode != 0:
        return command_err(ERR_GH_COMMAND_FAILED, "查询PR状态失败", proc)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return err(ERR_GH_COMMAND_FAILED, "PR状态返回不是合法JSON", {"stdout": proc.stdout.strip()})
    return ok(
        {
            "state": str(payload.get("state", "")).strip(),
            "merged_at": payload.get("mergedAt") or "",
            "merge_state_status": str(payload.get("mergeStateStatus", "")).strip(),
            "auto_merge_enabled": bool(payload.get("autoMergeRequest")),
        }
    )


# gitclient 中文：等待 PR 真正进入 MERGED 状态，只有真合并后才允许继续同步本地 main。
def wait_for_pr_merged(pr_url: str, repo_path: Path) -> dict[str, Any]:
    deadline = time.time() + PR_MERGE_WAIT_TIMEOUT_SEC
    last_data: dict[str, Any] = {}
    blocked_since = 0.0
    while time.time() < deadline:
        state_result = get_pr_state(pr_url, repo_path)
        if state_result["err_code"] != 0:
            return state_result
        last_data = state_result["data"]
        state = str(last_data.get("state", "")).strip().upper()
        merge_state = str(last_data.get("merge_state_status", "")).strip().upper()
        if state == "MERGED" and last_data.get("merged_at"):
            return ok(last_data)
        if merge_state == "DIRTY":
            now = time.time()
            if blocked_since <= 0:
                blocked_since = now
            if now - blocked_since >= PR_AUTO_MERGE_GRACE_SEC:
                return err(
                    ERR_GH_COMMAND_FAILED,
                    "PR当前不可合并",
                    {
                        "pr_url": pr_url,
                        "state": last_data.get("state", ""),
                        "merge_state_status": last_data.get("merge_state_status", ""),
                        "auto_merge_enabled": last_data.get("auto_merge_enabled", False),
                    },
                )
        else:
            blocked_since = 0.0
        time.sleep(PR_MERGE_WAIT_INTERVAL_SEC)
    return err(
        ERR_GH_COMMAND_FAILED,
        "等待PR合并超时",
        {
            "pr_url": pr_url,
            "state": last_data.get("state", ""),
            "merge_state_status": last_data.get("merge_state_status", ""),
            "auto_merge_enabled": last_data.get("auto_merge_enabled", False),
        },
    )


# gitclient 中文：执行 PR 合并闭环；支持 auto merge，但必须确认最终已经真正 MERGED。
def merge_pr_and_wait(pr_url: str, repo_path: Path, err_desc: str) -> dict[str, Any]:
    direct_merge_proc = run_cmd(["gh", "pr", "merge", pr_url, "--squash", "--delete-branch"], repo_path)
    if direct_merge_proc.returncode == 0:
        wait_result = wait_for_pr_merged(pr_url, repo_path)
        if wait_result["err_code"] != 0:
            return wait_result
        wait_result["data"]["merge_mode"] = "direct"
        return wait_result

    if not should_queue_auto_merge(direct_merge_proc):
        return command_err(ERR_GH_COMMAND_FAILED, err_desc, direct_merge_proc)

    auto_merge_proc = run_cmd(["gh", "pr", "merge", pr_url, "--auto", "--squash", "--delete-branch"], repo_path)
    if auto_merge_proc.returncode != 0:
        return command_err(ERR_GH_COMMAND_FAILED, err_desc, auto_merge_proc)

    wait_result = wait_for_pr_merged(pr_url, repo_path)
    if wait_result["err_code"] != 0:
        return wait_result
    wait_result["data"]["merge_mode"] = "auto"
    return wait_result


# gitclient 中文：检查当前 git/gh 基本运行前提是否满足。
def precheck_git() -> dict[str, Any]:
    ctx = load_git_context()
    repo_path = Path(ctx["repo_path"])
    if not str(ctx["project_id"]).strip():
        return err(ERR_INVALID_INPUT, "缺少项目ID-required.project_id")
    if not repo_path.exists():
        return err(ERR_INVALID_INPUT, f"git仓库路径不存在-git.repo_path: {repo_path}")

    git_probe = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], repo_path)
    if git_probe.returncode != 0:
        return command_err(ERR_GIT_NOT_READY, "当前目录不是git仓库", git_probe)

    if str(ctx["auth_check_command"]).strip():
        auth_probe = run_shell(str(ctx["auth_check_command"]), repo_path)
        if auth_probe.returncode != 0:
            return command_err(ERR_GIT_NOT_READY, "GitHub认证未就绪", auth_probe)

    remote_name = str(ctx["remote_name"])
    remote_probe = run_cmd(["git", "remote", "get-url", remote_name], repo_path)
    if remote_probe.returncode != 0:
        return command_err(ERR_GIT_NOT_READY, f"git远端不存在-{remote_name}", remote_probe)

    return ok(
        {
            "project_id": ctx["project_id"],
            "repo_path": str(repo_path),
            "remote_name": remote_name,
            "remote_url": remote_probe.stdout.strip(),
        }
    )


# gitclient 中文：检查工作区是否有未提交改动。
def get_worktree_status(repo_path: Path) -> dict[str, Any]:
    status_proc = run_cmd(["git", "status", "--short"], repo_path)
    if status_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "读取git工作区状态失败", status_proc)
    lines = [line for line in status_proc.stdout.splitlines() if line.strip()]
    return ok({"dirty": bool(lines), "lines": lines})


# gitclient 中文：生成新的工作分支名，避免直接在 main 上提交。
def build_branch_name(prefix: str = "auto") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}/{ts}"


# gitclient 中文：在工作区提交当前改动，推送分支，创建并合并 PR，最后同步 main。
def run_commit_and_merge(message: str, base_branch: str = "main") -> dict[str, Any]:
    message = resolve_commit_message(message)

    precheck = precheck_git()
    if precheck["err_code"] != 0:
        return precheck
    ctx = load_git_context()
    repo_path = Path(ctx["repo_path"])
    remote_name = str(ctx["remote_name"])

    worktree = get_worktree_status(repo_path)
    if worktree["err_code"] != 0:
        return worktree
    if not worktree["data"]["dirty"]:
        return err(ERR_GIT_NO_CHANGES, "当前工作区没有可提交改动")

    orig_branch_proc = run_cmd(["git", "branch", "--show-current"], repo_path)
    if orig_branch_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "读取当前分支失败", orig_branch_proc)
    orig_branch = orig_branch_proc.stdout.strip() or base_branch

    branch_name = build_branch_name()
    create_branch_proc = run_cmd(["git", "checkout", "-b", branch_name], repo_path)
    if create_branch_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"创建工作分支失败-{branch_name}", create_branch_proc)

    add_proc = run_cmd(["git", "add", "-A"], repo_path)
    if add_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "暂存改动失败", add_proc)

    staged_proc = run_cmd(["git", "diff", "--cached", "--name-only"], repo_path)
    if staged_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "检查暂存文件失败", staged_proc)
    staged_files = [line for line in staged_proc.stdout.splitlines() if line.strip()]
    if not staged_files:
        return err(ERR_GIT_NO_CHANGES, "git add 后没有可提交文件")

    commit_proc = run_cmd(["git", "commit", "-m", message], repo_path)
    if commit_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "git commit 失败", commit_proc)

    push_proc = run_cmd(["git", "push", "-u", remote_name, branch_name], repo_path)
    if push_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "git push 失败", push_proc)

    pr_title = message
    pr_body = f"RUN from {ctx['project_id']}\n\nAuto-created by tools/gitclient.py"
    pr_create_proc = run_cmd(
        ["gh", "pr", "create", "--base", base_branch, "--head", branch_name, "--title", pr_title, "--body", pr_body],
        repo_path,
    )
    if pr_create_proc.returncode != 0:
        return command_err(ERR_GH_COMMAND_FAILED, "创建PR失败", pr_create_proc)
    pr_url = pr_create_proc.stdout.strip().splitlines()[-1].strip() if pr_create_proc.stdout.strip() else ""

    merge_result = merge_pr_and_wait(pr_url, repo_path, "合并PR失败")
    if merge_result["err_code"] != 0:
        return merge_result

    fetch_proc = run_cmd(["git", "fetch", remote_name], repo_path)
    if fetch_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "拉取远端信息失败", fetch_proc)

    sync_main_proc = run_cmd(["git", "checkout", base_branch], repo_path)
    if sync_main_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"切回{base_branch}失败", sync_main_proc)

    sync_pull_proc = run_cmd(["git", "pull", "--rebase", remote_name, base_branch], repo_path)
    if sync_pull_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"同步最新{base_branch}失败", sync_pull_proc)

    return ok(
        {
            "project_id": ctx["project_id"],
            "orig_branch": orig_branch,
            "work_branch": branch_name,
            "base_branch": base_branch,
            "staged_files": staged_files,
            "pr_url": pr_url,
            "merge_mode": merge_result["data"].get("merge_mode", ""),
            "merged_at": merge_result["data"].get("merged_at", ""),
        }
    )


# gitclient 中文：从最新 main 派生回滚分支，回滚最近一次提交，然后走标准 PR 合并。
def run_rollback_last(base_branch: str = "main") -> dict[str, Any]:
    target_proc = run_cmd(["git", "rev-parse", base_branch], Path(load_git_context()["repo_path"]))
    if target_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"读取{base_branch}最新提交失败", target_proc)
    target_commit = target_proc.stdout.strip()
    return run_rollback_commit(target_commit, base_branch=base_branch)


# gitclient 中文：从最新 main 派生回滚分支，回滚指定提交，然后走标准 PR 合并。
def run_rollback_commit(commit_sha: str, base_branch: str = "main") -> dict[str, Any]:
    commit_sha = commit_sha.strip()
    if not commit_sha:
        return err(ERR_INVALID_INPUT, "回滚commit不能为空")

    precheck = precheck_git()
    if precheck["err_code"] != 0:
        return precheck
    ctx = load_git_context()
    repo_path = Path(ctx["repo_path"])
    remote_name = str(ctx["remote_name"])

    worktree = get_worktree_status(repo_path)
    if worktree["err_code"] != 0:
        return worktree
    if worktree["data"]["dirty"]:
        return err(ERR_GIT_DIRTY, "回滚前工作区必须干净", {"dirty_files": worktree["data"]["lines"]})

    fetch_proc = run_cmd(["git", "fetch", remote_name], repo_path)
    if fetch_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "拉取远端信息失败", fetch_proc)

    checkout_base_proc = run_cmd(["git", "checkout", base_branch], repo_path)
    if checkout_base_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"切换基础分支失败-{base_branch}", checkout_base_proc)

    pull_proc = run_cmd(["git", "pull", "--rebase", remote_name, base_branch], repo_path)
    if pull_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"同步基础分支失败-{base_branch}", pull_proc)

    branch_name = build_branch_name(prefix="rollback")
    create_branch_proc = run_cmd(["git", "checkout", "-b", branch_name], repo_path)
    if create_branch_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"创建回滚分支失败-{branch_name}", create_branch_proc)

    revert_proc = run_cmd(["git", "revert", "--no-edit", commit_sha], repo_path)
    if revert_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"回滚提交失败-{commit_sha}", revert_proc)

    push_proc = run_cmd(["git", "push", "-u", remote_name, branch_name], repo_path)
    if push_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, "推送回滚分支失败", push_proc)

    pr_title = f"revert: {commit_sha}"
    pr_body = f"Rollback commit {commit_sha}"
    pr_create_proc = run_cmd(
        ["gh", "pr", "create", "--base", base_branch, "--head", branch_name, "--title", pr_title, "--body", pr_body],
        repo_path,
    )
    if pr_create_proc.returncode != 0:
        return command_err(ERR_GH_COMMAND_FAILED, "创建回滚PR失败", pr_create_proc)
    pr_url = pr_create_proc.stdout.strip().splitlines()[-1].strip() if pr_create_proc.stdout.strip() else ""

    merge_result = merge_pr_and_wait(pr_url, repo_path, "合并回滚PR失败")
    if merge_result["err_code"] != 0:
        return merge_result

    sync_main_proc = run_cmd(["git", "checkout", base_branch], repo_path)
    if sync_main_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"切回{base_branch}失败", sync_main_proc)

    sync_pull_proc = run_cmd(["git", "pull", "--rebase", remote_name, base_branch], repo_path)
    if sync_pull_proc.returncode != 0:
        return command_err(ERR_GIT_COMMAND_FAILED, f"同步最新{base_branch}失败", sync_pull_proc)

    return ok(
        {
            "project_id": ctx["project_id"],
            "rollback_commit": commit_sha,
            "work_branch": branch_name,
            "base_branch": base_branch,
            "pr_url": pr_url,
            "merge_mode": merge_result["data"].get("merge_mode", ""),
            "merged_at": merge_result["data"].get("merged_at", ""),
        }
    )


# gitclient 中文：解析命令行参数，提供提交和回滚两类最小入口。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="quant-factory-os git client")
    parser.add_argument("--commit", nargs="?", const="", help="提交并合并到主分支")
    parser.add_argument("--rollback-last", action="store_true", help="回滚 main 最近一次提交")
    parser.add_argument("--rollback-commit", help="回滚指定 commit")
    parser.add_argument("--base-branch", default="main", help="目标基础分支，默认 main")
    return parser.parse_args(argv)


# gitclient 中文：CLI 入口，按参数分发到提交或回滚流程，并打印统一结果 JSON。
def main(argv: list[str] | None = None) -> int:
    build_logger()
    args = parse_args(argv)
    if args.commit is not None:
        result = run_commit_and_merge(args.commit, base_branch=args.base_branch)
    elif args.rollback_last:
        result = run_rollback_last(base_branch=args.base_branch)
    elif args.rollback_commit:
        result = run_rollback_commit(args.rollback_commit, base_branch=args.base_branch)
    else:
        result = err(ERR_INVALID_INPUT, "缺少操作参数，请使用 --commit / --rollback-last / --rollback-commit")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if int(result.get("err_code", 1)) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
