# Proxy Pool · 自建代理池管理平台

基于 **FastAPI + Redis + 3proxy + Prometheus + Grafana + Docker Compose** 的统一代理出口池，
为内部数据采集、广告平台数据同步、API 请求等业务提供 **稳定、可控、可监控** 的 HTTP/HTTPS/SOCKS5 代理能力。

支持从 5 台节点弹性扩展到几十、上百台。

---

## ✨ 核心能力

- **统一管理入口** — 业务系统只对接 FastAPI，不直接依赖具体代理服务器
- **多协议** — 每节点同时提供 HTTP(3128) + SOCKS5(1080)
- **动态调度** — 按地域 / 健康状态 / 负载的加权随机分配
- **健康检查** — 定时 TCP/HTTP 探活，故障节点自动摘除、恢复自动回池
- **强认证** — 3proxy 用户名密码认证 + 管理 API 隔离
- **可观测** — Prometheus 指标 + Grafana 看板
- **一键部署** — Docker Compose 标准化编排 + 可扩展节点 Agent

---

## 🏗 架构

```text
                     ┌────────────────────────────────┐
                     │           业务系统              │
                     │  Data Pipeline / API / 采集     │
                     └──────────────┬─────────────────┘
                                    │ HTTP API
                     ┌──────────────▼─────────────────┐
                     │          FastAPI                │
                     │   Proxy Manager / 调度 / 健康    │
                     └──────────────┬─────────────────┘
                                    │
                     ┌──────────────▼─────────────────┐
                     │            Redis                │
                     │   节点状态 / 心跳 / 分配 / 统计   │
                     └──┬───────────┬───────────┬──────┘
                        │           │           │
              ┌─────────▼──┐  ┌─────▼────┐  ┌───▼─────────┐
              │ 3proxy-01  │  │3proxy-02 │  │ 3proxy-...  │
              │  HTTP/S5   │  │ HTTP/S5  │  │  HTTP/S5    │
              └─────┬──────┘  └─────┬────┘  └─────┬───────┘
                    │               │             │
                    └───────────────┼─────────────┘
                                    ▼
                                 Internet
                                  /    \
                        Prometheus     Grafana
                                     (监控/告警)
```

`FastAPI` 控制面与 `Prometheus/Grafana` 监控体系**分离**，互不影响。

---

## 📁 目录结构

```text
proxy-pool/
├── README.md              # 本文件
├── docs/
│   ├── api.md             # 管理 API 参考
│   ├── deployment.md      # 部署指南
│   └── scheduling.md      # 调度与健康检查策略
├── api/                   # FastAPI 管理服务源码
│   └── app/
├── scripts/               # 运维脚本
│   ├── setup_pool.py      # 节点注册 + 验证脚本
│   └── nodes.example.json # 节点模板（脱敏）
├── CREDENTIALS.example.md # 凭据模板（脱敏，真实凭据不入库）
├── nodes.example.json     # 节点清单模板
└── .gitignore
```

---

## 🔌 快速开始

### 1. 启动管理平台（控制面）

```bash
# 在管控服务器（如 158.180.87.150）上
git clone https://github.com/vermilion-bird/proxy-pool.git
cd proxy-pool
docker compose up -d --build
```

**服务端口：**

| 服务 | 端口 | 说明 |
|------|------|------|
| FastAPI | 8082 | 代理管理 API |
| Redis | 6380 | 实时状态（内网）|
| Prometheus | 9090 | 指标采集 |
| Grafana | 3000 | 监控看板 (admin/admin) |

### 2. 部署 3proxy 节点

每台代理服务器部署 3proxy（HTTP 3128 + SOCKS5 1080）：

```bash
# 节点侧，以 5 台为例
curl -x http://3proxy:***@<NODE_IP>:3128 https://api.ipify.org   # 验证
```

> 完整节点侧部署与凭据轮换见 [docs/deployment.md](docs/deployment.md)

### 3. 注册节点 + 验证

```bash
python3 scripts/setup_pool.py
```

脚本会自动：读取各节点密码 → 注册到管理平台 → 端到端验证（acquire → 走代理 → 出口 IP）。

---

## 🌐 管理 API 速览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/nodes/register` | 节点注册 |
| GET | `/api/v1/nodes` | 节点列表（可按 `region` 过滤）|
| GET | `/api/v1/nodes/{id}` | 节点详情 |
| DELETE | `/api/v1/nodes/{id}` | 删除节点 |
| POST | `/api/v1/nodes/{id}/heartbeat` | 节点心跳 |
| GET | `/api/v1/proxies/acquire` | **获取代理**（按 region）|
| POST | `/api/v1/proxies/report` | 使用结果上报 |
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

consilient 示例：

```bash
# 获取一个 US 节点
curl "http://<MGR>:8082/api/v1/proxies/acquire?region=US"

# 使用后上报
curl -X POST http://<MGR>:8082/api/v1/proxies/report \
  -H "Content-Type: application/json" \
  -d '{"node_id":"proxy-128.0.0.1","success":true,"latency":82.5}'
```

详情见 [docs/api.md](docs/api.md)。

---

## 📊 监控指标

API 暴露 Prometheus 业务指标（`GET /metrics`），Grafana 看板（`Proxy Pool / Overview`）已自动配置。

| 指标 | 类型 | 说明 |
|------|------|------|
| `proxy_pool_nodes_total` | Gauge | 已注册节点总数 |
| `proxy_pool_nodes_healthy` | Gauge | 健康节点数 |
| `proxy_pool_nodes_healthy_by_region` | Gauge | 各区域健康节点数（`region` 标签）|
| `proxy_pool_acquire_total` | Counter | 代理分配次数（`region` 标签）|
| `proxy_pool_acquire_errors_total` | Counter | 分配失败次数（无健康节点 → 503）|
| `proxy_pool_report_total` | Counter | 使用结果上报次数（`result`: success/failure）|
| `proxy_pool_report_latency_seconds` | Histogram | 上报的上游延迟（秒）|
| `proxy_pool_register_total` | Counter | 节点注册次数 |
| `proxy_pool_heartbeat_total` | Counter | 节点心跳次数 |
| `proxy_pool_node_state_changes_total` | Counter | 节点状态变迁（`transition` 标签）|
| `proxy_pool_http_requests_total` | Counter | 管理 API 请求量（`method`/`path` 标签）|

Grafana 面板：池规模、按区域健康节点、请求 QPS、acquire 成功/失败、上报吞吐、延迟分位数（p50/p95/p99）、注册/心跳速率、状态变迁。

---

## 🗺 路线图

- [x] 基础代理能力（5 节点 3proxy）— HTTP/SOCKS5 + 认证
- [x] Proxy Manager（FastAPI + Redis）— 注册/心跳/分配/上报
- [x] 健康检查 + 故障摘除/恢复闭环
- [x] 监控（Prometheus + Grafana）
- [x] 强密码轮换 + 防火墙加固
- [ ] 加权调度 / 粘性 Proxy
- [ ] PostgreSQL 历史与审计
- [ ] 管理 API 认证（API Key）
- [ ] 节点 Agent 增强

---

## 🔒 安全说明

- 3proxy 使用**用户名 + 随机强密码**认证，禁止裸跑公网
- 管理 API 建议后续叠加 **API Key + IP 白名单**
- 真实凭据**不入库**（见 [CREDENTIALS.example.md](CREDENTIALS.example.md)）
- 云平台安全组 + 主机 iptables **白名单**双重加固