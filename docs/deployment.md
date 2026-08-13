# 部署指南

本文档覆盖代理池的两种部署：**控制面**（FastAPI + Redis + 监控）与 **节点侧**（3proxy）。

---

## 一、控制面部署（管理平台）

### 前置

- 一台具有公网 IP 的管控服务器（推荐独立于代理节点）
- Docker ≥ 20.10 + Docker Compose v2
- 建议 2C / 4G 以上

### 步骤

```bash
git clone https://github.com/vermilion-bird/proxy-pool.git
cd proxy-pool
docker compose up -d --build
```

### 服务清单

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| api | 本地构建 | 8082 | FastAPI 管理 + `/metrics` |
| redis | redis:7 | 6380（内网）| 实时节点状态 |
| prometheus | prom/prometheus | 9090 | 抓取 api 指标 |
| grafana | grafana/grafana | 3000 | 看板（admin/admin）|

> Grafana 数据源已通过 `grafana/provisioning/datasources` 自动指向 Prometheus。

### 验证

```bash
curl http://<MGR>:8082/health          # {"status":"ok"}
curl http://<MGR>:8082/api/v1/nodes     # {"nodes":[]}
curl http://<MGR>:9090/-/healthy        # Prometheus 存活
```

---

## 二、节点侧部署（3proxy）

### 前置

每台代理服务器：

- 公网 IP（HTTP/SOCKS5 出口）
- Docker ≥ 20.10（老版本无 compose 插件时用 `docker run` 等价启动）
- 开放端口：**TCP 3128（HTTP）/ 1080（SOCKS5）**

### 3proxy 配置

```nginx
# /opt/pp3/3proxy.cfg
nscache 65536
nserver 8.8.8.8
nserver 1.1.1.1
timeouts 1 5 30 60 180 1800 15
users 3proxy:CL:<STRONG_PASSWORD>
auth strong
allow 3proxy
proxy -n -a -p3128
socks -n -a -p1080
flush
```

### 启动（new Docker，含 compose 插件）

```bash
cd /opt/pp3
docker compose up -d
```

### 启动（老版 Docker 20.10/23.0，无 compose 插件）

```bash
docker run -d --name pp3proxy --restart unless-stopped --network host \
  -v /opt/pp3/3proxy.cfg:/etc/3proxy/3proxy.cfg:ro \
  3proxy/3proxy:latest
```

### 验证本地代理

```bash
curl -x http://3proxy:<PASSWORD>@127.0.0.1:3128 https://api.ipify.org
curl -x socks5h://3proxy:<PASSWORD>@127.0.0.1:1080 https://api.ipify.org
```

---

## 三、凭据轮换与加固

### 轮换节点密码

```bash
# 在每台节点上
PW=$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 20)
sudo sed -i "s/^users 3proxy:CL:.*/users 3proxy:CL:$PW/" /opt/pp3/3proxy.cfg
sudo docker restart pp3proxy
```

> ⚠️ `users 3proxy:CL:<PASSWORD>` 中的 **`CL:` 是明文认证标记，不可省略**，否则认证失效。

### 双重防火墙加固

**1) 云平台安全组（如 OCI VCN Security List）：**

为节点实例添加入站规则：

```
TCP 3128 / 1080  →  0.0.0.0/0  （或收紧为业务出口 IP）
```

**2) 主机 iptables 白名单：**

```bash
sudo iptables -I INPUT 1 -p tcp --dport 3128 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 1080 -j ACCEPT
sudo mkdir -p /etc/iptables
sudo iptables-save | sudo tee /etc/iptables/rules.v4 >/dev/null
echo '#!/bin/sh' | sudo tee /etc/network/if-pre-up.d/iptables >/dev/null
echo 'iptables-restore < /etc/iptables/rules.v4' | sudo tee -a /etc/network/if-pre-up.d/iptables >/dev/null
sudo chmod +x /etc/network/if-pre-up.d/iptables
```

> 若主机 default REJECT 且未放行 3128/1080，即使云平台已开放，外部仍无法访问。

---

## 四、节点注册进管理平台

### 自动脚本（推荐）

```bash
python3 scripts/setup_pool.py
```

自动完成：SSH 读取各节点密码 → 注册 → 端到端验证。

### 手动注册

```bash
curl -X POST http://<MGR>:8082/api/v1/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"node_id":"proxy-<IP>","ip":"<IP>","region":"US","protocol":"http","port":3128,"username":"3proxy","password":"<PASSWORD>"}'
```

### 端到端验证

```bash
# 1. 获取代理
curl "http://<MGR>:8082/api/v1/proxies/acquire?region=US"
# 2. 走代理出网
curl -x "http://3proxy:<PASSWORD>@<IP>:3128" https://api.ipify.org
# 3. 上报结果
curl -X POST http://<MGR>:8082/api/v1/proxies/report \
  -H "Content-Type: application/json" \
  -d '{"node_id":"proxy-<IP>","success":true,"latency":82.5}'
```

---

## 五、当前生产环境（示例）

管理平台：`158.180.87.150:8082`（FastAPI）/ `:9090`（Prometheus）/ `:3000`（Grafana）

| 节点 ID | IP | 区域 | 状态 |
|---------|-----|------|:---:|
| proxy-192.9.249.67 | 192.9.249.67 | US | ✅ |
| proxy-143.47.186.111 | 143.47.186.111 | JP | ✅ |
| proxy-158.180.87.150 | 158.180.87.150 | US | ✅ |
| proxy-140.83.82.237 | 140.83.82.237 | US | ✅ |
| proxy-130.61.144.130 | 130.61.144.130 | US | ✅ |

> 真实凭据见本地 `CREDENTIALS.md`（不入库），模板见 [CREDENTIALS.example.md](../CREDENTIALS.example.md)。