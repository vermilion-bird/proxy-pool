"""代理池客户端完整使用示例。

运行::

    python examples/usage.py [region]

没有参数时默认 US 区域。
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

from proxypool_client import NoProxyAvailable, ProxyPool


def main() -> None:
    region = sys.argv[1] if len(sys.argv) > 1 else "US"
    pool = ProxyPool(region=region)
    print(f"== 代理池客户端示例 (region={region}) ==")

    # 1) 拿一个代理
    try:
        proxy = pool.acquire(region=region)
    except NoProxyAvailable as e:
        print(f"[!] 无可用代理: {e}")
        return
    print(f"1) 获取代理: {proxy['host']}:{proxy['port']} ({proxy['protocol']})")

    # 2) 列出节点
    nodes = pool.list_nodes(region=region)
    print(f"2) 健康节点数: {len(nodes)}")

    # 3) 单次请求 (自动 acquire + report + 故障切换)
    try:
        resp = pool.request_via_proxy("https://api.ipify.org?format=json",
                                      region=region, timeout=25)
        print(f"3) 单次请求出口 IP: {resp.json().get('ip')}")
    except Exception as e:  # noqa: BLE001
        print(f"3) 单次请求失败: {type(e).__name__}: {e}")

    # 4) 会话级 (单节点复用)
    try:
        with pool.session(region=region) as s:
            ip = s.requests_get("https://api.ipify.org?format=json", timeout=25)
            headers = s.requests_get("https://httpbin.org/headers", timeout=25)
            print(f"4) 会话出口 IP: {ip.json().get('ip')}")
            print(f"   会话 headers 状态: {headers.status_code}")
    except Exception as e:  # noqa: BLE001
        print(f"4) 会话失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()