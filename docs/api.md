# Proxy Pool 管理 API 参考

基础地址：`http://<管理服务器>:8082`  
交互式文档（FastAPI 自动生成）：`http://<管理服务器>:8082/docs`

---

## 认证

管理 API（`/api/v1/*`）通过 **API Key + IP 白名单** 双重防护（v1.1.0+）。

### 配置（环境变量）

| 变量 | 必填 | 说明 |
|------|:---:|------|
| `PP_API_KEYS` | 生产必配 | 逗号分隔的 API Key 列表，配置后所有 `/api/v1/*` 请求必须携带有效 Key |
| `PP_IP_WHITELIST` | 可选 | 逗号分隔的 IP / CIDR 白名单，配置后仅白名单来源可访问 |
| `PP_TRUST_PROXY` | 可选 | 部署于反向代理后置 `1`，此时来源 IP 取 `X-Forwarded-For` 首个地址 |

> 未配置 `PP_API_KEYS` 时认证关闭（向后兼容），但**生产环境必须配置**。

### 认证方式（二选一）

```bash
# 方式一：X-API-Key 请求头
curl -H "X-API-Key: <KEY>" http://<MGR>:8082/api/v1/nodes

# 方式二：Authorization: Bearer
curl -H "Authorization: Bearer <KEY>" http://<MGR>:8082/api/v1/nodes
```

### 错误响应

| 状态码 | 场景 |
|:---:|------|
| 401 | 缺少 / 无效 API Key |
| 403 | 来源 IP 不在白名单 |

> `/health`、`/version`、`/metrics` 为公开端点，**不受认证保护**（Prometheus 抓取需要）。

---

## 节点管理

### 注册节点

```
POST /api/v1/nodes/register
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| node_id | string | ✅ | 节点唯一标识 |
| ip | string | ✅ | 代理公网 IP |
| port | int | ✅ | HTTP 代理端口（默认 3128）|
| region | string | | 地域代码（US/JP/...），默认 US |
| pool | string | | 业务专属池（ads / data-pipeline / ...），默认 default |
| isp | string | | ISP 提供商（OCI / AWS / ...），默认空 |
| protocol | string | | http / socks5，默认 http |
| username | string | | 认证用户名 |
| password | string | | 认证密码 |

**示例：**

```bash
curl -X POST http://<MGR>:8082/api/v1/nodes/register \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "proxy-128.0.0.1",
    "ip": "128.0.0.1",
    "port": 3128,
    "region": "US",
    "protocol": "http",
    "username": "3proxy",
    "password": "<PASSWORD>"
  }'
```

**响应：**

```json
{ "node_id": "proxy-128.0.0.1" }
```

### 节点列表

```
GET /api/v1/nodes?region=US&pool=ads&isp=OCI
```

**响应：**

```json
{ "nodes": ["proxy-128.0.0.1", "proxy-129.0.0.1"] }
```

### 节点详情

```
GET /api/v1/nodes/{node_id}
```

**响应：**

```json
{
  "node_id": "proxy-128.0.0.1",
  "ip": "128.0.0.1",
  "port": "3128",
  "region": "US",
  "protocol": "http",
  "username": "3proxy",
  "password": "<PASSWORD>",
  "status": "healthy",
  "success_count": "12",
  "fail_count": "0",
  "latency": "82",
  "current_connections": "3"
}
```

### 删除节点

```
DELETE /api/v1/nodes/{node_id}
```

**响应：**

```json
{ "status": "deleted" }
```

### 节点心跳

```
POST /api/v1/nodes/{node_id}/heartbeat
```

**响应：**

```json
{ "status": "ok" }
```

---

## 代理使用

### 获取代理（分配）

```
GET /api/v1/proxies/acquire?region=US
```

| 参数 | 类型 | 说明 |
|------|------|------|
| region | string | 可选，按地域筛选（US/JP/...）|
| pool | string | 可选，业务专属池（ads / data-pipeline / ...）|
| isp | string | 可选，ISP 提供商（OCI / AWS / ...）|
| account_id | string | 可选，启用 Sticky Proxy（固定出口 IP）|

**响应增加 `sticky` 字段**：`true` 表示命中既有绑定，`false` 表示新绑定/切换。

**响应：**

```json
{
  "proxy_id": "proxy-128.0.0.1",
  "host": "128.0.0.1",
  "port": "3128",
  "username": "3proxy",
  "password": "<PASSWORD>",
  "protocol": "http",
  "region": "US",
  "pool": "default",
  "isp": "OCI"
}
```

业务系统拿到后即可：`http://3proxy:<PASSWORD>@128.0.0.1:3128`

> 分配策略：**健康节点过滤 → 智能评分**（成功率 0.35 + 延迟 0.30 + 负载 0.20 + 稳定性 0.15）。
> 默认 `weighted` 加权随机；设 `PP_SCHED_MODE=best` 启用确定性选最优。详见 [scheduling.md](scheduling.md)。

### 使用结果上报

```
POST /api/v1/proxies/report
```

**请求体：**

| 字段 | 类型 | 说明 |
|------|------|------|
| node_id | string | 使用的节点 |
| success | bool | 是否成功（默认 true）|
| latency | float | 延迟毫秒数（默认 0）|

**示例：**

```bash
curl -X POST http://<MGR>:8082/api/v1/proxies/report \
  -H "Content-Type: application/json" \
  -d '{"node_id":"proxy-128.0.0.1","success":true,"latency":82.5}'
```

**响应：**

```json
{ "status": "ok" }
```

> 上报数据会累加到节点的 `success_count` / `fail_count` / `latency`，
> 用于健康检查、质量评分封禁与智能调度。

### 释放粘性绑定

```
POST /api/v1/proxies/release
```

**请求体：** `{"account_id": "<ACCOUNT_ID>"}`

**响应：** `{"status": "released"}`

### 解封节点

```
POST /api/v1/nodes/{node_id}/unban
```

将被质量评分自动封禁（disabled）的节点人工恢复为 healthy。

**响应：** `{"node_id": "...", "status": "healthy"}`

---

## 系统

### 健康检查

```
GET /health
```

**响应：**

```json
{ "status": "ok" }
```

### 指标（Prometheus）

```
GET /metrics
```

Prometheus 可按此端点抓取（管理平台已内置 `prometheus:9090`）。

---

## 审计历史（PostgreSQL，v2.0）

管理 API 将节点生命周期 / 分配记录 / 使用上报写入 PostgreSQL（可选）。

**启用**：`docker-compose.yml` 中置 `PG_ENABLED=1`（默认 0，未启用时审计静默降级不影响业务）。

| 端点 | 说明 |
|------|------|
| `GET /api/v1/audit/events?node_id=&limit=` | 节点生命周期事件（注册/删除/封禁/解封/状态变迁）|
| `GET /api/v1/audit/acquires?node_id=&limit=` | 代理分配历史 |
| `GET /api/v1/audit/reports?node_id=&limit=` | 使用上报历史（success / latency_ms）|

**示例：**

```bash
curl -H "X-API-Key: <KEY>" "http://<MGR>:8082/api/v1/audit/events?node_id=proxy-128.0.0.1&limit=10"
```

**响应：** `{"events": [{"id": 1, "node_id": "...", "event_type": "registered", ...}]}`

---

## 错误码

| 状态码 | 场景 |
|:---:|------|
| 200 | 成功 |
| 404 | 节点不存在 |
| 503 | 无健康节点可用（代理池主要告警）|

---

## 调度与健康检查

分配策略、健康检查频率、故障摘除/恢复阈值，见 [scheduling.md](scheduling.md)。