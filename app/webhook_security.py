from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse

DEFAULT_ALLOWED_WEBHOOK_HOSTS = frozenset({"open.feishu.cn", "open.larksuite.com"})


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def allowed_webhook_hosts() -> frozenset[str]:
    configured = {
        item.strip().lower().rstrip(".")
        for item in os.getenv("TODO_ALLOWED_WEBHOOK_HOSTS", "").split(",")
        if item.strip()
    }
    return frozenset(DEFAULT_ALLOWED_WEBHOOK_HOSTS | configured)


def _host_is_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    for allowed in allowed_webhook_hosts():
        if allowed.startswith("*."):
            suffix = allowed[1:]
            if host.endswith(suffix) and host != suffix[1:]:
                return True
        elif host == allowed:
            return True
    return False


def normalize_webhook_url(value: object, *, allow_blank: bool) -> str:
    if value is None:
        if allow_blank:
            return ""
        raise ValueError("Webhook 地址不能为空")

    url = str(value).strip()
    if not url:
        if allow_blank:
            return ""
        raise ValueError("Webhook 地址不能为空")

    try:
        parsed = urlparse(url)
        hostname: Optional[str] = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Webhook 地址格式不正确") from exc

    allowed_schemes = {"https"}
    if _env_flag("TODO_ALLOW_INSECURE_WEBHOOK_HTTP"):
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError("Webhook 地址必须使用 HTTPS")
    if not parsed.netloc or not hostname:
        raise ValueError("Webhook 地址格式不正确")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Webhook 地址不能包含用户名或密码")
    if parsed.fragment:
        raise ValueError("Webhook 地址不能包含 URL 片段")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Webhook 端口不合法")
    normalized_host = hostname.lower().rstrip(".")
    if not _host_is_allowed(normalized_host):
        raise ValueError(
            "Webhook 域名不在允许列表；默认仅允许飞书/Lark 官方域名，可通过 TODO_ALLOWED_WEBHOOK_HOSTS 扩展"
        )
    if normalized_host in DEFAULT_ALLOWED_WEBHOOK_HOSTS:
        prefix = "/open-apis/bot/v2/hook/"
        if not parsed.path.startswith(prefix) or not parsed.path[len(prefix):].strip("/"):
            raise ValueError("飞书/Lark Webhook 路径格式不正确")
    return url
