"""代理池 Python 客户端 (可复用)。

快速开始::

    from proxypool_client import ProxyPool

    pool = ProxyPool(region="US")
    proxy = pool.acquire()
    print(proxy["host"], proxy["port"])

    resp = pool.request_via_proxy("https://httpbin.org/ip", region="US")
    print("出口 IP:", resp.json()["origin"])
"""
from .proxypool_client import (
    ProxyPool,
    ProxyPoolError,
    ProxySession,
    NoProxyAvailable,
)

__all__ = ["ProxyPool", "ProxySession", "ProxyPoolError", "NoProxyAvailable"]
__version__ = "0.1.0"