import os
import random

from ..core import redis as redis_module


class NodeNotFoundError(Exception):
    pass


class NoHealthyNodeError(Exception):
    pass


class NodeRepository:
    """节点仓库：注册/心跳/智能调度/上报。

    调度模式（PP_SCHED_MODE，默认 weighted）：
      weighted  加权随机（按分数概率选择）
      best      智能调度：选得分最高的节点（确定性）

    调度权重（可经环境变量覆盖）：
      PP_SCHED_W_SUCCESS     成功率权重（默认 0.35）
      PP_SCHED_W_LATENCY     延迟权重（默认 0.30）
      PP_SCHED_W_LOAD        负载权重（默认 0.20）
      PP_SCHED_W_STABILITY   稳定性权重（默认 0.15）
    """

    def __init__(
        self,
        r=None,
        node_key_prefix="pp:node",
        pool_key="pp:pool",
        w_success=None,
        w_latency=None,
        w_load=None,
        w_stability=None,
        sched_mode=None,
        latency_threshold_ms=1000.0,
        load_threshold=10.0,
        stability_threshold=10.0,
    ):
        self.r = r or redis_module.get_client()
        self.nkp = node_key_prefix
        self.pk = pool_key
        self.w_success = (
            float(os.getenv("PP_SCHED_W_SUCCESS", "0.35"))
            if w_success is None else float(w_success)
        )
        self.w_latency = (
            float(os.getenv("PP_SCHED_W_LATENCY", "0.30"))
            if w_latency is None else float(w_latency)
        )
        self.w_load = (
            float(os.getenv("PP_SCHED_W_LOAD", "0.20"))
            if w_load is None else float(w_load)
        )
        self.w_stability = (
            float(os.getenv("PP_SCHED_W_STABILITY", "0.15"))
            if w_stability is None else float(w_stability)
        )
        self.sched_mode = (
            os.getenv("PP_SCHED_MODE", "weighted")
            if sched_mode is None else sched_mode
        ).lower()
        if self.sched_mode not in ("weighted", "best"):
            self.sched_mode = "weighted"
        self.latency_threshold_ms = latency_threshold_ms
        self.load_threshold = load_threshold
        self.stability_threshold = stability_threshold

    def _key(self, node_id):
        return f"{self.nkp}:{node_id}"

    def _is_healthy(self, node_id):
        return self.r.hget(self._key(node_id), "status") == "healthy"

    def register(self, node_data: dict) -> dict:
        nid = node_data.get("node_id") or node_data.get("id")
        if not nid:
            raise ValueError("node_id required")
        k = self._key(nid)
        self.r.hset(k, mapping={
            "node_id": nid,
            "ip": str(node_data.get("ip", "")),
            "port": str(node_data.get("port", 3128)),
            "region": str(node_data.get("region", "US")),
            "pool": str(node_data.get("pool", "default")),
            "isp": str(node_data.get("isp", "")),
            "protocol": str(node_data.get("protocol", "http")),
            "username": str(node_data.get("username", "")),
            "password": str(node_data.get("password", "")),
            "status": "healthy",
            "success_count": "0",
            "fail_count": "0",
            "latency": str(node_data.get("latency", 0)),
            "current_connections": str(node_data.get("current_connections", 0)),
        })
        self.r.sadd(self.pk, nid)
        return self.get(nid)

    def heartbeat(self, node_id, status="healthy"):
        self.r.hset(self._key(node_id), mapping={
            "status": status,
        })

    def update_meta(self, node_id, data: dict, overwrite_core: bool = False):
        """Update node metadata (e.g. geo enrichment) without overwriting core fields."""
        core = set() if overwrite_core else {"node_id","ip","port","region","pool","isp","protocol","username","password","status"}
        mapping = {k: str(v) for k,v in data.items() if k not in core and v}
        if mapping:
            self.r.hset(self._key(node_id), mapping=mapping)
        return self.get(node_id)



    def healthy_nodes(self, region=None, pool=None, isp=None):
        """健康节点列表，支持 region / pool（业务专属池）/ isp 多维过滤。"""
        ids = self.r.smembers(self.pk)
        out = [nid for nid in ids if self._is_healthy(nid)]
        for nid in list(out):
            d = self.r.hgetall(self._key(nid))
            if region and d.get("region") != region:
                out.remove(nid)
            elif pool and d.get("pool") != pool:
                out.remove(nid)
            elif isp and d.get("isp") != isp:
                out.remove(nid)
        return out

    def _score(self, node: dict) -> float:
        """计算节点调度得分（0~1）：成功率 + 延迟 + 负载 + 稳定性 加权。

        stability_score 基于健康检查连续成功次数（consecutive_successes），
        连续成功越多代表在线越稳定；无健康历史的新节点视为满分（给予机会）。
        """
        success = int(node.get("success_count") or 0)
        fail = int(node.get("fail_count") or 0)
        total = success + fail
        success_rate = (success / total) if total else 1.0  # 无统计数据视为满分

        latency = float(node.get("latency") or 0)
        latency_score = max(0.0, 1.0 - latency / self.latency_threshold_ms)

        connections = int(node.get("current_connections") or 0)
        load_score = max(0.0, 1.0 - connections / self.load_threshold)

        if "consecutive_successes" in node:
            successes = int(node.get("consecutive_successes") or 0)
            stability_score = min(1.0, successes / self.stability_threshold)
        else:
            stability_score = 1.0  # 无健康历史的新节点视为稳定

        return (
            self.w_success * success_rate
            + self.w_latency * latency_score
            + self.w_load * load_score
            + self.w_stability * stability_score
        )

    def acquire(self, region=None, pool=None, isp=None, mode=None):
        """按调度模式从匹配多维过滤条件的健康节点中选择一个。

        region / pool（业务专属池）/ isp 任一维度都可过滤。
        mode（覆盖 PP_SCHED_MODE）：
          best      智能调度：确定性选择得分最高的节点
          weighted  加权随机：得分越高概率越大；分数一致或全 0 时
                    退化为均匀随机（兼容无统计数据的新节点）
        """
        candidates = self.healthy_nodes(region, pool=pool, isp=isp)
        if not candidates:
            raise NoHealthyNodeError("no healthy nodes")
        nodes = [self.get(nid) for nid in candidates]
        if len(nodes) == 1:
            return nodes[0]

        mode = (mode or self.sched_mode).lower()
        if mode == "best":
            return max(nodes, key=lambda n: self._score(n))

        weights = [max(0.0, self._score(n)) for n in nodes]
        if sum(weights) <= 0:
            return random.choice(nodes)
        return random.choices(nodes, weights=weights, k=1)[0]

    # ---------- Sticky Proxy ----------

    def sticky_key(self, account_id):
        return f"pp:sticky:{account_id}"

    def acquire_sticky(self, account_id, region=None, pool=None, isp=None, ttl=1800, mode=None):
        """账号级固定出口 IP：优先复用已有绑定，故障时重新分配。

        返回 (node, sticky_hit)。
        - sticky_hit=True：命中既有绑定（绑定节点健康且区域匹配）
        - sticky_hit=False：新建绑定（原绑定故障/无绑定）
        """
        sk = self.sticky_key(account_id)
        bound = self.r.get(sk)
        if bound:
            try:
                node = self.get(bound)
                if node.get("status") == "healthy" and (
                    not region or node.get("region") == region
                ) and (
                    not pool or node.get("pool") == pool
                ) and (
                    not isp or node.get("isp") == isp
                ):
                    self.r.expire(sk, ttl)  # 续期
                    return node, True
            except NodeNotFoundError:
                pass
            self.r.delete(sk)  # 绑定节点故障/区域不匹配，解除旧绑定

        node = self.acquire(region, pool=pool, isp=isp, mode=mode)
        self.r.set(sk, node["node_id"], ex=ttl)
        return node, False

    def release_sticky(self, account_id):
        """释放账号的粘性绑定。"""
        return self.r.delete(self.sticky_key(account_id))

    def get(self, node_id):
        d = self.r.hgetall(self._key(node_id))
        if not d:
            raise NodeNotFoundError(f"node {node_id} not found")
        d["node_id"] = node_id
        return d

    def all_nodes(self):
        return [self.get(nid) for nid in self.r.smembers(self.pk)]

    def report(self, node_id, success=True, latency=0.0):
        k = self._key(node_id)
        p = self.r.pipeline()
        if success:
            p.hincrby(k, "success_count", 1)
        else:
            p.hincrby(k, "fail_count", 1)
        p.hset(k, "latency", latency)
        p.execute()

    def record_check(
        self,
        node_id,
        ok: bool,
        latency_ms: float = 0.0,
        fail_degraded: int = 3,
        fail_dead: int = 5,
        recover: int = 3,
    ) -> dict:
        """记录一次健康检查结果，应用状态机与防抖。

        - 检查失败：consecutive_failures +1；达到 fail_degraded -> degraded，
          达到 fail_dead -> dead（摘除，不再参与分配）
        - 检查成功：重置失败计数，consecutive_successes +1；
          degraded/dead 节点连续成功达到 recover -> healthy（重新入池）
        - maintenance / disabled 状态不参与自动迁移
        """
        node = self.get(node_id)
        status = node.get("status", "healthy")
        if status in ("maintenance", "disabled"):
            return node

        failures = int(node.get("consecutive_failures") or 0)
        successes = int(node.get("consecutive_successes") or 0)
        new_status = status

        if ok:
            failures = 0
            successes += 1
            if status in ("degraded", "dead") and successes >= recover:
                new_status = "healthy"
        else:
            successes = 0
            failures += 1
            if failures >= fail_dead:
                new_status = "dead"
            elif failures >= fail_degraded:
                new_status = "degraded"

        mapping = {
            "status": new_status,
            "consecutive_failures": str(failures),
            "consecutive_successes": str(successes),
            "latency": str(latency_ms),
        }
        if new_status != status:
            mapping["last_state_change"] = "health_check"
            try:
                from .. import metrics

                metrics.NODE_STATE_CHANGES.labels(transition=status + "->" + new_status).inc()
            except Exception:
                pass
            try:
                from .audit_repository import AuditRepository

                AuditRepository().record_node_event(
                    node_id, "state_change", old_status=status, new_status=new_status,
                    detail="health_check",
                )
            except Exception:
                pass
        self.r.hset(self._key(node_id), mapping=mapping)
        return self.get(node_id)

    # ---------- 质量评分封禁 ----------

    def quality_score(self, node: dict) -> float:
        """节点质量评分（0~1）：基于成功率，用于自动封禁判定。"""
        success = int(node.get("success_count") or 0)
        fail = int(node.get("fail_count") or 0)
        total = success + fail
        if total == 0:
            return 1.0  # 无样本不判定
        return success / total

    def ban(self, node_id, reason="quality"):
        """封禁节点：置为 disabled（不参与分配）。"""
        import time

        k = self._key(node_id)
        self.r.hset(k, mapping={
            "status": "disabled",
            "banned_reason": reason,
            "banned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        try:
            from .. import metrics

            metrics.NODE_STATE_CHANGES.labels(transition="banned").inc()
            metrics.BANNED_TOTAL.labels(reason=reason).inc()
        except Exception:
            pass
        try:
            from .audit_repository import AuditRepository

            AuditRepository().record_node_event(node_id, "banned", old_status="healthy", new_status="disabled", detail=reason)
        except Exception:
            pass
        return self.get(node_id)

    def unban(self, node_id):
        """解封节点：恢复 healthy 并清空封禁信息与失败计数。"""
        k = self._key(node_id)
        self.r.hset(k, mapping={
            "status": "healthy",
            "banned_reason": "",
            "banned_at": "",
            "consecutive_failures": "0",
            "consecutive_successes": "0",
        })
        try:
            from .. import metrics

            metrics.NODE_STATE_CHANGES.labels(transition="unbanned").inc()
        except Exception:
            pass
        try:
            from .audit_repository import AuditRepository

            AuditRepository().record_node_event(node_id, "unbanned", old_status="disabled", new_status="healthy")
        except Exception:
            pass
        return self.get(node_id)

    def evaluate_quality(self, min_success_rate=0.5, min_requests=20):
        """扫描全部节点，低成功率节点自动封禁（防抖：需达到最小请求数）。

        返回被封禁的 node_id 列表。
        """
        banned = []
        for node in self.all_nodes():
            status = node.get("status", "healthy")
            if status in ("maintenance", "disabled"):
                continue  # 人工状态/已封禁不重复评估
            success = int(node.get("success_count") or 0)
            fail = int(node.get("fail_count") or 0)
            total = success + fail
            if total < min_requests:
                continue  # 样本不足，避免小样本误判
            if self.quality_score(node) < min_success_rate:
                self.ban(node["node_id"], reason="low_success_rate")
                banned.append(node["node_id"])
        return banned
