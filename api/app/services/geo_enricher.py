"""IP 地理信息增强服务（基于 ipwho.is 免费 API）。

用法：
  - 节点注册时自动调用 enrich_node，覆盖 region/isp
  - 可通过 /api/v1/nodes/{node_id}/enrich 手动刷新
  - /api/v1/nodes/enrich-all 批量刷新全部节点
"""

import logging
import urllib.request
import json

logger = logging.getLogger("proxy-pool")

API_URL = "https://ipwho.is/{ip}"


def _fetch(ip: str, timeout: float = 5.0) -> dict | None:
    """查询 ipwho.is，返回地理信息 dict 或 None。"""
    try:
        req = urllib.request.Request(
            API_URL.format(ip=ip),
            headers={"User-Agent": "proxy-pool/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("ipwho.is query failed for %s: %s", ip, exc)
        return None

    if not data.get("success"):
        logger.warning("ipwho.is returned failure for %s: %s", ip, data.get("message", "unknown"))
        return None

    conn = data.get("connection", {})
    flag = data.get("flag", {})
    tz = data.get("timezone", {})

    return {
        # 覆盖核心字段
        "region": data.get("country_code", ""),
        "isp": conn.get("isp", ""),
        # 地理扩展字段
        "geo_country": data.get("country", ""),
        "geo_country_code": data.get("country_code", ""),
        "geo_region": data.get("region", ""),
        "geo_city": data.get("city", ""),
        "geo_latitude": str(data.get("latitude", "")),
        "geo_longitude": str(data.get("longitude", "")),
        "geo_continent": data.get("continent", ""),
        "geo_flag_emoji": flag.get("emoji", ""),
        "geo_isp": conn.get("isp", ""),
        "geo_org": conn.get("org", ""),
        "geo_asn": str(conn.get("asn", "")),
        "geo_domain": conn.get("domain", ""),
        "geo_timezone": tz.get("id", ""),
        "geo_enriched": "1",
    }


def enrich_node(node: dict) -> dict:
    """用 ipwho.is 增强节点信息，覆盖 region 和 isp。"""
    ip = node.get("ip", "")
    if not ip:
        return node
    geo = _fetch(ip)
    if not geo:
        return node
    # 全部覆盖（包括 region、isp 等核心字段）
    node.update(geo)
    return node

