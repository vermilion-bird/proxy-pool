from fastapi import APIRouter, Depends, HTTPException

from .. import metrics
from ..core.security import require_api_key
from ..repositories.node_repository import NodeRepository, NodeNotFoundError, NoHealthyNodeError

router = APIRouter(prefix="/api/v1", tags=["nodes"], dependencies=[Depends(require_api_key)])


def _repo():
    return NodeRepository()


def _scan_and_refresh():
    """路由操作后刷新池规模 Gauge。"""
    try:
        repo = NodeRepository()
        nodes_all = repo.all_nodes()
        healthy = [n for n in nodes_all if n.get("status") == "healthy"]
        by_region: dict = {}
        for n in healthy:
            r = n.get("region", "US")
            by_region[r] = by_region.get(r, 0) + 1
        metrics.observe_pool(len(nodes_all), len(healthy), by_region)
    except Exception:
        # 采集失败不影响业务返回
        pass


@router.get("/nodes")
def list_nodes(region: str | None = None):
    try:
        return {"nodes": _repo().healthy_nodes(region)}
    except NoHealthyNodeError:
        return {"nodes": []}


@router.post("/nodes/register")
def register_node(body: dict):
    metrics.REGISTER_TOTAL.inc()
    node = _repo().register(body)
    metrics.NODE_STATE_CHANGES.labels(transition="registered").inc()
    _scan_and_refresh()
    return {"node_id": node["node_id"]}


@router.post("/nodes/{node_id}/heartbeat")
def heartbeat(node_id: str):
    _repo().heartbeat(node_id)
    metrics.HEARTBEAT_TOTAL.labels(status="healthy").inc()
    _scan_and_refresh()
    return {"status": "ok"}


@router.get("/nodes/{node_id}")
def get_node(node_id: str):
    try:
        return _repo().get(node_id)
    except NodeNotFoundError:
        raise HTTPException(404, f"node {node_id} not found")


@router.delete("/nodes/{node_id}")
def delete_node(node_id: str):
    r = _repo()
    r.r.delete(r._key(node_id))
    r.r.srem(r.pk, node_id)
    metrics.NODE_STATE_CHANGES.labels(transition="deleted").inc()
    _scan_and_refresh()
    return {"status": "deleted"}


@router.get("/proxies/acquire")
def acquire(region: str | None = None):
    metrics.ACQUIRE_TOTAL.labels(region=region or "any").inc()
    try:
        node = _repo().acquire(region)
    except NoHealthyNodeError:
        metrics.ACQUIRE_ERRORS.inc()
        raise HTTPException(503, "no healthy nodes available")
    return {
        "proxy_id": node["node_id"],
        "host": node["ip"],
        "port": node["port"],
        "username": node["username"],
        "password": node["password"],
        "protocol": node["protocol"],
        "region": node["region"],
    }


@router.post("/proxies/report")
def report(body: dict):
    node_id = body["node_id"]
    success = body.get("success", True)
    latency = float(body.get("latency", 0.0))
    _repo().report(node_id, success, latency)
    metrics.REPORT_TOTAL.labels(result="success" if success else "failure").inc()
    metrics.REPORT_LATENCY.observe(latency)
    if not success:
        metrics.NODE_STATE_CHANGES.labels(transition="failed").inc()
    return {"status": "ok"}