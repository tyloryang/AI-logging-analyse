"""Prometheus HTTP API 客户端 - 主机自动发现与指标查询"""
import asyncio
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class PrometheusClient:
    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = httpx.Timeout(15.0)
        # 复用长连接，避免每次查询新建 TCP 连接
        kw: dict = {"timeout": self.timeout, "limits": httpx.Limits(max_connections=20)}
        if self.auth:
            kw["auth"] = self.auth
        self._client = httpx.AsyncClient(**kw)
        logger.info("[Prometheus] url=%s, auth=%s", self.base_url, "yes" if self.auth else "no")

    async def query(self, promql: str, timeout: float | None = None) -> list[dict]:
        """执行即时查询"""
        url = f"{self.base_url}/api/v1/query"
        logger.debug("[Prometheus] GET %s?query=%s", url, promql[:60])
        kw = {"params": {"query": promql}}
        if timeout:
            kw["timeout"] = httpx.Timeout(timeout)
        resp = await self._client.get(url, **kw)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {data}")
        return data.get("data", {}).get("result", [])

    async def get_targets(self) -> list[dict]:
        """获取所有 Prometheus targets"""
        resp = await self._client.get(f"{self.base_url}/api/v1/targets")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("activeTargets", [])

    # ────────── 主机自动发现 ──────────

    async def discover_hosts(self) -> list[dict]:
        """
        通过 Prometheus targets + node_exporter 指标自动发现主机。
        返回 [{instance, ip, job, state, hostname, os, arch, cpu_cores}, ...]
        """
        targets = await self.get_targets()

        # 去重，提取 instance；优先用 discoveredLabels.__address__ 获取真实 IP
        # （无论 K8s 还是 VM，__address__ 始终是 Prometheus 实际抓取的 IP:port）
        # 保留的系统标签，不计入自定义标签
        _SYSTEM_LABELS = {"instance", "job", "__name__"}

        hosts_map: dict[str, dict] = {}
        for t in targets:
            labels = t.get("labels", {})
            instance = labels.get("instance", "")
            if not instance or instance in hosts_map:
                continue

            # 真实 IP 优先级：discoveredLabels.__address__ > scrapeUrl > instance
            real_addr = t.get("discoveredLabels", {}).get("__address__", "")
            if real_addr:
                ip = real_addr.split(":")[0]
            else:
                ip = instance.split(":")[0]

            # 提取自定义标签：排除系统标签和以 __ 开头的内部标签
            custom_labels = {
                k: v for k, v in labels.items()
                if k not in _SYSTEM_LABELS and not k.startswith("__")
            }

            hosts_map[instance] = {
                "instance": instance,
                "ip": ip,
                "job": labels.get("job", ""),
                "state": t.get("health", "unknown"),
                "custom_labels": custom_labels,
            }

        # 并行查询主机元数据 + CPU 核数
        uname_results, cpu_results = await asyncio.gather(
            self._safe_query("node_uname_info"),
            self._safe_query('count by(instance) (node_cpu_seconds_total{mode="idle"})'),
        )

        for r in uname_results:
            m = r.get("metric", {})
            inst = m.get("instance", "")
            if inst in hosts_map:
                hosts_map[inst]["hostname"] = m.get("nodename", "")
                hosts_map[inst]["os"] = f"{m.get('sysname', '')} {m.get('release', '')}"
                hosts_map[inst]["arch"] = m.get("machine", "")
        for r in cpu_results:
            inst = r.get("metric", {}).get("instance", "")
            if inst in hosts_map:
                hosts_map[inst]["cpu_cores"] = int(float(r["value"][1]))

        return list(hosts_map.values())

    # ────────── 批量指标采集 ──────────

    async def get_all_host_metrics(self) -> dict[str, dict]:
        """
        一次性查询所有主机的关键指标，返回 {instance: {cpu_usage, mem_usage, ...}, ...}。
        使用批量 PromQL 而非逐台查询，高效。
        """
        queries = {
            "cpu_usage": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
            "mem_total": "node_memory_MemTotal_bytes",
            "mem_avail": "node_memory_MemAvailable_bytes",
            "load1": "node_load1",
            "load5": "node_load5",
            "load15": "node_load15",
            "boot_time": "node_boot_time_seconds",
            # 网络带宽（所有物理网卡，排除 lo/veth/docker/br）
            "net_recv": 'sum by(instance) (rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br.*|cni.*|flannel.*|cali.*"}[5m]))',
            "net_send": 'sum by(instance) (rate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|br.*|cni.*|flannel.*|cali.*"}[5m]))',
            # 磁盘 I/O 速率
            "disk_read": 'sum by(instance) (rate(node_disk_read_bytes_total[5m]))',
            "disk_write": 'sum by(instance) (rate(node_disk_written_bytes_total[5m]))',
            # TCP 连接
            "tcp_estab": "node_netstat_Tcp_CurrEstab",
            "tcp_tw": "node_sockstat_TCP_tw",
        }

        # 并行查询所有指标
        keys = list(queries.keys())
        results = await asyncio.gather(*(self._safe_query(queries[k]) for k in keys))
        raw: dict[str, list[dict]] = dict(zip(keys, results))

        # 按 instance 聚合
        metrics: dict[str, dict] = {}
        for key, results in raw.items():
            for r in results:
                inst = r.get("metric", {}).get("instance", "")
                if not inst:
                    continue
                if inst not in metrics:
                    metrics[inst] = {}
                metrics[inst][key] = float(r["value"][1])

        now = time.time()
        for inst, m in metrics.items():
            # 内存使用率
            if "mem_total" in m and "mem_avail" in m and m["mem_total"] > 0:
                m["mem_usage"] = round((1 - m["mem_avail"] / m["mem_total"]) * 100, 1)
                m["mem_total_gb"] = round(m["mem_total"] / (1024 ** 3), 1)
            if "cpu_usage" in m:
                m["cpu_usage"] = round(m["cpu_usage"], 1)
            if "boot_time" in m:
                m["uptime_seconds"] = int(now - m["boot_time"])
            # 网络带宽 → MB/s
            if "net_recv" in m:
                m["net_recv_mbps"] = round(m["net_recv"] / (1024 * 1024), 2)
            if "net_send" in m:
                m["net_send_mbps"] = round(m["net_send"] / (1024 * 1024), 2)
            # 磁盘 I/O → MB/s
            if "disk_read" in m:
                m["disk_read_mbps"] = round(m["disk_read"] / (1024 * 1024), 2)
            if "disk_write" in m:
                m["disk_write_mbps"] = round(m["disk_write"] / (1024 * 1024), 2)
            # TCP
            if "tcp_estab" in m:
                m["tcp_estab"] = int(m["tcp_estab"])
            if "tcp_tw" in m:
                m["tcp_tw"] = int(m["tcp_tw"])
            # 清理原始字段
            for k in ("mem_total", "mem_avail", "boot_time", "net_recv", "net_send", "disk_read", "disk_write"):
                m.pop(k, None)

        return metrics

    # ────────── 分区使用率 ──────────

    async def get_all_partitions(self) -> dict[str, list[dict]]:
        """
        查询所有主机的每个分区使用率。
        返回 {instance: [{mountpoint, fstype, total_gb, avail_gb, usage_pct}, ...]}
        排除 tmpfs、overlay 等虚拟文件系统。
        """
        fs_filter = 'fstype!~"tmpfs|overlay|squashfs|iso9660|devtmpfs|nsfs|shm"'
        total_results, avail_results = await asyncio.gather(
            self._safe_query(f'node_filesystem_size_bytes{{{fs_filter}}}'),
            self._safe_query(f'node_filesystem_avail_bytes{{{fs_filter}}}'),
        )

        # 按 instance+mountpoint 聚合
        totals: dict[str, dict[str, float]] = {}
        fstypes: dict[str, dict[str, str]] = {}
        for r in total_results:
            m = r.get("metric", {})
            inst = m.get("instance", "")
            mp = m.get("mountpoint", "")
            if not inst or not mp:
                continue
            totals.setdefault(inst, {})[mp] = float(r["value"][1])
            fstypes.setdefault(inst, {})[mp] = m.get("fstype", "")

        avails: dict[str, dict[str, float]] = {}
        for r in avail_results:
            m = r.get("metric", {})
            inst = m.get("instance", "")
            mp = m.get("mountpoint", "")
            if not inst or not mp:
                continue
            avails.setdefault(inst, {})[mp] = float(r["value"][1])

        result: dict[str, list[dict]] = {}
        for inst, mounts in totals.items():
            parts = []
            for mp, total in sorted(mounts.items()):
                if total <= 0:
                    continue
                avail = avails.get(inst, {}).get(mp, 0)
                total_gb = round(total / (1024 ** 3), 1)
                avail_gb = round(avail / (1024 ** 3), 1)
                used_gb = round((total - avail) / (1024 ** 3), 1)
                usage_pct = round((1 - avail / total) * 100, 1)
                parts.append({
                    "mountpoint": mp,
                    "fstype": fstypes.get(inst, {}).get(mp, ""),
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "avail_gb": avail_gb,
                    "usage_pct": usage_pct,
                })
            if parts:
                # / 排最前面
                parts.sort(key=lambda p: (0 if p["mountpoint"] == "/" else 1, p["mountpoint"]))
                result[inst] = parts
        return result

    # ────────── 巡检 ──────────

    async def inspect_hosts(self, instances: Optional[list[str]] = None) -> list[dict]:
        """
        巡检指定主机（默认全部），返回每台的检查项和整体状态。
        """
        hosts, all_metrics, all_partitions = await asyncio.gather(
            self.discover_hosts(),
            self.get_all_host_metrics(),
            self.get_all_partitions(),
        )

        if instances:
            hosts = [h for h in hosts if h["instance"] in instances]

        results = []
        for host in hosts:
            inst = host["instance"]
            m = all_metrics.get(inst, {})
            partitions = all_partitions.get(inst, [])
            checks = self._build_checks(m, host.get("cpu_cores", 4), partitions)

            worst = max((self._severity(c["status"]) for c in checks), default=0)
            overall = "critical" if worst >= 2 else "warning" if worst == 1 else "normal"

            results.append({
                "instance": inst,
                "ip": host.get("ip", ""),
                "hostname": host.get("hostname", inst),
                "os": host.get("os", ""),
                "job": host.get("job", ""),
                "state": host.get("state", "unknown"),
                "overall": overall,
                "checks": checks,
                "metrics": m,
                "partitions": partitions,
            })

        # 严重的排前面
        results.sort(key=lambda x: -self._severity(x["overall"]))
        return results

    # ────────── 内部方法 ──────────

    @staticmethod
    def _severity(status: str) -> int:
        return {"critical": 2, "warning": 1, "normal": 0}.get(status, 0)

    @staticmethod
    def _build_checks(m: dict, cpu_cores: int = 4, partitions: list[dict] | None = None) -> list[dict]:
        checks = []

        cpu = m.get("cpu_usage")
        if cpu is not None:
            checks.append({
                "item": "CPU 使用率",
                "value": f"{cpu}%",
                "status": "critical" if cpu > 90 else "warning" if cpu > 70 else "normal",
                "threshold": "≤70% / ≤90% / >90%",
            })

        mem = m.get("mem_usage")
        if mem is not None:
            checks.append({
                "item": "内存使用率",
                "value": f"{mem}%",
                "status": "critical" if mem > 90 else "warning" if mem > 80 else "normal",
                "threshold": "≤80% / ≤90% / >90%",
            })

        # 每个分区的使用率检查
        if partitions:
            for p in partitions:
                usage = p["usage_pct"]
                checks.append({
                    "item": f"磁盘 {p['mountpoint']}",
                    "value": f"{usage}% ({p['used_gb']}/{p['total_gb']}GB)",
                    "status": "critical" if usage > 90 else "warning" if usage > 80 else "normal",
                    "threshold": "≤80% / ≤90% / >90%",
                })

        load5 = m.get("load5")
        if load5 is not None:
            high = cpu_cores * 2
            warn = cpu_cores
            checks.append({
                "item": "5分钟负载",
                "value": f"{round(load5, 2)}",
                "status": "critical" if load5 > high else "warning" if load5 > warn else "normal",
                "threshold": f"≤{warn} / ≤{high} / >{high}（{cpu_cores}核）",
            })

        # 磁盘 I/O
        dr = m.get("disk_read_mbps")
        dw = m.get("disk_write_mbps")
        if dr is not None and dw is not None:
            checks.append({
                "item": "磁盘 I/O",
                "value": f"R:{dr} / W:{dw} MB/s",
                "status": "warning" if (dr > 100 or dw > 100) else "normal",
                "threshold": "≤100 MB/s",
            })

        # 网络带宽
        nr = m.get("net_recv_mbps")
        ns = m.get("net_send_mbps")
        if nr is not None and ns is not None:
            checks.append({
                "item": "网络带宽",
                "value": f"↓{nr} / ↑{ns} MB/s",
                "status": "warning" if (nr > 100 or ns > 100) else "normal",
                "threshold": "≤100 MB/s",
            })

        # TCP 连接
        tcp_e = m.get("tcp_estab")
        if tcp_e is not None:
            checks.append({
                "item": "TCP 连接数",
                "value": str(tcp_e),
                "status": "warning" if tcp_e > 5000 else "normal",
                "threshold": "≤5000",
            })
        tcp_tw = m.get("tcp_tw")
        if tcp_tw is not None:
            checks.append({
                "item": "TCP TIME_WAIT",
                "value": str(tcp_tw),
                "status": "warning" if tcp_tw > 10000 else "normal",
                "threshold": "≤10000",
            })

        uptime = m.get("uptime_seconds")
        if uptime is not None:
            days, rem = divmod(uptime, 86400)
            hours = rem // 3600
            checks.append({
                "item": "运行时长",
                "value": f"{days}天{hours}小时",
                "status": "warning" if uptime < 3600 else "normal",
                "threshold": "≥1小时正常",
            })

        return checks

    async def _safe_query(self, promql: str) -> list[dict]:
        try:
            return await self.query(promql)
        except Exception as e:
            logger.warning("Prometheus query failed [%s]: %s", promql[:60], e)
            return []
