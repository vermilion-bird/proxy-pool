# 代理池使用说明

## 架构概览

```
应用/爬虫 → 代理池 API → 动态调度 → 3proxy 节点
                ↓
         Prometheus + Grafana（监控/看板）
```

- **管理端**: http://158.180.87.150:8082 — FastAPI 代理池管理 API
- **监控**: http://158.180.87.150:9090 — Prometheus
- **看板**: http://158.180.87.150:3000 — Grafana（账号 `admin` / `admin123`）
- **节点**: 分布于 US / EU / AP 区域，HTTP(S) 3128 端口 + SOCKS5 1080 端口

---

## 快速开始

### 获取一个代理

```bash
curl -s "http://158.180.87.150:8082/api/v1/proxies/acquire?region=US"
```

返回示例：

```json
{
  "proxy_id": "proxy-130.61.144.130",
  "host": "130.61.144.130",
  "port": "3128",
  "username": "3proxy",
  "password": "xxxxx",
  "protocol": "http",
  "region": "US"
}
```

### 立即使用代理

**curl 示例**:

```bash
# 使用 HTTP 代理
curl -x http://3proxy:password@host:3128 https://httpbin.org/ip

# 使用 SOCKS5 代理
curl --socks5 3proxy:password@host:1080 https://httpbin.org/ip
```

**Python requests 示例**:

```python
import requests

# HTTP 代理
proxies = {
    "http": "http://3proxy:password@host:3128",
    "https": "http://3proxy:password@host:3128",
}
resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
print(resp.json())

# SOCKS5 代理（需 pip install requests[socks]）
proxies = {
    "http": "socks5://3proxy:password@host:1080",
    "https": "socks5://3proxy:password@host:1080",
}
resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
print(resp.json())
```

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |
| GET | `/api/v1/nodes` | 列出所有节点（可选 `?region=US`） |
| GET | `/api/v1/nodes/{node_id}` | 获取节点详情 |
| POST | `/api/v1/nodes/register` | 注册新节点 |
| POST | `/api/v1/nodes/{node_id}/heartbeat` | 节点心跳 |
| DELETE | `/api/v1/nodes/{node_id}` | 删除节点 |
| GET | `/api/v1/proxies/acquire` | 获取一个可用代理 (query param) |
| POST | `/api/v1/proxies/report` | 上报代理使用结果 |

### 获取代理列表

```bash
# 全部节点
curl -s http://158.180.87.150:8082/api/v1/nodes

# 按区域筛选
curl -s "http://158.180.87.150:8082/api/v1/nodes?region=US"

# 查看节点详情
curl -s http://158.180.87.150:8082/api/v1/nodes/proxy-161.33.44.38
```

### 获取代理（动态调度）

```bash
# GET 接口 (注意: 用 query param 传 region, 不是 POST body)
curl -s "http://158.180.87.150:8082/api/v1/proxies/acquire?region=US"
# 不带 region 则任意区域:
curl -s "http://158.180.87.150:8082/api/v1/proxies/acquire"
```

支持参数: 仅 `region` (协议是节点固有属性, 不做请求过滤):

```
?region=US     // 可选，指定区域 (US/EU/AP)
```

调度策略：健康检查 + 自动故障转移 → 选择成功率最高、连接数最少的节点。

> ⚠️ 真实接口是 **GET**。旧版本文档写的 `POST /api/v1/proxies/acquire` 有误。

### 上报代理使用结果

完成请求后将结果上报，帮助系统优化调度：

```bash
curl -s -X POST http://158.180.87.150:8082/api/v1/proxies/report \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "proxy-161.33.44.38",
    "success": true,
    "latency": 0.28
  }'
```

> ⚠️ 上报字段是 **`latency`**（秒，float），不是 `latency_ms`。

### 注册新节点（部署时才用）

```bash
curl -s -X POST http://158.180.87.150:8082/api/v1/nodes/register \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "proxy-xxx.xxx.xxx.xxx",
    "ip": "xxx.xxx.xxx.xxx",
    "port": 3128,
    "socks_port": 1080,
    "protocol": "http",
    "region": "US",
    "username": "3proxy",
    "password": "节点密码",
    "status": "healthy"
  }'
```

---

## 编程使用

