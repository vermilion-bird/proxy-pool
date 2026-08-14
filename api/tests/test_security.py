"""管理 API 认证功能测试：API Key + IP 白名单。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


class FakeRepo:
    """替换真实 NodeRepository，避免测试依赖 Redis。"""

    def __init__(self, *args, **kwargs):
        pass

    def all_nodes(self):
        return []

    def healthy_nodes(self, region=None, pool=None, isp=None):
        return []


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    import app.api.nodes as nodes_mod

    monkeypatch.setattr(nodes_mod, "NodeRepository", FakeRepo)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------- 公开端点（不需要认证） ----------

def test_public_endpoints_need_no_key(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    assert client.get("/health").status_code == 200
    assert client.get("/version").status_code == 200
    assert client.get("/metrics").status_code == 200


# ---------- API Key 认证 ----------

def test_auth_disabled_when_no_keys_configured(client, monkeypatch):
    monkeypatch.delenv("PP_API_KEYS", raising=False)
    resp = client.get("/api/v1/nodes")
    assert resp.status_code == 200, resp.text


def test_missing_key_rejected(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    resp = client.get("/api/v1/nodes")
    assert resp.status_code == 401, resp.text


def test_wrong_key_rejected(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    resp = client.get("/api/v1/nodes", headers={"X-API-Key": "sk-wrong"})
    assert resp.status_code == 401, resp.text


def test_x_api_key_header_accepted(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret,sk-second")
    resp = client.get("/api/v1/nodes", headers={"X-API-Key": "sk-second"})
    assert resp.status_code == 200, resp.text


def test_bearer_token_accepted(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    resp = client.get("/api/v1/nodes", headers={"Authorization": "Bearer sk-secret"})
    assert resp.status_code == 200, resp.text


# ---------- IP 白名单 ----------

def test_ip_whitelist_blocks_unknown_ip(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    monkeypatch.setenv("PP_IP_WHITELIST", "10.0.0.0/8,192.168.1.5")
    monkeypatch.setenv("PP_TRUST_PROXY", "1")
    resp = client.get(
        "/api/v1/nodes",
        headers={"X-API-Key": "sk-secret", "X-Forwarded-For": "203.0.113.9"},
    )
    # 模拟来源 IP 203.0.113.9 不在白名单 → 403
    assert resp.status_code == 403, resp.text


def test_ip_whitelist_allows_matching_ip(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    monkeypatch.setenv("PP_IP_WHITELIST", "10.0.0.0/8,192.168.1.5")
    monkeypatch.setenv("PP_TRUST_PROXY", "1")
    resp = client.get(
        "/api/v1/nodes",
        headers={"X-API-Key": "sk-secret", "X-Forwarded-For": "10.1.2.3"},
    )
    # 模拟来源 IP 10.1.2.3 在 10.0.0.0/8 内 → 放行
    assert resp.status_code == 200, resp.text


def test_ip_whitelist_with_trust_proxy(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    monkeypatch.setenv("PP_IP_WHITELIST", "203.0.113.9")
    monkeypatch.setenv("PP_TRUST_PROXY", "1")
    # X-Forwarded-For 取第一个 IP，且代理链中最后一个才是直连来源
    resp = client.get(
        "/api/v1/nodes",
        headers={"X-API-Key": "sk-secret", "X-Forwarded-For": "203.0.113.9, 10.1.1.1"},
    )
    assert resp.status_code == 200, resp.text


# ---------- 写接口同样受保护 ----------

def test_register_requires_key(client, monkeypatch):
    monkeypatch.setenv("PP_API_KEYS", "sk-secret")
    resp = client.post(
        "/api/v1/nodes/register",
        json={"node_id": "proxy-1.2.3.4", "ip": "1.2.3.4", "port": 3128},
    )
    assert resp.status_code == 401, resp.text
