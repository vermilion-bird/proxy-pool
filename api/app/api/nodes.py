from fastapi import APIRouter, Depends, HTTPException, Query

from .. import metrics
from ..core.security import require_api_key
from ..repositories.audit_repository import AuditRepository
from ..repositories.node_repository import NodeRepository, NodeNotFoundError, NoHealthyNodeError
from ..services import geo_enricher

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
        by_pool: dict = {}
        for n in healthy:
            r = n.get("region", "US")
            by_region[r] = by_region.get(r, 0) + 1
            p = n.get("pool", "default")
            by_pool[p] = by_pool.get(p, 0) + 1
        metrics.observe_pool(len(nodes_all), len(healthy), by_region, by_pool)
    except Exception:
        pass


@router.get("/nodes")
def list_nodes(
    region: str | None = None,
    pool: str | None = None,
    isp: str | None = None,
    include_all: bool = Query(False, description="Include non-healthy nodes as well"),
):
    """List nodes with full details. Filters by region/pool/isp (AND logic)."""
    try:
        repo = _repo()
        if include_all:
            all_nodes = repo.all_nodes()
            result = []
            for n in all_nodes:
                if region and n.get("region") != region:
                    continue
                if pool and n.get("pool", "default") != pool:
                    continue
                if isp and n.get("isp", "") != isp:
                    continue
                result.append(n)
            return {"nodes": result}
        else:
            ids = repo.healthy_nodes(region, pool=pool, isp=isp)
            nodes = [repo.get(nid) for nid in ids]
            return {"nodes": nodes}
    except NoHealthyNodeError:
        return {"nodes": []}
    except NodeNotFoundError:
        return {"nodes": []}


@router.post("/nodes/register")
def register_node(body: dict):
    metrics.REGISTER_TOTAL.inc()
    node = _repo().register(body)
    AuditRepository().record_node_event(node["node_id"], "registered", new_status="healthy")
    metrics.NODE_STATE_CHANGES.labels(transition="registered").inc()
    _scan_and_refresh()
    # Auto-enrich geo data
    try:
        enriched = geo_enricher.enrich_node(node)
        _repo().update_meta(node["node_id"], enriched, overwrite_core=True)
    except Exception:
        pass
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
    AuditRepository().record_node_event(node_id, "deleted", old_status="removed")
    metrics.NODE_STATE_CHANGES.labels(transition="deleted").inc()
    _scan_and_refresh()
    return {"status": "deleted"}


@router.get("/proxies/acquire")
def acquire(region: str | None = None, pool: str | None = None, isp: str | None = None, account_id: str | None = None):
    metrics.ACQUIRE_TOTAL.labels(region=region or "any").inc()
    try:
        if account_id:
            node, sticky = _repo().acquire_sticky(account_id, region=region, pool=pool, isp=isp)
        else:
            node, sticky = _repo().acquire(region, pool=pool, isp=isp), False
        AuditRepository().record_acquire(node["node_id"], region=region, pool=node.get("pool"), isp=node.get("isp"), account_id=account_id)
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
        "pool": node.get("pool", "default"),
        "isp": node.get("isp", ""),
        "sticky": sticky,
    }


@router.post("/proxies/report")
def report(body: dict):
    node_id = body["node_id"]
    success = body.get("success", True)
    latency = float(body.get("latency", 0.0))
    _repo().report(node_id, success, latency)
    AuditRepository().record_report(node_id, success, latency)
    metrics.REPORT_TOTAL.labels(result="success" if success else "failure").inc()
    metrics.REPORT_LATENCY.observe(latency)
    if not success:
        metrics.NODE_STATE_CHANGES.labels(transition="failed").inc()
    return {"status": "ok"}


@router.post("/proxies/release")
def release_sticky(body: dict):
    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(422, "account_id required")
    _repo().release_sticky(account_id)
    return {"status": "released"}


@router.post("/nodes/{node_id}/unban")
def unban_node(node_id: str):
    try:
        node = _repo().unban(node_id)
    except NodeNotFoundError:
        raise HTTPException(404, f"node {node_id} not found")
    _scan_and_refresh()
    return {"node_id": node["node_id"], "status": node["status"]}


# ---------- 地理信息增强 ----------


@router.post("/nodes/{node_id}/enrich")
def enrich_single(node_id: str):
    """向 ipwho.is 查询节点的地理信息并存入 Redis。"""
    try:
        node = _repo().get(node_id)
    except NodeNotFoundError:
        raise HTTPException(404, f"node {node_id} not found")
    enriched = geo_enricher.enrich_node(dict(node))
    _repo().update_meta(node_id, enriched, overwrite_core=True)
    return {"node_id": node_id, "geo": {k: v for k, v in enriched.items() if k.startswith("geo_")}}


@router.post("/nodes/enrich-all")
def enrich_all():
    """批量刷新全部节点的地理信息。"""
    nodes = _repo().all_nodes()
    results = []
    for node in nodes:
        try:
            enriched = geo_enricher.enrich_node(dict(node))
            _repo().update_meta(node["node_id"], enriched, overwrite_core=True)
            results.append({"node_id": node["node_id"], "success": True})
        except Exception as exc:
            results.append({"node_id": node["node_id"], "success": False, "error": str(exc)})
    return {"total": len(nodes), "results": results}


# ---------- 审计历史查询（PostgreSQL） ----------


@router.get("/audit/events")
def audit_node_events(node_id: str | None = None, limit: int = 50):
    """节点生命周期事件（注册/删除/封禁/解封/状态变迁）。"""
    return {"events": AuditRepository().query_node_events(node_id=node_id, limit=min(limit, 500))}


@router.get("/audit/acquires")
def audit_acquires(node_id: str | None = None, limit: int = 50):
    """代理分配历史。"""
    return {"acquires": AuditRepository().query_acquires(node_id=node_id, limit=min(limit, 500))}


@router.get("/audit/reports")
def audit_reports(node_id: str | None = None, limit: int = 50):
    """使用上报历史。"""
    return {"reports": AuditRepository().query_reports(node_id=node_id, limit=min(limit, 500))}

