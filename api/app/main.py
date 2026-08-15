import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from . import __version__
from .api import nodes
from .core import redis as redis_module

logger = logging.getLogger("proxy-pool")

HTTP_REQUESTS = Counter(
    "proxy_pool_http_requests_total",
    "HTTP requests received by the proxy-pool API.",
    ["method", "path"],
)

# Web UI static directory: env var (Docker) or relative path (local dev)
_WEB_DIR = os.environ.get(
    "WEB_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist"),
)


def _scan_pool():
    from . import metrics
    from .repositories.node_repository import NodeRepository
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
    except Exception as exc:
        logger.warning("pool scan failed: %s", exc)


async def _pool_observer(interval: float = 15.0):
    while True:
        await asyncio.sleep(interval)
        _scan_pool()


async def _health_check_loop():
    from .services.health_checker import HealthChecker
    checker = HealthChecker()
    while True:
        try:
            checker.run_once()
        except Exception as exc:
            logger.warning("health check run failed: %s", exc)
        await asyncio.sleep(checker.interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from .repositories.audit_repository import AuditRepository
        AuditRepository().init_schema()
    except Exception as exc:
        logger.warning("audit schema init skipped: %s", exc)
    _scan_pool()
    tasks = [
        asyncio.create_task(_pool_observer()),
        asyncio.create_task(_health_check_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Proxy Pool Manager", version=__version__, lifespan=lifespan)
app.include_router(nodes.router)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    response = await call_next(request)
    HTTP_REQUESTS.labels(method=request.method, path=request.url.path).inc()
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/version")
def version():
    return {"name": "proxy-pool", "version": __version__}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Web UI SPA (catch-all, runs after API routes) ---

@app.get("/{full_path:path}")
async def serve_web(full_path: str):
    """Serve Web UI static files or index.html for SPA routing."""
    if full_path:
        target = os.path.join(_WEB_DIR, full_path)
        if os.path.isfile(target):
            return FileResponse(target)
    index = os.path.join(_WEB_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return Response("Web UI not built. Run: cd web && npm run build", status_code=404)
