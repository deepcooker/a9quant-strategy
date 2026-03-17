#!/usr/bin/env python3
import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path


def usage() -> int:
    print(
        "Usage: tools/view.sh <path> [--from N] [--to M] [--max-lines K] "
        "[--find PATTERN] [--context N] [--lines START:END]"
    )
    return 2


def is_positive_int(value: str) -> bool:
    return value.isdigit() and int(value) >= 1


def is_non_negative_int(value: str) -> bool:
    return value.isdigit() and int(value) >= 0


def git_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: not inside a git repository.")
        raise SystemExit(1)
    return Path(result.stdout.strip()).resolve()


def parse_args(argv: list[str]) -> argparse.Namespace:
    if not argv or argv[0] in {"-h", "--help"}:
        raise SystemExit(usage())

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("path")
    parser.add_argument("positional_to", nargs="?")
    parser.add_argument("--from", dest="from_line", default="1")
    parser.add_argument("--to", dest="to_line", default="200")
    parser.add_argument("--max-lines", default="260")
    parser.add_argument("--find", dest="find_pattern", default="")
    parser.add_argument("--context", default="0")
    parser.add_argument("--lines", default="")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args(argv)
    if args.help:
        raise SystemExit(usage())
    return args


def normalize_range(args: argparse.Namespace) -> tuple[int, int, int, str, int]:
    from_line = args.from_line
    to_line = args.to_line
    max_lines = args.max_lines
    find_pattern = args.find_pattern
    context = args.context

    if args.lines:
        try:
            start_raw, end_raw = args.lines.split(":", 1)
        except ValueError:
            print("ERROR: --lines must be START:END.")
            raise SystemExit(2)
        from_line = start_raw
        to_line = end_raw

    if args.positional_to is not None:
        if args.find_pattern:
            print("ERROR: unexpected positional argument when using --find.")
            raise SystemExit(2)
        if not is_positive_int(args.positional_to):
            print(f"ERROR: unexpected positional argument: {args.positional_to}")
            raise SystemExit(2)
        to_line = args.positional_to

    if find_pattern:
        if not is_non_negative_int(context):
            print("ERROR: --context must be a non-negative integer.")
            raise SystemExit(2)
        return 0, 0, 0, find_pattern, int(context)

    if not (
        is_positive_int(from_line)
        and is_positive_int(to_line)
        and is_positive_int(max_lines)
    ):
        print("ERROR: --from/--to/--max-lines must be positive integers.")
        raise SystemExit(2)

    from_int = int(from_line)
    to_int = int(to_line)
    max_int = int(max_lines)

    if max_int > 260:
        print("ERROR: --max-lines exceeds 260. 请分段查看")
        raise SystemExit(1)
    if to_int < from_int:
        print("ERROR: --to must be >= --from.")
        raise SystemExit(2)

    range_count = to_int - from_int + 1
    if range_count > max_int:
        print(
            f"ERROR: requested range exceeds limit ({range_count} > {max_int}). 请分段查看"
        )
        raise SystemExit(1)

    return from_int, to_int, max_int, "", int(context)


def resolve_repo_file(repo_root: Path, raw_path: str) -> Path:
    resolved = Path(raw_path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        print("ERROR: path must be inside repo root.")
        raise SystemExit(1)

    if not resolved.is_file():
        print("ERROR: path is not a regular file.")
        raise SystemExit(1)
    return resolved


def check_denylist(repo_root: Path, resolved: Path, raw_path: str) -> None:
    denylist_file = repo_root / ".codex_read_denylist"
    if not denylist_file.is_file():
        return

    relative_path = "." if resolved == repo_root else str(resolved.relative_to(repo_root))
    matched_pattern = ""

    for raw_line in denylist_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if (
            fnmatch.fnmatch(relative_path, line)
            or fnmatch.fnmatch(str(resolved), line)
            or fnmatch.fnmatch(raw_path, line)
        ):
            matched_pattern = line
            break

    if not matched_pattern:
        return

    if os.environ.get("CODEX_READ_DENYLIST_ALLOW") == "1":
        print(
            "NOTICE: .codex_read_denylist override enabled "
            f"(CODEX_READ_DENYLIST_ALLOW=1), matched pattern: {matched_pattern}",
            file=sys.stderr,
        )
        return

    print(
        f"ERROR: blocked by .codex_read_denylist (matched pattern: {matched_pattern}).",
        file=sys.stderr,
    )
    print("Set CODEX_READ_DENYLIST_ALLOW=1 to override with audit trail.", file=sys.stderr)
    raise SystemExit(1)


def read_lines(resolved: Path) -> list[str]:
    return resolved.read_text(encoding="utf-8").splitlines()


def print_find_matches(lines: list[str], pattern: str, context: int) -> None:
    regex = re.compile(pattern)
    if context > 0:
        indexes: set[int] = set()
        for idx, line in enumerate(lines, start=1):
            if regex.search(line):
                start = max(1, idx - context)
                end = min(len(lines), idx + context)
                indexes.update(range(start, end + 1))
        if not indexes:
            print(f"No matches for pattern: {pattern}")
            raise SystemExit(1)
        for idx in sorted(indexes):
            print(idx)
        return

    matches = [str(idx) for idx, line in enumerate(lines, start=1) if regex.search(line)]
    if not matches:
        print(f"No matches for pattern: {pattern}")
        raise SystemExit(1)
    print("\n".join(matches))


def print_range(lines: list[str], start: int, end: int) -> None:
    for line in lines[start - 1 : end]:
        print(line)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    from_line, to_line, _max_lines, find_pattern, context = normalize_range(args)
    repo_root = git_repo_root()
    resolved = resolve_repo_file(repo_root, args.path)
    check_denylist(repo_root, resolved, args.path)
    lines = read_lines(resolved)

    if find_pattern:
        print_find_matches(lines, find_pattern, context)
    else:
        print_range(lines, from_line, to_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
