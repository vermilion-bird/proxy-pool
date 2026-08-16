# 代理池 Python 客户端 (可复用)

可在任何项目的虚拟环境/vendor 目录里直接使用, 无需依赖代理池 API 代码。

## 目录

```
client/
├── proxypool_client.py   # 客户端实现
├── __init__.py           # 包导出
├── README.md
└── examples/
    └── usage.py          # 完整示例
```

## 安装

无第三方硬依赖 (仅需 `requests`; 用 httpx 时需 `pip install httpx`,
用 SOCKS5 时需 `requests[socks]`):

```bash
pip install requests httpx
```

把 `client/` 拷到项目里当作 vendored 包引用, 或 `pip install -e ./client` (若加 pyproject)。

## 快速开始

```python
from proxypool_client import ProxyPool

pool = ProxyPool(region="US")

# 1) 单次请求 (自动 acquire + report + 故障切换)
resp = pool.request_via_proxy("https://httpbin.org/ip")
print("出口 IP:", resp.json()["origin"])

# 2) 会话级 (一个节点复用, 退出自动上报)
with pool.session(region="US") as s:
    r1 = s.requests_get("https://api.ipify.org?format=json")
    r2 = s.requests_get("https://httpbin.org/headers")
    print(r1.json()["ip"])
```

## 配置 (环境变量)

| 变量 | 说明 | 默认 |
|------|------|------|
| `PROXY_POOL_API_BASE` | 代理池 API 地址 | `http://158.180.87.150:8082` |
| `PROXY_POOL_REGION` | 默认区域 (US/EU/AP) | 无 |
| `PROXY_POOL_PROTOCOL` | 默认协议 (http/socks5) | 无 |

也可以在构造时传入: `ProxyPool(api_base=..., region=..., protocol=...)`。

## 关键 API

| 方法 | 说明 |
|------|------|
| `acquire(region, protocol)` | 获取一个健康代理 (GET) |
| `report(proxy_id, success, latency_ms)` | 上报结果 (注意 API 字段是 `latency` 秒) |
| `list_nodes(region)` | 列出健康节点 |
| `request_via_proxy(url, ...)` | requests 单次请求, 失败自动切换节点 |
| `request_via_httpx(url, ...)` | httpx 单次请求, 失败自动切换节点 |
| `session(region, protocol)` | 会话级单节点复用, 退出自动上报 |

`acquire` 返回示例:

```json
{
  "proxy_id": "proxy-130.61.144.130",
  "host": "130.61.144.130",
  "port": 3128,
  "username": "3proxy",
  "password": "***",
  "protocol": "http",
  "region": "US"
}
```

> ⚠️ **与 API 的差异说明**: 真实接口里 `acquire` 是 **GET** (query 传 region),
> `report` 的字段是 **`latency`**(秒) 而非 `latency_ms`。旧文档 (PROXY_POOL_USAGE.md)
> 里写的 POST acquire / latency_ms 有误, 本客户端已按真实接口实现。

## 故障切换

`request_via_proxy` / `request_via_httpx` 在遇到请求异常时会:
1. `report(proxy_id, False)` 通知池子该节点失败;
2. 重新 acquire 一个新节点;
3. 最多重试 `max_failover` 次 (默认 3)。

会话模式 (`session()`) 不自动切换 — 适合批量且愿意承担单节点风险的场景,
可自行在 `except` 里重新进入会话。