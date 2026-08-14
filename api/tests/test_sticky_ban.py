"""Sticky Proxy 与质量评分封禁测试。"""

import pytest

from app.repositories.node_repository import NoHealthyNodeError, NodeRepository


class FakeRedis:
    """最小内存 Redis：覆盖 NodeRepository 用到的全部命令。"""

    def __init__(self):
        self._hash = {}
        self._set = {}
        self._str = {}   # string keys（sticky 绑定）
        self._ttl = {}

    # ---- hash ----
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

    # ---- set ----
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

    # ---- string（sticky）----
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
        "username": "3proxy",
        "password": "pw",
    }
    data.update({k: str(v) for k, v in overrides.items()})
    return repo.register(data)


# ---------- Sticky Proxy ----------

def test_sticky_binds_account(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    node, hit = repo_inst.acquire_sticky("acct-1", ttl=1800)
    assert hit is False
    assert node["node_id"] == "proxy-a"
    assert r.get("pp:sticky:acct-1") == "proxy-a"
    assert r._ttl.get("pp:sticky:acct-1") == 1800


def test_sticky_reuses_binding(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    _register(repo_inst, r, "proxy-b")
    first, _ = repo_inst.acquire_sticky("acct-1", ttl=1800)
    bound = first["node_id"]
    # 第二次：应命中同一节点（粘性）
    node, hit = repo_inst.acquire_sticky("acct-1", ttl=1800)
    assert hit is True
    assert node["node_id"] == bound


def test_sticky_fails_over_when_node_unhealthy(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    _register(repo_inst, r, "proxy-b")
    first, _ = repo_inst.acquire_sticky("acct-1", ttl=1800)
    bound = first["node_id"]
    other = "proxy-b" if bound == "proxy-a" else "proxy-a"
    # 绑定节点变 dead -> 应重新分配并更新绑定
    r.hset("pp:node:" + bound, mapping={"status": "dead"})
    node, hit = repo_inst.acquire_sticky("acct-1", ttl=1800)
    assert hit is False
    assert node["node_id"] == other
    assert r.get("pp:sticky:acct-1") == other


def test_sticky_respects_region(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-us", region="US")
    _register(repo_inst, r, "proxy-jp", region="JP")
    # 先按 US 绑定
    node, _ = repo_inst.acquire_sticky("acct-1", region="US", ttl=1800)
    assert node["node_id"] == "proxy-us"
    # 请求 JP 区域但绑定在 US -> 应重新分配
    node, hit = repo_inst.acquire_sticky("acct-1", region="JP", ttl=1800)
    assert hit is False
    assert node["node_id"] == "proxy-jp"
    # 再次请求 JP -> 命中新绑定
    node, hit = repo_inst.acquire_sticky("acct-1", region="JP", ttl=1800)
    assert hit is True
    assert node["node_id"] == "proxy-jp"


def test_sticky_release(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    repo_inst.acquire_sticky("acct-1", ttl=1800)
    assert r.get("pp:sticky:acct-1") == "proxy-a"
    repo_inst.release_sticky("acct-1")
    assert r.get("pp:sticky:acct-1") is None


# ---------- 质量评分封禁 ----------

def test_quality_score(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good")
    _register(repo_inst, r, "proxy-bad")
    r.hset("pp:node:proxy-good", mapping={"success_count": "90", "fail_count": "10"})
    r.hset("pp:node:proxy-bad", mapping={"success_count": "10", "fail_count": "90"})
    assert repo_inst.quality_score(repo_inst.get("proxy-good")) == pytest.approx(0.9)
    assert repo_inst.quality_score(repo_inst.get("proxy-bad")) == pytest.approx(0.1)


def test_quality_score_no_sample_is_full(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-fresh")
    assert repo_inst.quality_score(repo_inst.get("proxy-fresh")) == 1.0


def test_ban_marks_disabled(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    node = repo_inst.ban("proxy-a", reason="low_success_rate")
    assert node["status"] == "disabled"
    assert node["banned_reason"] == "low_success_rate"
    # disabled 不参与分配
    with pytest.raises(NoHealthyNodeError):
        repo_inst.acquire()


def test_unban_restores_healthy(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-a")
    repo_inst.ban("proxy-a", reason="low_success_rate")
    node = repo_inst.unban("proxy-a")
    assert node["status"] == "healthy"
    assert node["banned_reason"] == ""


def test_evaluate_quality_bans_low_success(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-good")
    _register(repo_inst, r, "proxy-bad")
    r.hset("pp:node:proxy-good", mapping={"success_count": "90", "fail_count": "10"})
    r.hset("pp:node:proxy-bad", mapping={"success_count": "10", "fail_count": "90"})
    banned = repo_inst.evaluate_quality(min_success_rate=0.5, min_requests=20)
    assert banned == ["proxy-bad"]
    assert repo_inst.get("proxy-bad")["status"] == "disabled"
    assert repo_inst.get("proxy-good")["status"] == "healthy"


def test_evaluate_quality_respects_min_requests(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-bad")
    # 样本不足（只有 5 次）不封禁
    r.hset("pp:node:proxy-bad", mapping={"success_count": "0", "fail_count": "5"})
    banned = repo_inst.evaluate_quality(min_success_rate=0.5, min_requests=20)
    assert banned == []
    assert repo_inst.get("proxy-bad")["status"] == "healthy"


def test_evaluate_quality_skips_manual_and_banned(repo):
    repo_inst, r = repo
    _register(repo_inst, r, "proxy-maint")
    _register(repo_inst, r, "proxy-banned")
    r.hset("pp:node:proxy-maint", mapping={"status": "maintenance", "success_count": "0", "fail_count": "100"})
    r.hset("pp:node:proxy-banned", mapping={"status": "disabled", "success_count": "0", "fail_count": "100"})
    banned = repo_inst.evaluate_quality(min_success_rate=0.5, min_requests=20)
    assert banned == []
