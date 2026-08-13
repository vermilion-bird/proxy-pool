import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from .api import nodes
from .core import redis as redis_module

logger = logging.getLogger("proxy-pool")

# HTTP 请求指标（按 方法/路径 计数）
HTTP_REQUESTS = Counter(
    "proxy_pool_http_requests_total",
    "HTTP requests received by the proxy-pool API.",
    ["method", "path"],
)


def _scan_pool():
    """从 Redis 扫描节点池，刷新池规模 Gauge。"""
    from . import metrics
    from .repositories.node_repository import NodeRepository

    try:
        repo = NodeRepository()
        nodes_all = repo.all_nodes()
        healthy = [n for n in nodes_all if n.get("status") == "healthy"]
        by_region: dict = {}
        for n in healthy:
            r = n.get("region", "US")
            by_region[r] = by_region.get(r, 0) + 1
        metrics.observe_pool(len(nodes_all), len(healthy), by_region)
    except Exception as exc:  # 采集失败不影响 API
        logger.warning("pool scan failed: %s", exc)


async def _pool_observer(interval: float = 15.0):
    while True:
        await asyncio.sleep(interval)
        _scan_pool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scan_pool()
    task = asyncio.create_task(_pool_observer())
    yield
    task.cancel()


app = FastAPI(title="Proxy Pool Manager", version="0.1.0", lifespan=lifespan)
app.include_router(nodes.router)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    response = await call_next(request)
    HTTP_REQUESTS.labels(method=request.method, path=request.url.path).inc()
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)