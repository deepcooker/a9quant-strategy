#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


# result_schema 中文：成功返回码。
ERR_SUCCESS = 0

# result_schema 中文：配置/初始化类错误码段。
ERR_CONFIG_BASE = 1000

# result_schema 中文：学习/会话类错误码段。
ERR_SESSION_BASE = 2000

# result_schema 中文：Git/运行时类错误码段。
ERR_RUNTIME_BASE = 3000

# result_schema 中文：未知内部错误码段。
ERR_INTERNAL_BASE = 9000


# result_schema 中文：生成统一成功返回结构。
def ok(data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "err_code": ERR_SUCCESS,
        "err_desc": "success",
        "data": data or {},
    }


# result_schema 中文：生成统一失败返回结构。
def err(err_code: int, err_desc: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "err_code": int(err_code),
        "err_desc": str(err_desc),
        "data": data or {},
    }


# result_schema 中文：判断返回结构是否为失败。
def is_err(result: dict[str, Any]) -> bool:
    return int(result.get("err_code", ERR_INTERNAL_BASE)) != ERR_SUCCESS


# result_schema 中文：要求返回结构必须成功，否则直接透传原错误。
def passthrough_if_err(result: dict[str, Any]) -> dict[str, Any] | None:
    if is_err(result):
        return result
    return None


if __name__ == "__main__":
    print(ok({"message": "统一返回协议可用"}))
