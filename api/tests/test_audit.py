"""PostgreSQL 审计历史测试（fake 连接，不依赖真实 PG）。"""

import pytest

from app.repositories.audit_repository import AuditRepository


class FakeCursor:
    def __init__(self, results=None):
        self.executed = []
        self._results = results or []
        self.description = [("id",), ("node_id",), ("event_type",), ("old_status",), ("new_status",), ("detail",), ("created_at",)]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._results

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConnection:
    def __init__(self, results=None):
        self._cur = FakeCursor(results)
        self.committed = 0
        self.closed = False

    def cursor(self):
        return self._cur

    def commit(self):
        self.committed += 1

    def close(self):
        self.closed = True


def _repo(enabled=True, results=None):
    conn = FakeConnection(results)
    factory = lambda: conn
    repo = AuditRepository(conn_factory=factory)
    repo._enabled = enabled
    return repo, conn


# ---------- 写入 ----------

def test_write_disabled_does_nothing():
    repo, conn = _repo(enabled=False)
    repo.record_node_event("proxy-a", "registered")
    assert conn._cur.executed == []


def test_record_node_event():
    repo, conn = _repo()
    repo.record_node_event("proxy-a", "registered", new_status="healthy")
    assert conn.committed == 1
    sql, params = conn._cur.executed[0]
    assert "node_events" in sql
    assert params[0] == "proxy-a"
    assert params[1] == "registered"
    assert params[3] == "healthy"


def test_record_acquire():
    repo, conn = _repo()
    repo.record_acquire("proxy-a", region="US", pool="ads", isp="OCI", account_id="acct-1")
    sql, params = conn._cur.executed[0]
    assert "acquire_logs" in sql
    assert params == ("proxy-a", "US", "ads", "OCI", "acct-1")


def test_record_report():
    repo, conn = _repo()
    repo.record_report("proxy-a", success=True, latency_ms=82.5)
    sql, params = conn._cur.executed[0]
    assert "report_logs" in sql
    assert params == ("proxy-a", True, 82.5)


def test_write_error_swallowed(monkeypatch):
    repo, conn = _repo()
    monkeypatch.setattr(conn._cur, "execute", lambda sql, params=None: (_ for _ in ()).throw(RuntimeError("pg down")))
    # 不应抛异常
    repo.record_node_event("proxy-a", "registered")


# ---------- 查询 ----------

def test_query_returns_rows():
    fake_row = (1, "proxy-a", "registered", None, "healthy", None, "2026-08-13 00:00:00")
    repo, conn = _repo(results=[fake_row])
    rows = repo.query_node_events(node_id="proxy-a", limit=10)
    assert len(rows) == 1
    assert rows[0]["node_id"] == "proxy-a"
    assert rows[0]["event_type"] == "registered"


def test_query_disabled_returns_empty():
    repo, conn = _repo(enabled=False)
    assert repo.query_node_events() == []
    assert repo.query_acquires() == []
    assert repo.query_reports() == []


def test_query_limits():
    repo, conn = _repo(results=[])
    repo.query_acquires(node_id="proxy-a", limit=5)
    sql, params = conn._cur.executed[0]
    assert "LIMIT %s" in sql
    assert params[2] == 5


# ---------- schema 初始化 ----------

def test_init_schema():
    repo, conn = _repo()
    repo.init_schema()
    sql, _ = conn._cur.executed[0]
    assert "CREATE TABLE IF NOT EXISTS node_events" in sql
    assert "CREATE TABLE IF NOT EXISTS acquire_logs" in sql