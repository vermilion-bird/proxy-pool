#!/usr/bin/env python3
"""
代理池节点注册 + 端到端验证脚本（通用模板，可复用）。

功能：
  1. 从每台节点 SSH 读取 3proxy 密码
  2. 注册到代理池管理平台
  3. 端到端验证（acquire → 走代理 → 出口 IP）

用法：
  通过环境变量配置（含凭据，勿入库）：
    PP_SSH_KEY=/path/to/id_rsa
    PP_MGR_API=http://<MANAGER_IP>:8082
    PP_NODES="IP1:US:ID1 IP2:JP:ID2 ..."   # 空格分隔的 节点=IP:区域:节点ID
  python3 scripts/setup_pool.py
"""
import subprocess, json, os, sys, urllib.request, urllib.error

# ─────────────── 配置（从环境变量读取）───────────────
SSH_KEY = os.environ.get('PP_SSH_KEY', '~/.ssh/id_rsa')
API     = os.environ.get('PP_MGR_API', '').rstrip('/')
NODES   = os.environ.get('PP_NODES', '').strip()

# 每项格式: IP:REGION:NODE_ID ，空格分隔
SSH_USER = os.environ.get('PP_SSH_USER', 'ubuntu')
CFG_PATH = os.environ.get('PP_CFG_PATH', '/opt/pp3/3proxy.cfg')
CFG_LINE = os.environ.get('PP_CFG_LINE', '^users 3proxy:CL:')


def parse_nodes():
    if not NODES:
        sys.exit('缺少 PP_NODES，格式: IP:REGION:NODE_ID (空格分隔)')
    out = []
    for item in NODES.split():
        parts = item.split(':')
        if len(parts) == 3:
            ip, region, nid = parts
        elif len(parts) == 2:
            ip, region = parts
            nid = f'proxy-{ip}'
        else:
            sys.exit(f'无法解析节点项: {item!r}')
        out.append({'node_id': nid, 'ip': ip, 'region': region})
    return out


def ssh_read(ip, pattern):
    r = subprocess.run(
        ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
         '-i', SSH_KEY, f'{SSH_USER}@{ip}',
         f"sudo grep '{pattern}' {CFG_PATH}"],
        capture_output=True, text=True, timeout=20)
    line = r.stdout.strip()
    parts = line.split(':')
    return parts[-1].strip() if len(parts) >= 3 else ''


def api_post(path, payload):
    req = urllib.request.Request(
        f'{API}{path}', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def test_proxy(host, port, user, pw):
    proxy_url = f'http://{user}:{pw}@{host}:{port}'
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}))
    try:
        r = opener.open('http://api.ipify.org', timeout=12)
        return True, r.read().decode().strip()
    except Exception as e:
        return False, str(e)


def main():
    if not API:
        sys.exit('缺少 PP_MGR_API')
    nodes = parse_nodes()
    print('=' * 55)
    print('STEP 1  读取各节点密码')
    print('=' * 55)
    for n in nodes:
        n['password'] = ssh_read(n['ip'], CFG_LINE)
        n['port'] = 3128
        n['protocol'] = 'http'
        n['username'] = '3proxy'
        print(f"  {'✅' if n['password'] else '❌'}  {n['ip']:20s}  pw={'*' * len(n['password']) if n['password'] else '!!'}")

    print()
    print('=' * 55)
    print('STEP 2  注册到代理池管理平台')
    print('=' * 55)
    for n in nodes:
        body = api_post('/api/v1/nodes/register', n)
        print(f"  ✅  {n['node_id']}  →  {body}")

    print()
    print('=' * 55)
    print('STEP 3  端到端验证')
    print('=' * 55)
    ok = 0
    for n in nodes:
        good, res = test_proxy(n['ip'], n['port'], n['username'], n['password'])
        print(f"  {'✅' if good else '❌'}  {n['node_id']:30s}  {'出口IP=' + res if good else 'ERROR: ' + res}")
        ok += good
        if good:
            api_post('/api/v1/proxies/report',
                     {'node_id': n['node_id'], 'success': True, 'latency': 0})

    print()
    print(f'完成  {ok}/{len(nodes)} 节点验证通过')


if __name__ == '__main__':
    main()