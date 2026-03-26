"""SkyWalking OAP GraphQL client

端口说明：
  11800 → gRPC（Agent 数据上报，不能用于 HTTP 查询）
  12800 → HTTP REST / GraphQL（查询接口，默认）

如果 12800 连不上，请检查 K8s NodePort 或 Docker 端口映射，
通过 SKYWALKING_OAP_URL 环境变量指定实际可访问的 HTTP 地址。
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SKYWALKING_OAP_URL = os.getenv("SKYWALKING_OAP_URL", "http://192.168.9.226:12800")
GRAPHQL_URL = f"{SKYWALKING_OAP_URL.rstrip('/')}/graphql"


# ─────────────────────────────────────────────────────────────────────────────
# Duration 工具
# ─────────────────────────────────────────────────────────────────────────────

def _build_duration(
    hours: int = 1,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
) -> dict:
    """构造 SkyWalking Duration 对象。

    SkyWalking Duration 格式（必须严格匹配，否则 OAP 返回空数据）：
      DAY    → "yyyy-MM-dd"          e.g. "2025-03-26"
      HOUR   → "yyyy-MM-dd HH"       e.g. "2025-03-26 10"   ← 仅2位小时
      MINUTE → "yyyy-MM-dd HHmm"     e.g. "2025-03-26 1045" ← 4位HHmm
    """
    if start_str and end_str:
        try:
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
        step     = "DAY"
        time_fmt = "%Y-%m-%d"
    elif span_h > 1:
        step     = "HOUR"
        time_fmt = "%Y-%m-%d %H"          # ← 正确：仅 2 位小时，不加 "00"
    else:
        step     = "MINUTE"
        time_fmt = "%Y-%m-%d %H%M"        # ← 正确：4 位 HHmm

    return {
        "start": start_dt.strftime(time_fmt),
        "end":   end_dt.strftime(time_fmt),
        "step":  step,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GraphQL 执行
# ─────────────────────────────────────────────────────────────────────────────

async def _gql(query: str, variables: Optional[dict] = None) -> dict:
    """执行 GraphQL 查询，失败时抛出 RuntimeError 并记录详细日志。"""
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    logger.debug("[SW-GQL] URL=%s vars=%s", GRAPHQL_URL, variables)

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            GRAPHQL_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                logger.error("[SW-GQL] HTTP %d: %s", resp.status, text[:500])
                raise RuntimeError(f"OAP HTTP {resp.status}: {text[:300]}")
            try:
                body = await resp.json(content_type=None)
            except Exception:
                import json as _json
                body = _json.loads(text)
            if "errors" in body and body["errors"]:
                logger.error("[SW-GQL] GraphQL errors: %s", body["errors"])
                raise RuntimeError(f"GraphQL errors: {body['errors']}")
            return body.get("data") or {}


# ─────────────────────────────────────────────────────────────────────────────
# 连通性诊断
# ─────────────────────────────────────────────────────────────────────────────

async def check_connectivity() -> bool:
    try:
        dur = _build_duration(1)
        # 用内联参数而非变量，避免类型声明问题
        await _gql(f"""
        query {{
          getAllServices(duration: {{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}) {{
            id
          }}
        }}
        """)
        return True
    except Exception as e:
        logger.debug("[SkyWalking] connectivity check failed: %s", e)
        return False


async def diagnose() -> dict:
    """返回连通性诊断信息，供 /api/sw/test 端点使用。"""
    import aiohttp as _aio
    result = {
        "oap_url": SKYWALKING_OAP_URL,
        "graphql_url": GRAPHQL_URL,
        "reachable": False,
        "error": None,
        "services_count": 0,
        "duration_sample": None,
    }
    try:
        dur = _build_duration(1)
        result["duration_sample"] = dur
        data = await _gql(f"""
        query {{
          getAllServices(duration: {{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}) {{
            id name
          }}
        }}
        """)
        svcs = data.get("getAllServices") or []
        result["reachable"]      = True
        result["services_count"] = len(svcs)
        result["services"]       = [s["name"] for s in svcs[:10]]
    except _aio.ClientConnectorError as e:
        result["error"] = f"连接失败（端口不通？）: {e}"
    except RuntimeError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SkyWalking Client
# ─────────────────────────────────────────────────────────────────────────────

class SkyWalkingClient:

    # ── 服务列表 ─────────────────────────────────────────────────────────────
    async def get_services(self, hours: int = 1) -> list[dict]:
        dur = _build_duration(hours)
        data = await _gql(f"""
        query {{
          getAllServices(duration: {{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}) {{
            id name group
          }}
        }}
        """)
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

        # !! 注意：TraceQueryCondition 不包含 orderCondition/queryOrder（会报 GraphQL error）
        # 字段严格按 SkyWalking schema：serviceId, endpointId, traceId,
        # queryDuration, traceState, paging
        condition: dict = {
            "queryDuration": dur,
            "traceState": "ERROR" if error_only else "ALL",
            "paging": {"pageNum": page, "pageSize": page_size},
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

    # ── 追踪详情 ─────────────────────────────────────────────────────────────
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
        dur_inline = f'{{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}'
        if service_id:
            data = await _gql(f"""
            query {{
              getServiceTopology(serviceId: "{service_id}", duration: {dur_inline}) {{
                nodes {{ id name type isReal }}
                calls {{ id source target callType detectPoints }}
              }}
            }}
            """)
            result = data.get("getServiceTopology") or {}
        else:
            data = await _gql(f"""
            query {{
              getGlobalTopology(duration: {dur_inline}) {{
                nodes {{ id name type isReal }}
                calls {{ id source target callType detectPoints }}
              }}
            }}
            """)
            result = data.get("getGlobalTopology") or {}
        return {
            "nodes": result.get("nodes") or [],
            "calls": result.get("calls") or [],
        }

    # ── 服务指标 ─────────────────────────────────────────────────────────────
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
                logger.debug("[SW] metric %s failed: %s", metric_name, exc)
            return []

        resp_time  = await _read("service_resp_time")
        throughput = await _read("service_cpm")
        sla        = await _read("service_sla")
        error_rate = [
            {"id": v["id"], "value": round(100 - v["value"] / 100, 2)}
            for v in sla
        ] if sla else []

        return {
            "resp_time":  resp_time,
            "throughput": throughput,
            "error_rate": error_rate,
            "duration":   dur,
        }


# 全局单例
sw_client = SkyWalkingClient()