> 💡 **推荐直接使用可复用客户端** `client/`（`proxypool_client.ProxyPool`）：
> 已按真实接口实现（GET acquire / latency 上报），含自动重试、故障切换、会话模式。
> 下方是纯 requests 手写示例，仅作参考。

### Python 封装示例

```python
import requests
from typing import Optional

class ProxyPool:
    """代理池客户端"""

    def __init__(self, api_base: str = "http://158.180.87.150:8082"):
        self.api_base = api_base.rstrip("/")

    def acquire(self, region: Optional[str] = None,
                protocol: Optional[str] = None) -> dict:
        """获取一个代理"""
        payload = {}
        if region:
            payload["region"] = region
        if protocol:
            payload["protocol"] = protocol
        resp = requests.post(
            f"{self.api_base}/api/v1/proxies/acquire",
            json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def report(self, node_id: str, success: bool,
               latency_ms: int = 0):
        """上报使用结果"""
        resp = requests.post(
            f"{self.api_base}/api/v1/proxies/report",
            json={
                "node_id": node_id,
                "success": success,
                "latency_ms": latency_ms
            }, timeout=5)
        resp.raise_for_status()

    def list_nodes(self, region: Optional[str] = None) -> list:
        """列出节点"""
        params = {"region": region} if region else {}
        resp = requests.get(
            f"{self.api_base}/api/v1/nodes",
            params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()["nodes"]

    def request_via_proxy(self, url: str,
                          region: Optional[str] = None,
                          timeout: int = 30) -> requests.Response:
        """通过代理池获取代理并发起请求"""
        proxy = self.acquire(region=region)
        proxy_url = f"{proxy['protocol']}://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            resp = requests.get(url, proxies=proxies, timeout=timeout)
            self.report(proxy["proxy_id"], True, latency_ms=int(resp.elapsed.total_seconds() * 1000))
            return resp
        except Exception as e:
            self.report(proxy["proxy_id"], False)
            raise
```

### 使用示例

```python
pool = ProxyPool()

# 获取美国区域的代理
proxy = pool.acquire(region="US")
print(f"代理: {proxy['host']}:{proxy['port']}")

# 通过代理请求
resp = pool.request_via_proxy("https://httpbin.org/ip", region="US")
print(f"出口 IP: {resp.json()['origin']}")
```

### 批量请求（自动管理代理）

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

pool = ProxyPool()
urls = [
    "https://httpbin.org/ip",
    "https://api.ipify.org?format=json",
    "https://ip-api.com/json",
]

def fetch(url):
    try:
        resp = pool.request_via_proxy(url, timeout=15)
        return url, resp.json()
    except Exception as e:
        return url, str(e)

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch, url): url for url in urls}
    for future in as_completed(futures):
        url, result = future.result()
        print(f"{url}: {result}")
```

---

## 应用配置

### 浏览器配置

**Chrome 命令行**:

```bash
# HTTP 代理
chromium --proxy-server=http://3proxy:password@host:3128

# SOCKS5 代理
chromium --proxy-server=socks5://3proxy:password@host:1080
```

**SwitchyOmega (Chrome 插件)**:
1. 新建情景模式 → 代理服务器
2. 协议: HTTP / SOCKS5
3. 服务器: 节点 IP
4. 端口: 3128 / 1080
5. 身份验证: 用户名 `3proxy` + 密码

### 系统代理

**Linux/macOS**:

```bash
export http_proxy="http://3proxy:password@host:3128"
export https_proxy="http://3proxy:password@host:3128"
export all_proxy="socks5://3proxy:password@host:1080"
```

**Windows PowerShell**:

```powershell
$env:http_proxy="http://3proxy:password@host:3128"
$env:https_proxy="http://3proxy:password@host:3128"
```

### Docker 容器

```bash
docker run -e HTTP_PROXY="http://3proxy:password@host:3128" \
           -e HTTPS_PROXY="http://3proxy:password@host:3128" \
           your-image
