"""SkyWalking OAP GraphQL client

SkyWalking OAP 暴露两个端口：
  11800 → gRPC（Agent 数据上报）
  12800 → HTTP REST / GraphQL（查询接口）

SKYWALKING_OAP_URL 应指向 HTTP 查询端口（默认 12800）。
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# OAP HTTP Query URL（GraphQL），默认 12800
SKYWALKING_OAP_URL = os.getenv("SKYWALKING_OAP_URL", "http://192.168.9.226:12800")
GRAPHQL_URL = f"{SKYWALKING_OAP_URL.rstrip('/')}/graphql"


# ─────────────────────────────────────────────────────────────────────────────
# 时间格式工具
# ─────────────────────────────────────────────────────────────────────────────

def _build_duration(
    hours: int = 1,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
) -> dict:
    """构造 SkyWalking GraphQL Duration 对象，自动选择合适的 step。"""
    if start_str and end_str:
        try:
            # ISO format (UTC)
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    start_dt = datetime.strptime(start_str, fmt).replace(tzinfo=timezone.utc)
                    end_dt   = datetime.strptime(end_str,   fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"无法解析时间: {start_str}")
        except Exception:
            end_dt   = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(hours=hours)
    else:
        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(hours=hours)

    span_h = (end_dt - start_dt).total_seconds() / 3600
    if span_h > 24 * 3:
        step = "DAY";    fmt = "%Y-%m-%d"
    elif span_h > 1:
        step = "HOUR";   fmt = "%Y-%m-%d %H00"
    else:
        step = "MINUTE"; fmt = "%Y-%m-%d %H%M"

    return {
        "start": start_dt.strftime(fmt),
        "end":   end_dt.strftime(fmt),
        "step":  step,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GraphQL 执行
# ─────────────────────────────────────────────────────────────────────────────

async def _gql(query: str, variables: Optional[dict] = None) -> dict:
    """向 SkyWalking OAP 发送 GraphQL 请求，返回 data 字段。"""
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            GRAPHQL_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OAP HTTP {resp.status}: {text[:300]}")
            body = await resp.json()
            if "errors" in body and body["errors"]:
                raise RuntimeError(f"GraphQL errors: {body['errors']}")
            return body.get("data") or {}


# ─────────────────────────────────────────────────────────────────────────────
# 健康检查
# ─────────────────────────────────────────────────────────────────────────────

async def check_connectivity() -> bool:
    """检查 OAP 是否可达（查询服务列表）。"""
    try:
        dur = _build_duration(1)
        await _gql(
            "query { getAllServices(duration: $d) { id } }".replace(
                "$d", f'{{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}'
            )
        )
        return True
    except Exception as e:
        logger.debug("[SkyWalking] connectivity check failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SkyWalking Client
# ─────────────────────────────────────────────────────────────────────────────

class SkyWalkingClient:

    # ── 服务列表 ─────────────────────────────────────────────────────────────
    async def get_services(self, hours: int = 1) -> list[dict]:
        dur = _build_duration(hours)
        data = await _gql("""
        query GetServices($d: Duration!) {
          getAllServices(duration: $d) { id name group }
        }
        """, {"d": dur})
        return data.get("getAllServices") or []

    # ── 服务实例 ─────────────────────────────────────────────────────────────
    async def get_instances(self, service_id: str, hours: int = 1) -> list[dict]:
        dur = _build_duration(hours)
        data = await _gql("""
        query GetInstances($sid: ID!, $d: Duration!) {
          getServiceInstances(duration: $d, serviceId: $sid) {
            id name
            attributes { name value }
          }
        }
        """, {"sid": service_id, "d": dur})
        return data.get("getServiceInstances") or []

    # ── 端点列表 ─────────────────────────────────────────────────────────────
    async def get_endpoints(
        self,
        service_id: str,
        keyword: str = "",
        limit: int = 50,
    ) -> list[dict]:
        data = await _gql("""
        query GetEndpoints($sid: ID!, $kw: String!, $limit: Int!) {
          searchEndpoint(serviceId: $sid, keyword: $kw, limit: $limit) { id name }
        }
        """, {"sid": service_id, "kw": keyword, "limit": limit})
        return data.get("searchEndpoint") or []

    # ── 追踪列表 ─────────────────────────────────────────────────────────────
    async def get_traces(
        self,
        service_id: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        hours: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        error_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        dur = _build_duration(hours, start_time, end_time)
        condition: dict = {
            "queryDuration": dur,
            "traceState": "ERROR" if error_only else "ALL",
            "paging": {"pageNum": page, "pageSize": page_size},
            "orderCondition": {"metric": "startTime", "sort": "DES"},
        }
        if service_id:
            condition["serviceId"] = service_id
        if endpoint_id:
            condition["endpointId"] = endpoint_id
        if trace_id:
            condition["traceId"] = trace_id

        data = await _gql("""
        query GetTraces($c: TraceQueryCondition!) {
          queryBasicTraces(condition: $c) {
            traces {
              segmentId
              endpointNames
              duration
              start
              isError
              traceIds
            }
            total
          }
        }
        """, {"c": condition})
        result = data.get("queryBasicTraces") or {}
        return {
            "traces": result.get("traces") or [],
            "total":  result.get("total") or 0,
        }

    # ── 追踪详情（Span 列表）─────────────────────────────────────────────────
    async def get_trace_detail(self, trace_id: str) -> list[dict]:
        data = await _gql("""
        query GetTrace($tid: ID!) {
          queryTrace(traceId: $tid) {
            spans {
              traceId
              segmentId
              spanId
              parentSpanId
              refs {
                traceId
                parentSegmentId
                parentSpanId
                type
              }
              serviceCode
              serviceInstanceName
              startTime
              endTime
              endpoint
              type
              peer
              component
              isError
              layer
              tags  { key value }
              logs  { time data { key value } }
            }
          }
        }
        """, {"tid": trace_id})
        result = data.get("queryTrace") or {}
        return result.get("spans") or []

    # ── 服务拓扑 ─────────────────────────────────────────────────────────────
    async def get_topology(
        self,
        hours: int = 1,
        service_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        dur = _build_duration(hours, start_time, end_time)
        if service_id:
            data = await _gql("""
            query GetSvcTopo($sid: ID!, $d: Duration!) {
              getServiceTopology(serviceId: $sid, duration: $d) {
                nodes { id name type isReal }
                calls { id source target callType detectPoints }
              }
            }
            """, {"sid": service_id, "d": dur})
            result = data.get("getServiceTopology") or {}
        else:
            data = await _gql("""
            query GetGlobalTopo($d: Duration!) {
              getGlobalTopology(duration: $d) {
                nodes { id name type isReal }
                calls { id source target callType detectPoints }
              }
            }
            """, {"d": dur})
            result = data.get("getGlobalTopology") or {}
        return {
            "nodes": result.get("nodes") or [],
            "calls": result.get("calls") or [],
        }

    # ── 服务性能指标 ─────────────────────────────────────────────────────────
    async def get_service_metrics(
        self,
        service_name: str,
        hours: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        dur    = _build_duration(hours, start_time, end_time)
        entity = {"scope": "Service", "serviceName": service_name, "normal": True}

        async def _read(metric_name: str) -> list:
            try:
                d = await _gql("""
                query ReadMetric($name: String!, $entity: Entity!, $d: Duration!) {
                  readMetricsValues(
                    condition: { name: $name, entity: $entity }
                    duration: $d
                  ) {
                    label
                    values { values { id value } }
                  }
                }
                """, {"name": metric_name, "entity": entity, "d": dur})
                mv = d.get("readMetricsValues")
                if mv and mv.get("values") and mv["values"].get("values"):
                    return [
                        {"id": v.get("id", ""), "value": v.get("value") or 0}
                        for v in mv["values"]["values"]
                    ]
            except Exception as exc:
                logger.debug("[SkyWalking] metric %s failed: %s", metric_name, exc)
            return []

        resp_time  = await _read("service_resp_time")   # ms 平均响应时间
        throughput = await _read("service_cpm")          # 每分钟调用次数
        sla        = await _read("service_sla")          # 成功率 (0~10000, /100 = %)
        p99        = await _read("service_percentile")   # 可能是多条label
        error_rate = [
            {"id": v["id"], "value": round(100 - v["value"] / 100, 2)}
            for v in sla
        ] if sla else []

        return {
            "resp_time":  resp_time,
            "throughput": throughput,
            "error_rate": error_rate,
            "p99":        p99,
            "duration":   dur,
        }


# 全局单例
sw_client = SkyWalkingClient()
