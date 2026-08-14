from prometheus_client import Counter, Gauge, Histogram

# ---- 业务指标 ----

# 节点池规模
NODES_TOTAL = Gauge(
    "proxy_pool_nodes_total",
    "Registered proxy nodes (healthy + unhealthy).",
)
NODES_HEALTHY = Gauge(
    "proxy_pool_nodes_healthy",
    "Healthy proxy nodes currently in the pool.",
)
NODES_BY_REGION = Gauge(
    "proxy_pool_nodes_healthy_by_region",
    "Healthy proxy nodes per region.",
    ["region"],
)

# acquire 分配
ACQUIRE_TOTAL = Counter(
    "proxy_pool_acquire_total",
    "Proxy acquire attempts.",
    ["region"],
)
ACQUIRE_ERRORS = Counter(
    "proxy_pool_acquire_errors_total",
    "Proxy acquire failures (no healthy node).",
)

# 使用上报
REPORT_TOTAL = Counter(
    "proxy_pool_report_total",
    "Proxy usage reports received.",
    ["result"],  # success | failure
)
REPORT_LATENCY = Histogram(
    "proxy_pool_report_latency_seconds",
    "Reported upstream latency (seconds).",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

# 注册 / 心跳
REGISTER_TOTAL = Counter(
    "proxy_pool_register_total",
    "Node registration attempts.",
)
HEARTBEAT_TOTAL = Counter(
    "proxy_pool_heartbeat_total",
    "Node heartbeats received.",
    ["status"],
)

# 节点状态变迁
NODE_STATE_CHANGES = Counter(
    "proxy_pool_node_state_changes_total",
    "Node state transitions (register / health lost).",
    ["transition"],
)
BANNED_TOTAL = Counter(
    "proxy_pool_node_banned_total",
    "Nodes auto-banned by quality evaluation.",
    ["reason"],
)


_seen_regions = set()


def observe_pool(nodes_total: int, healthy: int, healthy_by_region: dict):
    """Refresh pool-size gauges from a registry scan."""
    NODES_TOTAL.set(nodes_total)
    NODES_HEALTHY.set(healthy)
    # 清除已消失地区的旧标签
    for region in _seen_regions - set(healthy_by_region):
        NODES_BY_REGION.remove(region)
    _seen_regions.update(healthy_by_region)
    for region, count in healthy_by_region.items():
        NODES_BY_REGION.labels(region=region).set(count)