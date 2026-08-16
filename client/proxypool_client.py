"""代理池客户端 (可复用).

比文档里的示例更完整:
- 环境变量配置: ``PROXY_POOL_API_BASE`` (默认 http://158.180.87.150:8082)
- 自动重试 + 故障切换: 一次请求失败会自动上报并重新获取一个不同节点
- 同步 (requests) 与 httpx 两种请求方式
- 会话级代理 (context manager) 或单次请求两种用法
- 结构化日志

依赖:
- requests  (或 ``requests[socks]`` 用于 SOCKS5)
- httpx     (可选, 用于 ``request_via_httpx`` / ``session`` 用法)

环境变量:
- ``PROXY_POOL_API_BASE``  代理池 API 地址, 默认 http://158.180.87.150:8082
- ``PROXY_POOL_REGION``    默认区域 (US/EU/AP), 可省略
- ``PROXY_POOL_PROTOCOL``  默认协议 http/socks5, 可省略
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterator, Optional

import requests

log = logging.getLogger(__name__)

DEFAULT_API_BASE = os.environ.get("PROXY_POOL_API_BASE", "http://158.180.87.150:8082")


class ProxyPoolError(RuntimeError):
    """代理池 API 或节点不可用时抛出。"""


class NoProxyAvailable(ProxyPoolError):
    """池里没有可用节点。"""


class ProxyPool:
    """代理池客户端。

    用法::

        pool = ProxyPool(region="US")
        proxy = pool.acquire()          # 拿一个代理 (dict)
        resp = pool.request_via_proxy("https://httpbin.org/ip")
        resp = pool.request_via_httpx("https://httpbin.org/ip")

    - 单次请求用法: ``request_via_proxy`` / ``request_via_httpx`` 自动 acquire + report。
    - 批量/会话用法: ``session(region=...)`` 上下文管理器, 进处先 acquire,
      退出自动 report; 请求中途节点失败会重连。
    """

    def __init__(self, api_base: str | None = None,
                 region: str | None = None,
                 protocol: str | None = None,
                 timeout: float = 5.0,
                 max_failover: int = 3,
                 acquire_timeout: float = 5.0):
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.region = region or os.environ.get("PROXY_POOL_REGION")
        self.protocol = protocol or os.environ.get("PROXY_POOL_PROTOCOL")
        self.timeout = timeout
        self.max_failover = max_failover
        self.acquire_timeout = acquire_timeout

    # ------------------------------------------------------------------ #
    # 底层 API
    # ------------------------------------------------------------------ #
    def acquire(self, region: str | None = None,
                protocol: str | None = None) -> dict[str, str]:
        """获取一个可用代理。返回含 proxy_id/host/port/username/password/protocol/region。

        注意: acquire 是 GET 接口, 通过 query param 传 region (协议是节点固有属性,
        不做请求过滤)。
        """
        params: dict[str, str] = {}
        region = region or self.region
        protocol = protocol or self.protocol
        if region:
            params["region"] = region
        if protocol:
            params["protocol"] = protocol
        try:
            resp = requests.get(
                f"{self.api_base}/api/v1/proxies/acquire",
                params=params or None, timeout=self.acquire_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise ProxyPoolError(f"acquire failed: {e}") from e
        if not data or not data.get("proxy_id"):
            raise NoProxyAvailable(f"no proxy available (region={region})")
        return data

    def report(self, proxy_id: str, success: bool,
               latency_ms: int | None = None) -> None:
        """上报节点使用结果, 帮助调度优化。失败不抛出 (仅记日志)。"""
        body: dict[str, Any] = {"node_id": proxy_id, "success": bool(success)}
        if latency_ms is not None:
            # API 字段名是 ``latency`` (秒), 注意不是 latency_ms
            body["latency"] = float(latency_ms) / 1000.0
        try:
            resp = requests.post(
                f"{self.api_base}/api/v1/proxies/report",
                json=body, timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("report failed (proxy_id=%s): %s", proxy_id, e)

    def list_nodes(self, region: str | None = None) -> list[dict]:
        """列出所有节点 (可选按区域过滤)。"""
        params = {}
        if region or self.region:
            params["region"] = region or self.region
        resp = requests.get(f"{self.api_base}/api/v1/nodes",
                            params=params or None, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("nodes", resp.json() if isinstance(resp.json(), list) else [])

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def proxy_url(proxy: dict) -> str:
        """把 acquire 返回的 dict 拼成 ``protocol://user:pass@host:port``。"""
        return (f"{proxy['protocol']}://{proxy['username']}:{proxy['password']}"
                f"@{proxy['host']}:{proxy['port']}")

    # ------------------------------------------------------------------ #
    # 单次请求 (自动 acquire + report)
    # ------------------------------------------------------------------ #
    def request_via_proxy(self, url: str, *, method: str = "GET",
                          region: str | None = None,
                          timeout: float = 30.0,
                          **kwargs: Any) -> requests.Response:
        """通过代理池发起 requests 请求; 失败自动故障切换到新节点。"""
        last_err: Exception | None = None
        for _ in range(self.max_failover):
            proxy = self.acquire(region=region)
            p_url = self.proxy_url(proxy)
            proxies = {"http": p_url, "https": p_url}
            try:
                resp = requests.request(method, url, proxies=proxies,
                                        timeout=timeout, **kwargs)
                ms = int(resp.elapsed.total_seconds() * 1000)
                self.report(proxy["proxy_id"], True, ms)
                return resp
            except requests.RequestException as e:
                last_err = e
                self.report(proxy["proxy_id"], False)
                log.warning("request via %s failed (%s), failing over", proxy["host"], e)
        assert last_err is not None
        raise ProxyPoolError(f"all proxies failed: {last_err}") from last_err

    def request_via_httpx(self, url: str, *, method: str = "GET",
                          region: str | None = None,
                          timeout: float = 30.0,
                          **kwargs: Any):
        """通过代理池发起 httpx 请求 (需要 ``pip install httpx``)。"""
        import httpx
        last_err: Exception | None = None
        for _ in range(self.max_failover):
            proxy = self.acquire(region=region)
            p_url = self.proxy_url(proxy)
            try:
                with httpx.Client(proxy=p_url, timeout=timeout) as client:
                    start = time_monotonic()
                    resp = client.request(method, url, **kwargs)
                    ms = int((time_monotonic() - start) * 1000)
                self.report(proxy["proxy_id"], True, ms)
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_err = e
                self.report(proxy["proxy_id"], False)
                log.warning("httpx via %s failed (%s), failing over", proxy["host"], e)
        assert last_err is not None
        raise ProxyPoolError(f"all proxies failed: {last_err}") from last_err

    # ------------------------------------------------------------------ #
    # 会话级 (单节点复用, 退出自动上报)
    # ------------------------------------------------------------------ #
    def session(self, region: str | None = None,
                protocol: str | None = None) -> "ProxySession":
        """进入一个会话: 进处 acquire 一个节点并在整个 with 块复用。"""
        return ProxySession(self, region=region, protocol=protocol)