```

### curl / wget

```bash
curl -x http://3proxy:password@host:3128 https://example.com
wget -e use_proxy=yes -e http_proxy=http://3proxy:password@host:3128 https://example.com
```

---

## 监控与看板

### Grafana 看板

访问 http://158.180.87.150:3000/d/proxy-pool-overview

提供 9 个面板：
1. **Registered Nodes** — 总节点数（瞬时值）
2. **Healthy Nodes** — 健康节点数
3. **Healthy Nodes by Region** — 各区域健康节点（时间序列）
4. **API Requests/sec** — API 总请求量
5. **Acquire/sec** — 代理获取速率（成功/失败）
6. **Report throughput** — 上报成功率/失败率
7. **Report Latency (p50/p95/p99)** — 代理延迟分位数
8. **Register/Heartbeat Rate** — 注册/心跳速率
9. **Node State Transitions** — 节点状态变更

### Prometheus 指标

API 监控端: http://158.180.87.150:8082/metrics

| 指标 | 类型 | 说明 |
|------|------|------|
| `proxy_pool_nodes_total` | Gauge | 已注册节点总数 |
| `proxy_pool_nodes_healthy` | Gauge | 健康节点数 |
| `proxy_pool_nodes_healthy_by_region` | GaugeVec | 各区域健康节点数（标签: region） |
| `proxy_pool_acquire_total` | Counter | 代理获取总次数 |
| `proxy_pool_acquire_errors_total` | Counter | 代理获取失败次数 |
| `proxy_pool_report_total` | Counter | 代理上报总次数（标签: status=success/fail） |
| `proxy_pool_report_latency_seconds` | Histogram | 代理延迟分布 |
| `proxy_pool_register_total` | Counter | 节点注册总次数 |
| `proxy_pool_hearbeat_total` | Counter | 心跳接收总次数 |
| `proxy_pool_node_state_changes_total` | Counter | 节点状态变更总次数（标签: region, status） |
| `proxy_pool_http_requests_total` | Counter | HTTP 请求总次数（标签: method, endpoint, status） |

---

## 节点信息

| 区域 | 节点 IP | HTTP 端口 | SOCKS5 端口 | 状态 |
|------|---------|-----------|-------------|------|
| US | 130.61.144.130 | 3128 | 1080 | ✅ 健康 |
| US | 192.9.249.67 | 3128 | 1080 | ✅ 健康 |
| US | 158.180.87.150 | 3128 | 1080 | ✅ 健康 |
| US | 192.9.148.250 | 3128 | 1080 | ✅ 已注册 |
| US | 138.2.123.29 | 3128 | 1080 | ✅ 健康 |
| EU | 143.47.186.111 | 3128 | 1080 | ✅ 健康 |
| EU | 140.83.82.237 | 3128 | 1080 | ⚠️ OCI 防火墙 |
| EU | 141.144.198.198 | 3128 | 1080 | ✅ 健康 |
| EU | 138.3.242.126 | 3128 | 1080 | ✅ 健康 |
| AP | 161.33.44.38 | 3128 | 1080 | ✅ 健康 |

> **注意**: 部分 OCI 节点默认防火墙未开放 3128/1080 端口，白名单模式（仅允许指定 IP 访问）。如需从外部直连这些节点，请配置安全组规则。

---

## 常见问题

### 代理连接失败

1. **检查节点健康状态**
   ```bash
   curl -s http://158.180.87.150:8082/api/v1/nodes/proxy-NODE_IP
   ```
   确认 `status` 为 `healthy`。

2. **检查网络连通性**
   ```bash
   telnet NODE_IP 3128
   curl -x http://3proxy:password@NODE_IP:3128 https://httpbin.org/ip
   ```

3. **防火墙 / 安全组**
   - OCI: 检查入站规则是否允许目标端口
   - 其他云: 检查安全组/防火墙规则

### 获取代理返回空

- 所有节点可能都已标记为不健康
- 检查 Prometheus / Grafana 看状态
- 检查 `pp-api` 容器的 Redis 连接

### 代理速度慢

- 使用 `region` 参数选择离目标最近的区域
- 检查节点带宽和连接数
- 在 Grafana 查看 `Report Latency` 面板

### 添加新节点

参见 [DEPLOY.md](./DEPLOY.md) 或使用自动部署脚本：

```bash
# 1. 在新节点上安装 3proxy
curl -sL https://github.com/3proxy/3proxy/archive/refs/tags/0.9.4.tar.gz | tar xz
cd 3proxy-0.9.4
make -f Makefile.Linux
sudo make -f Makefile.Linux install

# 2. 编写配置（含用户认证）
# 3. 启动 3proxy
# 4. 注册到代理池
curl -X POST http://158.180.87.150:8082/api/v1/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"node_id":"proxy-IP","ip":"IP",...}
```

---

> 通过操作: 2026-08-13 | 版本: v1.0