from fastapi import APIRouter, HTTPException

from ..repositories.node_repository import NodeRepository, NodeNotFoundError, NoHealthyNodeError

router = APIRouter(prefix="/api/v1", tags=["nodes"])


def _repo():
    return NodeRepository()


@router.get("/nodes")
def list_nodes(region: str | None = None):
    try:
        return {"nodes": _repo().healthy_nodes(region)}
    except NoHealthyNodeError:
        return {"nodes": []}


@router.post("/nodes/register")
def register_node(body: dict):
    node = _repo().register(body)
    return {"node_id": node["node_id"]}


@router.post("/nodes/{node_id}/heartbeat")
def heartbeat(node_id: str):
    _repo().heartbeat(node_id)
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
    return {"status": "deleted"}


@router.get("/proxies/acquire")
def acquire(region: str | None = None):
    try:
        node = _repo().acquire(region)
    except NoHealthyNodeError:
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
    _repo().report(body["node_id"], body.get("success", True), body.get("latency", 0.0))
    return {"status": "ok"}