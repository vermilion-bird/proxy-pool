# Proxy Pool 管理 API 参考

基础地址：`http://<管理服务器>:8082`  
交互式文档（FastAPI 自动生成）：`http://<管理服务器>:8082/docs`

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
GET /api/v1/nodes?region=US
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

**响应：**

```json
{
  "proxy_id": "proxy-128.0.0.1",
  "host": "128.0.0.1",
  "port": "3128",
  "username": "3proxy",
  "password": "<PASSWORD>",
  "protocol": "http",
  "region": "US"
}
```

业务系统拿到后即可：`http://3proxy:<PASSWORD>@128.0.0.1:3128`

> ⚠️ 分配基于**健康节点 + 随机**；后续将升级为「健康 → 负载 → 成功率 → 延迟 → 加权随机」评分调度，见 [scheduling.md](scheduling.md)。

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
> 用于健康检查与后续的加权调度。

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

## 错误码

| 状态码 | 场景 |
|:---:|------|
| 200 | 成功 |
| 404 | 节点不存在 |
| 503 | 无健康节点可用（代理池主要告警）|

---

## 调度与健康检查

分配策略、健康检查频率、故障摘除/恢复阈值，见 [scheduling.md](scheduling.md)。