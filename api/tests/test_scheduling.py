"""加权随机调度测试：成功率 / 延迟 / 负载 影响选择概率。"""

import random

import pytest

from app.repositories.node_repository import NoHealthyNodeError, NodeRepository


class FakeRedis:
    """最小内存 Redis：仅覆盖 NodeRepository 用到的命令。"""

    def __init__(self):
        self._hash = {}  # key -> {field: value}
        self._set = {}   # key -> set()

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

    def srem(self, key, member):
        s = self._set.get(key, set())
        if member in s:
            s.discard(member)
            return 1
        return 0

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
    repo = NodeRepository(r=r)
    return repo, r


def _register(repo, r, node_id, **overrides):
    data = {
        "node_id": node_id,
        "ip": node_id,
        "port": 3128,
        "region": "US",
        "protocol": "http",
        "username": "3proxy",
        "password": "pw",
        "latency": "50",
        "current_connections": "1",
    }
    # register() 会把 success_count/fail_count 重置为 0，
    # 统计字段需注册后写入（真实场景由 report() 累加产生）
    stats = {}
    for k in ("success_count", "fail_count"):
        if k in overrides:
            stats[k] = str(overrides.pop(k))
    data.update({k: str(v) for k, v in overrides.items()})
    node = repo.register(data)
    if stats:
        r.hset(f"pp:node:{node_id}", mapping=stats)
    return node


# ---------- 基础行为 ----------

def test_acquire_raises_when_no_healthy(repo):
    repo_inst, _ = repo
    with pytest.raises(NoHealthyNodeError):
        repo_inst.acquire()


def test_acquire_single_node(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    node = repo_inst.acquire()
    assert node["node_id"] == "proxy-a"


def test_acquire_region_filter(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-us", region="US")
    _register(repo_inst, r, "proxy-jp", region="JP")
    node = repo_inst.acquire(region="JP")
    assert node["node_id"] == "proxy-jp"


def test_acquire_skips_unhealthy(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good")
    _register(repo_inst, r, "proxy-bad")
    r.hset("pp:node:proxy-bad", mapping={"status": "dead"})
    for _ in range(50):
        assert repo_inst.acquire()["node_id"] == "proxy-good"


# ---------- 权重计算 ----------

def test_score_prefers_high_success_rate(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good", success_count="100", fail_count="0")
    _register(repo_inst, r, "proxy-bad", success_count="0", fail_count="100")
    assert repo_inst._score(repo_inst.get("proxy-good")) > repo_inst._score(repo_inst.get("proxy-bad"))


def test_score_prefers_low_latency(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-fast", latency="20")
    _register(repo_inst, r, "proxy-slow", latency="800")
    assert repo_inst._score(repo_inst.get("proxy-fast")) > repo_inst._score(repo_inst.get("proxy-slow"))


def test_score_prefers_low_load(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-idle", current_connections="0")
    _register(repo_inst, r, "proxy-busy", current_connections="8")
    assert repo_inst._score(repo_inst.get("proxy-idle")) > repo_inst._score(repo_inst.get("proxy-busy"))


def test_score_defaults_to_full_when_no_stats(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-fresh", success_count="0", fail_count="0", latency="0", current_connections="0")
    assert repo_inst._score(repo_inst.get("proxy-fresh")) == 1.0


# ---------- 加权随机统计验证 ----------

def test_weighted_acquire_prefers_better_node(repo):
    """成功率 100% vs 0%：好节点被选中的次数应显著更多。"""
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good", success_count="100", fail_count="0", latency="10", current_connections="0")
    _register(repo_inst, r, "proxy-bad", success_count="0", fail_count="100", latency="900", current_connections="9")

    random.seed(42)
    hits = {"proxy-good": 0, "proxy-bad": 0}
    for _ in range(2000):
        node = repo_inst.acquire()
        hits[node["node_id"]] += 1

    # 权重比约 1.0 : 0.0x，好节点应占绝大多数
    assert hits["proxy-good"] > hits["proxy-bad"] * 5, hits
    assert hits["proxy-good"] > 1500, hits


def test_uniform_when_equal_scores(repo):
    """分数一致时退化为均匀随机，两端不应偏差过大。"""
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a", success_count="10", fail_count="0", latency="50", current_connections="1")
    _register(repo_inst, r, "proxy-b", success_count="10", fail_count="0", latency="50", current_connections="1")

    random.seed(7)
    hits = {"proxy-a": 0, "proxy-b": 0}
    for _ in range(2000):
        node = repo_inst.acquire()
        hits[node["node_id"]] += 1

    assert 700 < hits["proxy-a"] < 1300, hits
    assert 700 < hits["proxy-b"] < 1300, hits


def test_report_updates_stats_and_affects_score(repo):
    """失败上报后节点得分应下降。"""
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-x", success_count="10", fail_count="0", latency="30", current_connections="1")
    before = repo_inst._score(repo_inst.get("proxy-x"))
    repo_inst.report("proxy-x", success=False, latency=900.0)
    after = repo_inst._score(repo_inst.get("proxy-x"))
    assert after < before
