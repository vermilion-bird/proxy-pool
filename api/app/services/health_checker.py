"""健康检查服务：TCP/HTTP 探活 + 状态机防抖（连续失败摘除 / 连续成功恢复）。

配置（环境变量）：
  PP_HC_INTERVAL       检查间隔秒（默认 30）
  PP_HC_TIMEOUT        探测超时秒（默认 5）
  PP_HC_FAIL_DEGRADED  连续失败进入 degraded 阈值（默认 3）
  PP_HC_FAIL_DEAD      连续失败进入 dead 阈值（默认 5）
  PP_HC_RECOVER        连续成功恢复 healthy 阈值（默认 3）
  PP_HC_HTTP_PROBE     是否启用 HTTP 深度探测（默认 1）
  PP_HC_PROBE_URL      HTTP 探测目标（默认 http://example.com）
"""

import logging
import os
import socket
import time
import urllib.request

logger = logging.getLogger("proxy-pool")

MANUAL_STATUSES = ("maintenance", "disabled")


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


class HealthChecker:
    """周期探测所有节点并应用状态机（防抖）。

    - 连续失败 >= fail_degraded -> degraded（摘除，不再参与分配）
    - 连续失败 >= fail_dead     -> dead
    - 连续成功 >= recover       -> healthy（重新入池）
    - maintenance / disabled 节点跳过检查
    """

    def __init__(self, repo=None):
        from ..repositories.node_repository import NodeRepository

        self.repo = repo or NodeRepository()
        self.interval = _env_float("PP_HC_INTERVAL", 30.0)
        self.timeout = _env_float("PP_HC_TIMEOUT", 5.0)
        self.fail_degraded = _env_int("PP_HC_FAIL_DEGRADED", 3)
        self.fail_dead = _env_int("PP_HC_FAIL_DEAD", 5)
        self.recover = _env_int("PP_HC_RECOVER", 3)
        self.http_probe = os.getenv("PP_HC_HTTP_PROBE", "1") == "1"
        self.probe_url = os.getenv("PP_HC_PROBE_URL", "http://example.com")

    def check_node(self, node: dict) -> tuple:
        """探测单个节点，返回 (ok: bool, latency_ms: float)。

        1. TCP 拨号 node:port（必做）
        2. HTTP 经代理访问 probe_url（PP_HC_HTTP_PROBE=1 时）
        """
        host = node.get("ip", "")
        port = int(node.get("port") or 3128)
        t0 = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=self.timeout):
                pass
        except OSError as exc:
            logger.debug("TCP probe failed %s:%s: %s", host, port, exc)
            return False, 0.0
        tcp_latency_ms = (time.monotonic() - t0) * 1000.0

        if not self.http_probe:
            return True, tcp_latency_ms

        try:
            proxy_url = (
                "http://"
                + node.get("username", "")
                + ":"
                + node.get("password", "")
                + "@"
                + host
                + ":"
                + str(port)
            )
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            )
            opener.open(self.probe_url, timeout=self.timeout)
        except Exception as exc:
            logger.debug("HTTP probe failed %s: %s", host, exc)
            return False, tcp_latency_ms
        return True, tcp_latency_ms

    def run_once(self):
        """扫描全部节点执行一次健康检查并更新状态。"""
        nodes = self.repo.all_nodes()
        for node in nodes:
            status = node.get("status", "healthy")
            if status in MANUAL_STATUSES:
                continue
            ok, latency_ms = self.check_node(node)
            self.repo.record_check(
                node["node_id"], ok, latency_ms,
                fail_degraded=self.fail_degraded,
                fail_dead=self.fail_dead,
                recover=self.recover,
            )
