"""审计历史存储：节点生命周期 / 分配记录 / 使用上报（PostgreSQL）。

设计原则：审计是"尽力而为"——PG 不可用时静默降级，
不影响代理池主业务流程（Redis 仍是实时状态的单一事实来源）。
"""

import logging

logger = logging.getLogger("proxy-pool")

SCHEMA = """
CREATE TABLE IF NOT EXISTS node_events (
    id          BIGSERIAL PRIMARY KEY,
    node_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,           -- registered | deleted | banned | unbanned | state_change
    old_status  TEXT,
    new_status  TEXT,
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_node_events_node ON node_events(node_id, created_at);

CREATE TABLE IF NOT EXISTS acquire_logs (
    id          BIGSERIAL PRIMARY KEY,
    node_id     TEXT NOT NULL,
    region      TEXT,
    pool        TEXT,
    isp         TEXT,
    account_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_acquire_logs_node ON acquire_logs(node_id, created_at);

CREATE TABLE IF NOT EXISTS report_logs (
    id          BIGSERIAL PRIMARY KEY,
    node_id     TEXT NOT NULL,
    success     BOOLEAN NOT NULL,
    latency_ms  DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_report_logs_node ON report_logs(node_id, created_at);
"""


class AuditRepository:
    """审计写入与查询。连接对象可注入以便测试。"""

    def __init__(self, conn_factory=None):
        self._conn_factory = conn_factory
        self._enabled = None  # 懒加载

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            from ..core import pg

            self._enabled = pg.pg_enabled()
        return self._enabled

    def _connect(self):
        if self._conn_factory:
            return self._conn_factory()
        from ..core import pg

        return pg.get_connection()

    def _execute(self, sql: str, params: tuple):
        """执行写入；失败仅记日志，不影响业务。"""
        if not self.enabled:
            return
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("audit write skipped (%s): %s", sql.split()[0], exc)

    def init_schema(self):
        if not self.enabled:
            return
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("audit schema init failed: %s", exc)

    # ---- 写入 ----

    def record_node_event(self, node_id, event_type, old_status=None, new_status=None, detail=None):
        self._execute(
            "INSERT INTO node_events (node_id, event_type, old_status, new_status, detail) "
            "VALUES (%s, %s, %s, %s, %s)",
            (node_id, event_type, old_status, new_status, detail),
        )

    def record_acquire(self, node_id, region=None, pool=None, isp=None, account_id=None):
        self._execute(
            "INSERT INTO acquire_logs (node_id, region, pool, isp, account_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (node_id, region, pool, isp, account_id),
        )

    def record_report(self, node_id, success, latency_ms):
        self._execute(
            "INSERT INTO report_logs (node_id, success, latency_ms) VALUES (%s, %s, %s)",
            (node_id, bool(success), float(latency_ms)),
        )

    # ---- 查询 ----

    def query_node_events(self, node_id=None, limit=50):
        return self._query(
            "SELECT id, node_id, event_type, old_status, new_status, detail, created_at "
            "FROM node_events WHERE (%s IS NULL OR node_id = %s) "
            "ORDER BY id DESC LIMIT %s",
            (node_id, node_id, int(limit)),
        )

    def query_acquires(self, node_id=None, limit=50):
        return self._query(
            "SELECT id, node_id, region, pool, isp, account_id, created_at "
            "FROM acquire_logs WHERE (%s IS NULL OR node_id = %s) "
            "ORDER BY id DESC LIMIT %s",
            (node_id, node_id, int(limit)),
        )

    def query_reports(self, node_id=None, limit=50):
        return self._query(
            "SELECT id, node_id, success, latency_ms, created_at "
            "FROM report_logs WHERE (%s IS NULL OR node_id = %s) "
            "ORDER BY id DESC LIMIT %s",
            (node_id, node_id, int(limit)),
        )

    def _query(self, sql: str, params: tuple):
        """查询历史；PG 不可用或未启用时返回空列表。"""
        if not self.enabled:
            return []
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("audit query skipped: %s", exc)
            return []
