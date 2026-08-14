"""管理 API 认证：API Key + IP 白名单。

配置（环境变量）：
  PP_API_KEYS       逗号分隔的 API Key 列表；配置后所有 /api/v1/* 请求必须携带有效 Key
  PP_IP_WHITELIST   逗号分隔的 IP / CIDR 白名单；配置后仅白名单内来源可访问管理 API

认证方式（任选其一）：
  - 请求头 X-API-Key: <key>
  - 请求头 Authorization: Bearer <key>

未配置 PP_API_KEYS 时认证关闭（向后兼容）；生产环境必须配置。
"""

import ipaddress
import logging
import os
import secrets

from fastapi import HTTPException, Request, status

logger = logging.getLogger("proxy-pool")


def _split_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _configured_keys() -> list[str]:
    return _split_list(os.getenv("PP_API_KEYS", ""))


def _parse_whitelist(raw: str) -> list:
    """解析 IP 白名单：支持单个 IP（10.0.0.1）与 CIDR（10.0.0.0/8）。"""
    out = []
    for item in _split_list(raw):
        try:
            if "/" in item:
                out.append(ipaddress.ip_network(item, strict=False))
            else:
                out.append(ipaddress.ip_address(item))
        except ValueError:
            logger.warning("ignoring invalid IP whitelist entry: %s", item)
    return out


def _ip_allowed(client_ip: str, whitelist: list) -> bool:
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for rule in whitelist:
        if isinstance(rule, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if addr in rule:
                return True
        elif addr == rule:
            return True
    return False


def _extract_key(request: Request) -> str | None:
    """从 X-API-Key 或 Authorization: Bearer 头中提取 API Key。"""
    key = request.headers.get("X-API-Key")
    if key:
        return key.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _client_ip(request: Request) -> str:
    """获取客户端 IP。部署于反向代理后时可用 PP_TRUST_PROXY=1 信任 X-Forwarded-For。"""
    if os.getenv("PP_TRUST_PROXY", "0") == "1":
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


async def require_api_key(request: Request) -> None:
    """FastAPI 依赖：校验来源 IP（可选）与 API Key。

    挂在 /api/v1/* 路由上。无有效 Key 或来源不在白名单时抛 401/403。
    """
    # 1) IP 白名单（配置后启用）
    whitelist = _parse_whitelist(os.getenv("PP_IP_WHITELIST", ""))
    if whitelist and not _ip_allowed(_client_ip(request), whitelist):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="source IP not allowed",
        )

    # 2) API Key（配置后启用；未配置则放行，兼容现有部署）
    keys = _configured_keys()
    if not keys:
        logger.warning("PP_API_KEYS not set: management API auth is DISABLED")
        return

    provided = _extract_key(request)
    if not provided or not any(secrets.compare_digest(provided, k) for k in keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
