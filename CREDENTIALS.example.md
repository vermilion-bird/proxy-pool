# 代理池节点凭据模板

> ⚠️ **此文件为脱敏模板，仅用于说明格式。**
> 真实凭据保存在本地（不入 git）：`projects/proxy-pool/CREDENTIALS.md`（本机）与各节点 `/opt/pp3/3proxy.cfg`。
> 请勿将真实密码提交到 GitHub。

## 节点清单格式

| 节点ID | IP | 端口 | 用户名 | 密码 | 区域 |
|--------|-----|------|--------|------|------|
| proxy-<IP> | <IP> | 3128 | 3proxy | `<STRONG_PASSWORD>` | US |
| proxy-<IP> | <IP> | 3128 | 3proxy | `<STRONG_PASSWORD>` | JP |

## 使用示例

```bash
# HTTP 代理
curl -x http://3proxy:<PASSWORD>@<IP>:3128 https://api.ipify.org

# SOCKS5 代理
curl -x socks5h://3proxy:<PASSWORD>@<IP>:1080 https://api.ipify.org
```

## 生成强密码

```bash
openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 20
```

## 节点 3proxy 认证配置（真实密码在节点本地）

```nginx
users 3proxy:CL:<STRONG_PASSWORD>
auth strong
allow 3proxy
```

> ⚠️ 保持 `CL:` 前缀（明文认证标记），否则认证失效。

## 凭据存储规范

| 位置 | 内容 | 是否入库 |
|------|------|:---:|
| `CREDENTIALS.md`（本地）| 真实密码 | ❌（.gitignore）|
| `nodes.json`（本地）| 真实密码 + API 地址 | ❌（.gitignore）|
| `CREDENTIALS.example.md` | 脱敏模板 | ✅ |
| `nodes.example.json` | 脱敏模板 | ✅ |