class ProxySession:
    """单个节点会话。退出时把最终状态上报回池。

    用法::

        with pool.session(region="US") as ps:
            ps.requests_get("https://httpbin.org/ip", timeout=10)
            ps.requests_get("https://httpbin.org/headers", timeout=10)
    """

    def __init__(self, pool: ProxyPool, region: str | None = None,
                 protocol: str | None = None):
        self._pool = pool
        self._region = region or pool.region
        self._protocol = protocol or pool.protocol
        self._proxy: dict | None = None
        self._succeeded = 0
        self._failed = 0
        self._total_ms = 0
        self._requests_session: Any | None = None
        self._httpx_client: Any | None = None

    # -- lifecycle ------------------------------------------------------ #
    def __enter__(self) -> "ProxySession":
        self._proxy = self._pool.acquire(region=self._region, protocol=self._protocol)
        log.debug("session acquired proxy %s", self._proxy["host"])
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._requests_session is not None:
            self._requests_session.close()
            self._requests_session = None
        if self._httpx_client is not None:
            self._httpx_client.close()
            self._httpx_client = None
        proxy = self._proxy
        if proxy is not None:
            ok = self._failed == 0
            avg_ms = int(self._total_ms / self._succeeded) if self._succeeded else 0
            self._pool.report(proxy["proxy_id"], ok, avg_ms)
            self._proxy = None

    @property
    def proxy(self) -> dict:
        if self._proxy is None:
            raise ProxyPoolError("session not entered (use `with pool.session(...)` or call __enter__)")
        return self._proxy

    @property
    def proxy_url(self) -> str:
        return self._pool.proxy_url(self.proxy)

    # -- requests ------------------------------------------------------- #
    @property
    def requests(self):
        """一个已挂代理的 requests.Session (惰性创建)。"""
        import requests as _requests
        if self._requests_session is None:
            s = _requests.Session()
            p_url = self.proxy_url
            s.proxies = {"http": p_url, "https": p_url}
            self._requests_session = s
        return self._requests_session

    def requests_get(self, url: str, *, timeout: float = 30.0, **kw) -> requests.Response:
        return self._track("requests", lambda: self.requests.get(url, timeout=timeout, **kw))

    def requests_post(self, url: str, *, timeout: float = 30.0, **kw) -> requests.Response:
        return self._track("requests", lambda: self.requests.post(url, timeout=timeout, **kw))

    # -- httpx ---------------------------------------------------------- #
    @property
    def httpx(self):
        """一个已挂代理的 httpx.Client (惰性创建)。"""
        import httpx
        if self._httpx_client is None:
            self._httpx_client = httpx.Client(proxy=self.proxy_url,
                                              headers={"User-Agent": "proxypool-client/1.0"})
        return self._httpx_client

    def httpx_get(self, url: str, *, params=None, timeout: float = 30.0, **kw):
        return self._track("httpx", lambda: self.httpx.get(url, params=params, timeout=timeout, **kw))

    # -- internals ------------------------------------------------------ #
    def _track(self, kind: str, fn):
        import time
        start = time.monotonic()
        try:
            result = fn()
        except Exception as e:
            self._failed += 1
            raise
        ms = int((time.monotonic() - start) * 1000)
        self._succeeded += 1
        self._total_ms += ms
        return result


def time_monotonic():
    import time
    return time.monotonic()


__all__ = ["ProxyPool", "ProxySession", "ProxyPoolError", "NoProxyAvailable"]