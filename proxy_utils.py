# /root/policy/busi/strategy/proxy_utils.py
import os
import logging

# 通用日志（避免和策略日志冲突）
logger = logging.getLogger("ProxyUtils")

def set_system_proxy(
    enable: bool = True,
    http_proxy: str = "http://127.0.0.1:7890",
    https_proxy: str = "http://127.0.0.1:7890"
):
    """
    通用系统代理配置工具（支持开关、自定义代理地址）
    :param enable: 是否启用代理（True=启用，False=禁用）
    :param http_proxy: HTTP代理地址（默认适配国内常用代理端口）
    :param https_proxy: HTTPS代理地址（默认和HTTP一致）
    """
    if enable:
        # 启用代理（复用原有生产环境配置）
        os.environ["http_proxy"] = http_proxy
        os.environ["https_proxy"] = https_proxy
        logger.info(f"✅ 系统代理已启用 | HTTP: {http_proxy} | HTTPS: {https_proxy}")
    else:
        # 禁用代理（清空环境变量）
        if "http_proxy" in os.environ:
            del os.environ["http_proxy"]
        if "https_proxy" in os.environ:
            del os.environ["https_proxy"]
        logger.info("❌ 系统代理已禁用")

def set_proxy_by_env(env: str = "prod"):
    """
    按环境快速配置代理（生产/测试/本地）
    :param env: 环境标识（prod=生产，test=测试，local=本地）
    """
    env_proxy_map = {
        "prod": ("http://127.0.0.1:7890", "http://127.0.0.1:7890"),  # 生产环境代理
        "test": ("http://10.0.0.1:7890", "http://10.0.0.1:7890"),    # 测试环境代理
        "local": ("", "")                                           # 本地环境禁用代理
    }
    http, https = env_proxy_map.get(env, ("", ""))
    set_system_proxy(enable=bool(http), http_proxy=http, https_proxy=https)