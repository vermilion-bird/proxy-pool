from fastapi import FastAPI

from .api import nodes

app = FastAPI(title="Proxy Pool Manager", version="0.1.0")
app.include_router(nodes.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    from fastapi import Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)