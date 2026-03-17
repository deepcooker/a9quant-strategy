#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


# 0001 中文：读取 JSON 文件，缺失或解析失败时返回空字典。
def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# 0002 中文：读取文本文件，缺失时返回空字符串。
def read_text(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


# 0003 中文：把对象写入 JSON 文件。
def write_json(path: str | Path, obj: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# 0004 中文：计算文件 SHA256 摘要，缺失或出错时返回标记值。
def file_sha(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return "missing"
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return "error"


# 0005 中文：按原顺序去重并过滤空项。
def ordered_unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


# 0006 中文：标准化多行文本块内容。
def normalize_block(lines: list[str]) -> str:
    parts: list[str] = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("- "):
            s = s[2:].strip()
        parts.append(s)
    return " ".join(parts)


# 0007 中文：标准化多行列表条目。
def normalize_list(lines: list[str]) -> list[str]:
    items: list[str] = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("- "):
            s = s[2:].strip()
        items.append(s)
    return items


# 0008 中文：标准化 scope 路径列表。
def normalize_scope(raw_scope: Any) -> list[str]:
    if not isinstance(raw_scope, list):
        return []
    out: list[str] = []
    for item in raw_scope:
        s = str(item).strip()
        if s:
            out.append(s.replace("`", ""))
    return out


# 0009 中文：按大小写不敏感方式去重文本行。
def dedup_lines(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(str(item))
    return out


# 0010 中文：去重 acceptance 条目并压缩空白。
def dedup_acceptance(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        item = " ".join(str(raw).split()).strip()
        if not item:
            continue
        key = item.lower().replace("`", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# 0011 中文：把逗号分隔的 scope 文本拆成列表。
def split_scope(scope_text: str) -> list[str]:
    out: list[str] = []
    for raw in str(scope_text).split(","):
        item = raw.strip().replace("`", "")
        if item:
            out.append(item)
    return out


# 0012 中文：把长文本压缩成短句。
def short_text(text: str, limit: int = 140) -> str:
    s = " ".join(str(text).split())
    if len(s) <= limit:
        return s
    return s[: limit - 3].rstrip() + "..."


# 0013 中文：解析布尔型命令行标志。
def parse_bool_flag(raw: str, name: str, *, allow_auto: bool = False, auto_as: str = "1") -> str:
    v = raw.strip().lower()
    if allow_auto and v == "auto":
        return auto_as
    if v in {"1", "true", "yes", "y"}:
        return "1"
    if v in {"0", "false", "no", "n"}:
        return "0"
    raise SystemExit(f"ERROR: {name} expects one of 1/0/true/false/yes/no" + ("/auto" if allow_auto else ""))


# 0014 中文：提取文本中的第一条非空行。
def first_line(text: str, default: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return default
