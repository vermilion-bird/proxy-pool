# Proxy Pool Skill

代理池（Proxy Pool）的获取与使用 Skill，可发布到 [ClawHub](https://clawhub.com)。

## 目录

```text
skill/proxy-pool/
├── SKILL.md                      # Skill 说明（frontmatter + 使用文档）
└── scripts/
    └── proxy_pool_client.py      # Python 客户端（获取/测试代理）
```

## 安装

```bash
clawhub install proxy-pool
```

## 使用

详见 [SKILL.md](proxy-pool/SKILL.md)，核心用法：

```bash
# 获取一个代理
curl "https://proxy.8tb.cc/api/v1/proxies/acquire"

# 用代理发请求（HTTP）
curl -x "http://3proxy:<PASSWORD>@<HOST>:3128" https://api.ipify.org

# Python 客户端
python scripts/proxy_pool_client.py acquire --region US
```

## 环境变量

```env
PP_MGR_API=https://proxy.8tb.cc
PP_API_KEY=<API Key，若已启用认证>
```
