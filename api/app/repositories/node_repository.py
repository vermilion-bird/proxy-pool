import os
import random

from ..core import redis as redis_module


class NodeNotFoundError(Exception):
    pass


class NoHealthyNodeError(Exception):
    pass


class NodeRepository:
    """节点仓库：注册/心跳/加权随机调度/上报。

    调度权重（可经环境变量覆盖）：
      PP_SCHED_W_SUCCESS   成功率权重（默认 0.5）
      PP_SCHED_W_LATENCY   延迟权重（默认 0.3）
      PP_SCHED_W_LOAD      负载权重（默认 0.2）
    """

    def __init__(
        self,
        r=None,
        node_key_prefix="pp:node",
        pool_key="pp:pool",
        w_success=None,
        w_latency=None,
        w_load=None,
        latency_threshold_ms=1000.0,
        load_threshold=10.0,
    ):
        self.r = r or redis_module.get_client()
        self.nkp = node_key_prefix
        self.pk = pool_key
        self.w_success = (
            float(os.getenv("PP_SCHED_W_SUCCESS", "0.5"))
            if w_success is None else float(w_success)
        )
        self.w_latency = (
            float(os.getenv("PP_SCHED_W_LATENCY", "0.3"))
            if w_latency is None else float(w_latency)
        )
        self.w_load = (
            float(os.getenv("PP_SCHED_W_LOAD", "0.2"))
            if w_load is None else float(w_load)
        )
        self.latency_threshold_ms = latency_threshold_ms
        self.load_threshold = load_threshold

    def _key(self, node_id):
        return f"{self.nkp}:{node_id}"

    def _is_healthy(self, node_id):
        return self.r.hget(self._key(node_id), "status") == "healthy"

    def register(self, node_data: dict) -> dict:
        nid = node_data.get("node_id") or node_data.get("id")
        if not nid:
            raise ValueError("node_id required")
        k = self._key(nid)
        self.r.hset(k, mapping={
            "node_id": nid,
            "ip": str(node_data.get("ip", "")),
            "port": str(node_data.get("port", 3128)),
            "region": str(node_data.get("region", "US")),
            "protocol": str(node_data.get("protocol", "http")),
            "username": str(node_data.get("username", "")),
            "password": str(node_data.get("password", "")),
            "status": "healthy",
            "success_count": "0",
            "fail_count": "0",
            "latency": str(node_data.get("latency", 0)),
            "current_connections": str(node_data.get("current_connections", 0)),
        })
        self.r.sadd(self.pk, nid)
        return self.get(nid)

    def heartbeat(self, node_id, status="healthy"):
        self.r.hset(self._key(node_id), mapping={
            "status": status,
        })

    def healthy_nodes(self, region=None):
        ids = self.r.smembers(self.pk)
        out = [nid for nid in ids if self._is_healthy(nid)]
        if region:
            out = [nid for nid in out if self.r.hget(self._key(nid), "region") == region]
        return out

    def _score(self, node: dict) -> float:
        """计算节点调度得分（0~1）：成功率 + 延迟 + 负载 加权。"""
        success = int(node.get("success_count") or 0)
        fail = int(node.get("fail_count") or 0)
        total = success + fail
        success_rate = (success / total) if total else 1.0  # 无统计数据视为满分

        latency = float(node.get("latency") or 0)
        latency_score = max(0.0, 1.0 - latency / self.latency_threshold_ms)

        connections = int(node.get("current_connections") or 0)
        load_score = max(0.0, 1.0 - connections / self.load_threshold)

        return (
            self.w_success * success_rate
            + self.w_latency * latency_score
            + self.w_load * load_score
        )

    def acquire(self, region=None):
        """加权随机选择一个健康节点（成功率/延迟/负载）。

        权重越高的节点被选中的概率越大；所有节点得分一致或全为 0 时
        退化为均匀随机（兼容无统计数据的新节点）。
        """
        candidates = self.healthy_nodes(region)
        if not candidates:
            raise NoHealthyNodeError("no healthy nodes")
        nodes = [self.get(nid) for nid in candidates]
        weights = [max(0.0, self._score(n)) for n in nodes]
        if sum(weights) <= 0:
            return random.choice(nodes)
        return random.choices(nodes, weights=weights, k=1)[0]

    def get(self, node_id):
        d = self.r.hgetall(self._key(node_id))
        if not d:
            raise NodeNotFoundError(f"node {node_id} not found")
        d["node_id"] = node_id
        return d

    def all_nodes(self):
        return [self.get(nid) for nid in self.r.smembers(self.pk)]

    def report(self, node_id, success=True, latency=0.0):
        k = self._key(node_id)
        p = self.r.pipeline()
        if success:
            p.hincrby(k, "success_count", 1)
        else:
            p.hincrby(k, "fail_count", 1)
        p.hset(k, "latency", latency)
        p.execute()