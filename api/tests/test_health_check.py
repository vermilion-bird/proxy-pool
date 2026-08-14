"""健康检查测试：状态机防抖 + TCP/HTTP 探活。"""

import pytest

from app.repositories.node_repository import NodeRepository
from app.services.health_checker import HealthChecker


class FakeRedis:
    """最小内存 Redis：仅覆盖用到的命令。"""

    def __init__(self):
        self._hash = {}
        self._set = {}

    def hset(self, key, mapping=None, **kwargs):
        d = self._hash.setdefault(key, {})
        if mapping:
            d.update(mapping)
        d.update(kwargs)
        return len(d)

    def hgetall(self, key):
        return dict(self._hash.get(key, {}))

    def hget(self, key, field):
        return self._hash.get(key, {}).get(field)

    def hincrby(self, key, field, amount):
        d = self._hash.setdefault(key, {})
        d[field] = int(d.get(field, 0)) + amount
        return d[field]

    def sadd(self, key, *members):
        s = self._set.setdefault(key, set())
        s.update(members)
        return len(s)

    def smembers(self, key):
        return set(self._set.get(key, set()))

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, r):
        self._r = r
        self._ops = []

    def hincrby(self, key, field, amount):
        self._ops.append(("incr", key, field, amount))
        return self

    def hset(self, key, field, value):
        self._ops.append(("set", key, field, value))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == "incr":
                self._r.hincrby(op[1], op[2], op[3])
            else:
                self._r.hset(op[1], {op[2]: op[3]})


@pytest.fixture
def repo():
    r = FakeRedis()
    return NodeRepository(r=r), r


def _register(repo, r, node_id, **overrides):
    data = {
        "node_id": node_id,
        "ip": "10.0.0.1",
        "port": 3128,
        "region": "US",
        "username": "3proxy",
        "password": "pw",
    }
    data.update({k: str(v) for k, v in overrides.items()})
    return repo.register(data)


# ---------- 状态机防抖 ----------

def test_failure_accumulates_and_degrades(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    # 1、2 次失败：仍 healthy；第 3 次 -> degraded
    for i in range(2):
        repo_inst.record_check("proxy-a", ok=False)
        assert repo_inst.get("proxy-a")["status"] == "healthy"
    repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "degraded"
    assert repo_inst.get("proxy-a")["consecutive_failures"] == "3"


def test_failure_reaches_dead(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    for _ in range(4):
        repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "degraded"
    repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "dead"


def test_success_resets_failure_counter(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    for _ in range(2):
        repo_inst.record_check("proxy-a", ok=False)
    # 中间成功一次 -> 失败计数清零
    repo_inst.record_check("proxy-a", ok=True)
    assert repo_inst.get("proxy-a")["consecutive_failures"] == "0"
    assert repo_inst.get("proxy-a")["status"] == "healthy"


def test_recovery_from_dead(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    for _ in range(5):
        repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "dead"
    # 连续 3 次成功 -> healthy
    for _ in range(2):
        repo_inst.record_check("proxy-a", ok=True)
        assert repo_inst.get("proxy-a")["status"] == "dead"
    repo_inst.record_check("proxy-a", ok=True)
    assert repo_inst.get("proxy-a")["status"] == "healthy"


def test_manual_status_not_auto_migrated(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    repo_inst.heartbeat("proxy-a", status="maintenance")
    for _ in range(6):
        repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "maintenance"


def test_degraded_node_excluded_from_acquire(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good")
    _register(repo_inst, r, "proxy-bad")
    for _ in range(3):
        repo_inst.record_check("proxy-bad", ok=False)
    assert repo_inst.get("proxy-bad")["status"] == "degraded"
    # 加权调度只会选 healthy
    for _ in range(100):
        assert repo_inst.acquire()["node_id"] == "proxy-good"


def test_record_check_updates_latency(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    repo_inst.record_check("proxy-a", ok=True, latency_ms=123.4)
    assert repo_inst.get("proxy-a")["latency"] == "123.4"


# ---------- HealthChecker 探活 ----------

def test_check_node_tcp_failure(monkeypatch, repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")

    def fake_conn(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr("app.services.health_checker.socket.create_connection", fake_conn)
    checker = HealthChecker(repo=repo_inst)
    ok, latency = checker.check_node(repo_inst.get("proxy-a"))
    assert ok is False
    assert latency == 0.0


def test_check_node_tcp_ok_no_http_probe(monkeypatch, repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("app.services.health_checker.socket.create_connection", lambda *a, **kw: FakeConn())
    checker = HealthChecker(repo=repo_inst)
    checker.http_probe = False
    ok, latency = checker.check_node(repo_inst.get("proxy-a"))
    assert ok is True
    assert latency >= 0.0


def test_run_once_dead_after_repeated_failures(monkeypatch, repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    checker = HealthChecker(repo=repo_inst)
    checker.fail_degraded = 3
    checker.fail_dead = 5
    checker.check_node = lambda node: (False, 0.0)
    for _ in range(5):
        checker.run_once()
    assert repo_inst.get("proxy-a")["status"] == "dead"


def test_run_once_skips_manual_nodes(monkeypatch, repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    repo_inst.heartbeat("proxy-a", status="disabled")
    calls = []

    checker = HealthChecker(repo=repo_inst)

    def spy(node):
        calls.append(node["node_id"])
        return (False, 0.0)

    checker.check_node = spy
    checker.run_once()
    assert calls == []
    assert repo_inst.get("proxy-a")["status"] == "disabled"
