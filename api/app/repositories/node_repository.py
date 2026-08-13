import random

from ..core import redis as redis_module


class NodeNotFoundError(Exception):
    pass


class NoHealthyNodeError(Exception):
    pass


class NodeRepository:
    def __init__(self, r=None, node_key_prefix="pp:node", pool_key="pp:pool"):
        self.r = r or redis_module.get_client()
        self.nkp = node_key_prefix
        self.pk = pool_key

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

    def acquire(self, region=None):
        candidates = self.healthy_nodes(region)
        if not candidates:
            raise NoHealthyNodeError("no healthy nodes")
        return self.get(random.choice(candidates))

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