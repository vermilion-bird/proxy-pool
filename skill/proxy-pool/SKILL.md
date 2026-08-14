---
name: proxy-pool
description: 代理池（Proxy Pool）的获取与使用。当用户需要获取代理、使用代理发请求、按 region/pool 选择代理、使用 Sticky Proxy 固定出口 IP、用 Python/curl 走代理访问时使用本 skill。触发词：代理、proxy、代理池、获取代理、acquire、代理怎么用、走代理、出口IP、sticky。
metadata:
  short-description: 获取并使用代理
source:
  repository: https://github.com/vermilion-bird/proxy-pool
  license: MIT
---

# Proxy Pool 代理池使用 Skill

统一代理出口池，为数据采集、广告平台同步、API 请求等业务提供 HTTP/HTTPS/SOCKS5 代理。

## 获取一个代理

```bash
curl "https://proxy.8tb.cc/api/v1/proxies/acquire"
```

**响应示例：**

```json
{
  "proxy_id": "proxy-130.61.144.130",
  "host": "130.61.144.130",
  "port": "3128",
  "username": "3proxy",
  "password": "xxxxx",
  "protocol": "http",
  "region": "US",
  "pool": "default",
  "isp": "",
  "sticky": false
}
```

拿到后即可用：`http://<username>:<password>@<host>:<port>`

## 使用代理

### curl

```bash
# HTTP 代理（端口 3128）
curl -x "http://3proxy:<PASSWORD>@<HOST>:3128" https://api.ipify.org

# SOCKS5 代理（端口 1080）
curl --socks5-hostname "3proxy:<PASSWORD>@<HOST>:1080" https://api.ipify.org
```

### Python requests

```python
import requests

proxies = {
    "http": "http://3proxy:<PASSWORD>@<HOST>:3128",
    "https": "http://3proxy:<PASSWORD>@<HOST>:3128",
}
resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
print(resp.json())  # {"origin": "<出口IP>"}

# SOCKS5 需 pip install requests[socks]
proxies = {"http": "socks5://3proxy:<PASSWORD>@<HOST>:1080",
           "https": "socks5://3proxy:<PASSWORD>@<HOST>:1080"}
```

## 选择代理（可选参数）

```bash
# 按区域（US/JP/AP/EU...）
curl "https://proxy.8tb.cc/api/v1/proxies/acquire?region=US"

# 按业务池 / ISP
curl "https://proxy.8tb.cc/api/v1/proxies/acquire?pool=ads"
curl "https://proxy.8tb.cc/api/v1/proxies/acquire?region=US&pool=ads&isp=OCI"
```

## Sticky Proxy（固定出口 IP）

同一 `account_id` 始终返回同一节点（用于账号级同步需保持出口 IP 的场景）：

```bash
curl "https://proxy.8tb.cc/api/v1/proxies/acquire?account_id=acct-123"
```

## Python 客户端

`scripts/proxy_pool_client.py` 封装了获取 + 使用：

```bash
# 获取一个代理
python scripts/proxy_pool_client.py acquire --region US

# 获取代理并验证出口 IP（走代理访问，确认连通）
python scripts/proxy_pool_client.py test --node-id proxy-130.61.144.130
```

完整用法：`python scripts/proxy_pool_client.py --help`

## 环境变量

```env
PP_MGR_API=https://proxy.8tb.cc   # 管理 API 地址（默认已指向域名）
PP_API_KEY=                       # API 认证 Key（若已启用认证则必填）
```

> 若管理 API 已启用认证，请求需带 `X-API-Key: <KEY>` 头；`/health` 等公开端点除外。

## Tags
`proxy`, `proxy-pool`, `3proxy`, `http-proxy`, `socks5`, `scraping`, `data-collection`

## Compatibility
- Codex: ✅
- Claude Code: ✅
