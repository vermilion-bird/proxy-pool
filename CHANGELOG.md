# Changelog

本项目的所有重要变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（SemVer）。

## [Unreleased]

### Added

- **加权随机调度**（v1.1.0）：替换纯随机的 acquire 分配
  - 按 成功率(0.5) + 延迟(0.3) + 负载(0.2) 加权随机选择健康节点
  - 分数一致或全 0 时退化为均匀随机，兼容无统计数据的节点
  - 权重系数可经 `PP_SCHED_W_SUCCESS` / `PP_SCHED_W_LATENCY` / `PP_SCHED_W_LOAD` 调整
  - 单元测试：`api/tests/test_scheduling.py`（11 个用例，含 2000 次抽样统计验证）
- **管理 API 认证**（v1.1.0）：API Key + IP 白名单双重防护
  - `X-API-Key` 或 `Authorization: Bearer` 两种认证方式（防时序攻击比较）
  - IP / CIDR 白名单（`PP_IP_WHITELIST`），可选反向代理信任（`PP_TRUST_PROXY`）
  - `/api/v1/*` 全部路由受保护；`/health`、`/version`、`/metrics` 保持公开
  - 未配置 Key 时向后兼容放行，生产环境必须配置（`.env.example` 模板）
  - `scripts/setup_pool.py` 支持 `PP_API_KEY` 自动携带认证头
  - 单元测试：`api/tests/test_security.py`（10 个用例，API Key / 白名单 / 代理信任 / 写接口）

## [1.0.0] - 2026-08-13

首个正式版本：Proxy Pool 代理池管理平台 MVP 完成并上线。
基础代理能力（HTTP/SOCKS5 + 认证）、Proxy Manager（FastAPI + Redis）、
健康检查闭环、Prometheus/Grafana 监控全部就绪。

### Added

- **代理池管理平台**（FastAPI + Redis + 3proxy + Prometheus + Grafana + Docker Compose）
  - 节点注册 / 心跳 / 列表（按 region 过滤）/ 详情 / 删除
  - 代理分配 GET /api/v1/proxies/acquire（健康节点随机选择）
  - 使用结果上报 POST /api/v1/proxies/report（success / latency 统计）
  - 健康检查与故障摘除/恢复闭环（Redis 实时状态 + 心跳）
- **多协议支持**：每节点同时提供 HTTP(3128) + SOCKS5(1080)，3proxy 用户名密码强认证
- **业务监控指标**：11 个 Prometheus 指标（池规模、按区域健康数、acquire/report 计数、
  延迟直方图、注册/心跳速率、节点状态变迁、HTTP 请求量）
- **Grafana 看板**：Proxy Pool / Overview，9 个面板（池规模、区域健康、QPS、
  acquire 成功/失败、上报吞吐、延迟分位数 p50/p95/p99、注册/心跳、状态变迁）
- **Docker 编排**：docker-compose.yml 一键启动 api / redis / prometheus / grafana
- **运维脚本**：scripts/setup_pool.py 节点注册 + 端到端验证（SSH 读密码 → 注册 → 走代理验出口 IP）
- **文档**：README、管理 API 参考（docs/api.md）、部署指南（docs/deployment.md）、
  调度与健康检查策略（docs/scheduling.md）、使用说明（docs/PROXY_POOL_USAGE.md）、
  凭据模板（CREDENTIALS.example.md）

## Roadmap（后续版本规划）

> 优先级与版本号可能随实际需求调整；已定项会随开发逐步移入上方版本条目。

### v1.1.x — 调度增强 + 安全加固

- [x] **加权随机调度**：按 成功率 / 延迟 / 负载 加权随机分配 —— 已交付，见 [Unreleased]
- [ ] **健康检查增强**：TCP/HTTP 探活 + 连续失败摘除、连续成功恢复（防抖），节点状态机
- [x] **管理 API 认证**：API Key + IP 白名单（保护 register/heartbeat 等写接口）—— 已交付，见 [Unreleased]
- [ ] **节点 Agent 增强**：自动注册、心跳上报、本地 3proxy 配置管理与指标采集

### v1.2.x — 智能调度 + 区域池

- [ ] **Score Based Scheduler**：成功率(0.35) + 延迟(0.30) + 负载(0.20) + 稳定性(0.15) 综合评分
- [ ] **Sticky Proxy**：账号级固定出口 IP（Redis 粘性绑定 + TTL + 降级策略）
- [ ] **区域池 / ISP 池 / 业务专属池**：按业务场景隔离节点资源
- [ ] **节点质量评分与自动封禁**：低成功率/高延迟节点自动降权或下线

### v2.0 — 平台化

- [ ] **PostgreSQL 历史与审计**：节点生命周期、分配记录、质量趋势落库
- [ ] **多租户 / 代理套餐**：按租户配额、API Key 分级、套餐限速
- [ ] **告警体系**：Prometheus Alertmanager + 飞书/钉钉通知
- [ ] **控制台**：Web UI 管理节点、查看监控、配置调度策略

[1.0.0]: https://github.com/vermilion-bird/proxy-pool/releases/tag/v1.0.0