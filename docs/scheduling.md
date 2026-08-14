# 调度与健康检查策略

本页说明代理池的调度算法、健康检查机制、故障摘除与恢复策略，以及后续演进方向。

---

## 一、代理分配调度

### 当前（v1.1）：Weighted Random + Health Filter

```
健康节点集合（region 可选）
        │
        ▼
   计算每个节点权重 score
        │
        ▼
   按权重随机选择一个（random.choices）
        │
        ▼
   返回该节点
```

实现要点：

1. **过滤**：只从 `healthy` 节点中选（Redis 实时状态）。
2. **地域**：`region` 参数过滤节点区域。
3. **加权随机**：按 成功率 / 延迟 / 负载 三项加权计算得分，得分越高被选中概率越大；
   分数一致或全为 0 时退化为均匀随机（兼容无统计数据的新节点）。

权重公式（`NodeRepository._score`）：

```python
score = (
    0.5 * success_rate      # 成功率：成功数 / (成功+失败)，无数据视为 1.0
  + 0.3 * latency_score     # 延迟：1 - latency/1000ms（越低越高，1000ms 封顶为 0）
  + 0.2 * load_score        # 负载：1 - connections/10（越少越高，10 连接封顶为 0）
)
```

权重系数可通过环境变量调整：`PP_SCHED_W_SUCCESS` / `PP_SCHED_W_LATENCY` / `PP_SCHED_W_LOAD`
（默认 0.5 / 0.3 / 0.2），归一化阈值 `latency_threshold_ms`（默认 1000）与 `load_threshold`（默认 10）。

### 演进：Score Based Scheduler

后续引入评分，综合考虑多维度：

```python
score = (
    0.35 * success_score      # 成功率
  + 0.30 * latency_score      # 延迟（P50/P95）
  + 0.20 * load_score         # 并发连接（越少越高）
  + 0.15 * stability_score    # 稳定性 / 在线时长
)
```

选得分最高节点，兼顾质量与负载。

### 远期：Sticky Proxy

对广告平台 / 账号级数据同步，需保持同一账号固定出口 IP：

```text
account_id = 123456  ──►  proxy-03  ──►  proxy-03  ──►  proxy-03
```

Redis：`proxy:sticky:{account_id}` + TTL（30min / 1h / 6h）。
粘性期间节点若故障，需降级策略（等待恢复 / 切换到备用）。

---

## 二、健康检查

### 检查频率（v1.1 已实现：自动后台巡检）

| 等级 | 频率 | 内容 | 实现 |
|------|------|------|:---:|
| 基础心跳 | 10s | 节点 Agent 上报（`/heartbeat`）| ✅ |
| 代理检测 | `PP_HC_INTERVAL`（默认 30s）| TCP 拨号 3128 + HTTP 经代理探测 | ✅ 自动巡检 |
| 深度检测 | 5min | CONNECT HTTPS + 公网 IP 校验 | 规划中 |

管理平台启动后自动运行 **HealthChecker 后台任务**，按 `PP_HC_INTERVAL` 周期扫描全部节点：

1. **TCP**：`socket.create_connection(ip:port, timeout)` 可建连（必做，记录拨号延迟）
2. **HTTP**：经代理访问 `PP_HC_PROBE_URL`（默认 `http://example.com`，`PP_HC_HTTP_PROBE=0` 可关闭）

### 状态机与防抖（v1.1 已实现）

检查结果经 `record_check()` 应用状态机，**连续 N 次**判断避免抖动：

```text
连续失败 1~2 次 → 记录（保持 healthy）
连续失败 3 次   → degraded（摘除，不再参与分配）   [PP_HC_FAIL_DEGRADED]
连续失败 5 次   → dead                            [PP_HC_FAIL_DEAD]

dead / degraded 连续成功 3 次 → healthy（重新入池）[PP_HC_RECOVER]

maintenance / disabled → 跳过自动检查与迁移（人工状态）
```

- 状态字段：`status` / `consecutive_failures` / `consecutive_successes` / `latency`
- 状态变迁写入指标 `proxy_pool_node_state_changes_total`（`transition` 标签）
- 探活超时 `PP_HC_TIMEOUT`（默认 5s）

---

## 三、节点状态机与故障摘除

### 状态

| 状态 | 说明 | 是否参与分配 |
|------|------|:---:|
| starting | 启动中 | ❌ |
| **healthy** | 正常可用 | ✅ |
| degraded | 性能下降 / 部分失败 | ❌ |
| dead | 不可用 | ❌ |
| maintenance | 人工维护 | ❌ |
| disabled | 管理员禁用 | ❌ |

### 故障摘除（防抖）

```text
连续 1 次失败 → 记录
连续 3 次失败 → degraded（摘除）
连续 5 次失败 → dead
```

### 恢复

```text
dead
  └─ 连续 3 次成功 → healthy（重新入池）
```

用「连续 N 次」替代单次判断，**避免节点在正常/异常间反复抖动**。
摘除与恢复均需满足连续阈值，保证调度稳定。

---

## 四、Redis 数据模型

| Key | 类型 | 说明 |
|-----|------|------|
| `proxy:node:{node_id}` | Hash | 节点详情 + 统计 |
| `proxy:pool` | Set | 全部节点 ID |
| `proxy:nodes:region:{code}` | Set | 地域节点 |
| `proxy:heartbeat:{node_id}` | String | 心跳（TTL 60s）|
| `proxy:sticky:{account_id}` | String | 粘性绑定（远期）|

节点 Hash 字段：`ip / port / region / protocol / username / password /
status / success_count / fail_count / latency / current_connections / last_check`

---

## 五、监控与告警

### Prometheus 指标（`/metrics`）

```
proxy_node_status                    节点健康（1=healthy, 0=unhealthy）
proxy_node_latency                   节点延迟
proxy_node_success_rate              节点成功率
proxy_node_requests_total            总请求数
proxy_node_errors_total              错误数
proxy_node_active_connections        活跃连接
proxy_acquire_total                  分配次数
proxy_acquire_failed_total           分配失败
```

### 核心告警

| 告警 | 条件 |
|------|------|
| 节点离线 | `proxy_node_status == 0` 持续 > 1min |
| 成功率过低 | `success_rate < 95%` |
| 延迟异常 | P95 latency > 1000ms |
| 连接数过高 | `active_connections > 阈值` |
| **健康节点不足** | `healthy_nodes < 3`（核心业务告警）|

---

## 六、路线图

- [x] Weighted Random（成功率/延迟加权）
- [x] 健康检查增强（TCP/HTTP 探活 + 状态机防抖摘除/恢复）
- [x] 管理 API 认证（API Key + IP 白名单）
- [ ] Score Based Scheduler
- [ ] Sticky Proxy + 降级策略
- [ ] 区域池 / ISP 池 / 业务专属池
- [ ] 自动封禁节点 / 节点质量评分
- [ ] 多租户 / API Key / 代理套餐