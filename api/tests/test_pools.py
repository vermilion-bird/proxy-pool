"""区域池 / ISP 池 / 业务专属池测试。"""

import pytest

from app.repositories.node_repository import NoHealthyNodeError, NodeRepository


class FakeRedis:
    """最小内存 Redis。"""

    def __init__(self):
        self._hash = {}
        self._set = {}
        self._str = {}
        self._ttl = {}

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

    def get(self, key):
        return self._str.get(key)

    def set(self, key, value, ex=None):
        self._str[key] = value
        if ex is not None:
            self._ttl[key] = ex
        return True

    def expire(self, key, seconds):
        if key in self._str:
            self._ttl[key] = seconds
            return 1
        return 0

    def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self._str:
                del self._str[k]
                self._ttl.pop(k, None)
                n += 1
            if k in self._hash:
                del self._hash[k]
                n += 1
        return n

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
        "pool": "default",
        "isp": "",
        "username": "3proxy",
        "password": "pw",
    }
    data.update({k: str(v) for k, v in overrides.items()})
    return repo.register(data)


# ---------- 注册带 pool/isp ----------

def test_register_defaults_pool(repo):
    repo_inst, r = repo
    node = _register(repo_inst, r, "proxy-a")
    assert node["pool"] == "default"
    assert node["isp"] == ""


def test_register_pool_isp(repo):
    repo_inst, r = repo
    node = _register(repo_inst, r, "proxy-a", pool="ads", isp="OCI")
    assert node["pool"] == "ads"
    assert node["isp"] == "OCI"


# ---------- 多维过滤 ----------

def test_healthy_nodes_filter_by_pool(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-default", pool="default")
    _register(repo_inst, r, "proxy-ads", pool="ads")
    _register(repo_inst, r, "proxy-data", pool="data-pipeline")
    got = sorted(repo_inst.healthy_nodes(pool="ads"))
    assert got == ["proxy-ads"]


def test_healthy_nodes_filter_by_isp(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-oci", isp="OCI")
    _register(repo_inst, r, "proxy-aws", isp="AWS")
    got = sorted(repo_inst.healthy_nodes(isp="AWS"))
    assert got == ["proxy-aws"]


def test_healthy_nodes_multi_dimension(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a", region="US", pool="ads", isp="OCI")
    _register(repo_inst, r, "proxy-b", region="JP", pool="ads", isp="OCI")
    _register(repo_inst, r, "proxy-c", region="US", pool="data", isp="OCI")
    got = sorted(repo_inst.healthy_nodes(region="US", pool="ads", isp="OCI"))
    assert got == ["proxy-a"]


def test_acquire_isolated_by_pool(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-ads-1", pool="ads")
    _register(repo_inst, r, "proxy-ads-2", pool="ads")
    _register(repo_inst, r, "proxy-data", pool="data-pipeline")
    for _ in range(50):
        node = repo_inst.acquire(pool="data-pipeline")
        assert node["node_id"] == "proxy-data"
    # ads 池只能拿到 ads 节点
    seen = {repo_inst.acquire(pool="ads")["node_id"] for _ in range(50)}
    assert seen <= {"proxy-ads-1", "proxy-ads-2"}


def test_acquire_no_match_raises(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a", pool="ads")
    with pytest.raises(NoHealthyNodeError):
        repo_inst.acquire(pool="nonexistent")


def test_acquire_best_respects_pool(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-ads-best", pool="ads", success_count="100", fail_count="0")
    _register(repo_inst, r, "proxy-other-best", pool="other", success_count="100", fail_count="0")
    for _ in range(10):
        assert repo_inst.acquire(pool="ads", mode="best")["node_id"] == "proxy-ads-best"


# ---------- sticky + pool ----------

def test_sticky_respects_pool(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-ads", pool="ads")
    _register(repo_inst, r, "proxy-data", pool="data")
    node, _ = repo_inst.acquire_sticky("acct-1", pool="ads", ttl=1800)
    assert node["node_id"] == "proxy-ads"
    # 再次请求 ads 池 -> 命中同一节点
    node2, hit = repo_inst.acquire_sticky("acct-1", pool="ads", ttl=1800)
    assert hit is True
    assert node2["node_id"] == "proxy-ads"
    # 请求 data 池 -> 绑定在 ads 不匹配，重新分配
    node3, hit = repo_inst.acquire_sticky("acct-1", pool="data", ttl=1800)
    assert hit is False
    assert node3["node_id"] == "proxy-data"


# ---------- 健康检查与质量封禁兼容 pool ----------

def test_record_check_and_ban_keep_pool(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a", pool="ads")
    for _ in range(5):
        repo_inst.record_check("proxy-a", ok=False)
    assert repo_inst.get("proxy-a")["status"] == "dead"
    assert repo_inst.get("proxy-a")["pool"] == "ads"
    repo_inst.ban("proxy-a", reason="low_success_rate")
    assert repo_inst.get("proxy-a")["pool"] == "ads"
