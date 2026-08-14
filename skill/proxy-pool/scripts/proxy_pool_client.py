#!/usr/bin/env python3
"""Proxy Pool 代理池 Python 客户端。

用法：
  python proxy_pool_client.py acquire [--region US] [--pool ads] [--isp OCI] [--account-id acct-1] [--json]
  python proxy_pool_client.py test --node-id proxy-130.61.144.130 [--timeout 15]
  python proxy_pool_client.py nodes [--region US] [--pool ads] [--isp OCI]
  python proxy_pool_client.py node --node-id proxy-xxx
  python proxy_pool_client.py report --node-id proxy-xxx [--success true] [--latency 82.5]
  python proxy_pool_client.py release --account-id acct-1
  python proxy_pool_client.py unban --node-id proxy-xxx
  python proxy_pool_client.py audit --events|--acquires|--reports [--node-id proxy-xxx] [--limit 20]
  python proxy_pool_client.py health

环境变量：
  PP_MGR_API   管理 API 地址（默认 http://158.180.87.150:8082）
  PP_API_KEY   管理 API 认证 Key（可选，若已启用认证则必填）
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

API = os.environ.get("PP_MGR_API", "https://proxy.8tb.cc").rstrip("/")
API_KEY = os.environ.get("PP_API_KEY", "")


def _headers():
    h = {
        "Content-Type": "application/json",
        "User-Agent": "proxy-pool-client/1.0 (+https://github.com/vermilion-bird/proxy-pool)",
    }
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _request(method, path, params=None, body=None, timeout=15):
    url = API + path
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v is not None)
        url += ("?" if "?" not in url else "&") + qs
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    # 兼容无系统根证书环境（如 macOS 原生 Python）
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}


def cmd_acquire(args):
    status, data = _request("GET", "/api/v1/proxies/acquire", params={
        "region": args.region, "pool": args.pool, "isp": args.isp, "account_id": args.account_id,
    })
    if status != 200:
        print(f"acquire 失败 [{status}]: {data.get('error','')}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        proxy_url = f"{data['protocol']}://{data['username']}:{data['password']}@{data['host']}:{data['port']}"
        print(f"proxy_id : {data['proxy_id']}")
        print(f"URL      : {proxy_url}  (sticky={data.get('sticky', False)})")
        print(f"region   : {data.get('region')}  pool={data.get('pool')}  isp={data.get('isp')}")
    return data


def cmd_test(args):
    """获取指定节点信息并走代理验证出口 IP。"""
    status, node = _request("GET", f"/api/v1/nodes/{args.node_id}")
    if status != 200:
        print(f"节点不存在 [{status}]", file=sys.stderr)
        sys.exit(1)
    print(f"节点状态: {node.get('status')}  region={node.get('region')}")
    proxy_url = f"http://{node['username']}:{node['password']}@{node['ip']}:{node['port']}"
    # 兼容无系统根证书环境（如 macOS 原生 Python）
    ctx = ssl._create_unverified_context()
    handlers = [urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})]
    try:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    except TypeError:
        pass
    opener = urllib.request.build_opener(*handlers)
    last = None
    for target in ("https://api.ipify.org", "http://api.ipify.org", "http://httpbin.org/ip"):
        try:
            resp = opener.open(target, timeout=args.timeout)
            egress = resp.read().decode().strip()
            ok = egress == node["ip"]
            print(f"代理出口: {egress}  {'✅ 与节点 IP 一致' if ok else '⚠️ 不一致!'}")
            return 0 if ok else 1
        except Exception as e:
            last = e
    print(f"代理测试失败: {last}", file=sys.stderr)
    return 1


def cmd_nodes(args):
    status, data = _request("GET", "/api/v1/nodes", params={"region": args.region, "pool": args.pool, "isp": args.isp})
    nodes = data.get("nodes", [])
    print(f"健康节点数: {len(nodes)}")
    for nid in nodes:
        print(f"  {nid}")
    return nodes


def cmd_node(args):
    status, node = _request("GET", f"/api/v1/nodes/{args.node_id}")
    if status != 200:
        print(f"节点不存在 [{status}]", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(node, ensure_ascii=False, indent=2))
    return node


def cmd_report(args):
    status, data = _request("POST", "/api/v1/proxies/report", body={
        "node_id": args.node_id, "success": args.success, "latency": args.latency,
    })
    print(f"上报结果: {status} {data}")


def cmd_release(args):
    status, data = _request("POST", "/api/v1/proxies/release", body={"account_id": args.account_id})
    print(f"释放粘性绑定: {status} {data}")


def cmd_unban(args):
    status, data = _request("POST", f"/api/v1/nodes/{args.node_id}/unban")
    print(f"解封: {status} {data}")


def cmd_audit(args):
    if args.events:
        path = "/api/v1/audit/events"
    elif args.acquires:
        path = "/api/v1/audit/acquires"
    else:
        path = "/api/v1/audit/reports"
    status, data = _request("GET", path, params={"node_id": args.node_id, "limit": args.limit})
    rows = next(iter(data.values()), [])
    print(f"审计记录数: {len(rows)}")
    for row in rows[: args.limit]:
        print(f"  {row}")
    return rows


def cmd_health(args):
    status, data = _request("GET", "/health")
    print(f"health: {status} {data}")


def main():
    p = argparse.ArgumentParser(description="Proxy Pool 客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("acquire", help="获取一个代理")
    a.add_argument("--region"); a.add_argument("--pool"); a.add_argument("--isp"); a.add_argument("--account-id")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_acquire)

    t = sub.add_parser("test", help="测试代理节点连通性")
    t.add_argument("--node-id", required=True); t.add_argument("--timeout", type=int, default=15)
    t.set_defaults(func=cmd_test)

    n = sub.add_parser("nodes", help="列出健康节点")
    n.add_argument("--region"); n.add_argument("--pool"); n.add_argument("--isp")
    n.set_defaults(func=cmd_nodes)

    nd = sub.add_parser("node", help="节点详情")
    nd.add_argument("--node-id", required=True)
    nd.set_defaults(func=cmd_node)

    r = sub.add_parser("report", help="上报使用结果")
    r.add_argument("--node-id", required=True); r.add_argument("--success", type=lambda s: s.lower() == "true", default=True)
    r.add_argument("--latency", type=float, default=0.0)
    r.set_defaults(func=cmd_report)

    rel = sub.add_parser("release", help="释放粘性绑定")
    rel.add_argument("--account-id", required=True)
    rel.set_defaults(func=cmd_release)

    ub = sub.add_parser("unban", help="解封节点")
    ub.add_argument("--node-id", required=True)
    ub.set_defaults(func=cmd_unban)

    au = sub.add_parser("audit", help="查询审计历史")
    au.add_argument("--events", action="store_true"); au.add_argument("--acquires", action="store_true")
    au.add_argument("--node-id"); au.add_argument("--limit", type=int, default=20)
    au.set_defaults(func=cmd_audit)

    h = sub.add_parser("health", help="健康检查")
    h.set_defaults(func=cmd_health)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402

    main()
