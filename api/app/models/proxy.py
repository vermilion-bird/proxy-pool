from pydantic import BaseModel


class Node(BaseModel):
    node_id: str
    ip: str
    port: int = 3128
    region: str = "US"
    protocol: str = "http"
    username: str = ""
    password: str = ""
    status: str = "healthy"
    success_count: int = 0
    fail_count: int = 0
    latency_ms: float = 0.0
    current_connections: int = 0
    last_health_check: str = ""
    expire_at: int = 0
    created_at: str = ""