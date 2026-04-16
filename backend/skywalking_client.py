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


def _current_graphql_url() -> str:
    """每次调用时从 os.environ 读取，支持 settings 页面热更新。"""
    base = os.getenv("SKYWALKING_OAP_URL", SKYWALKING_OAP_URL).rstrip("/")
    return f"{base}/graphql"


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
    elif span_h >= 1:                      # ← >= 1 避免 1h 刚好落到 MINUTE 粒度
        step     = "HOUR"
        time_fmt = "%Y-%m-%d %H"
    else:
        step     = "MINUTE"
        time_fmt = "%Y-%m-%d %H%M"

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

    gql_url = _current_graphql_url()
    logger.debug("[SW-GQL] URL=%s vars=%s", gql_url, variables)

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            gql_url,
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
        "oap_url": os.getenv("SKYWALKING_OAP_URL", SKYWALKING_OAP_URL),
        "graphql_url": _current_graphql_url(),
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
# Demo-mode 检测
# ─────────────────────────────────────────────────────────────────────────────

def _is_conn_error(exc: Exception) -> bool:
    """判断是否为连接失败（非业务错误），此时应 fallback 到 Demo 数据。"""
    import aiohttp
    import asyncio
    return isinstance(exc, (
        aiohttp.ClientConnectorError,
        aiohttp.ServerConnectionError,
        aiohttp.ClientOSError,
        asyncio.TimeoutError,
        ConnectionRefusedError,
        OSError,
        RuntimeError,          # OAP 返回 HTTP 错误或 GraphQL 错误都算不可用
    ))


def _demo_mode() -> bool:
    """环境变量 SW_DEMO_MODE=1 可强制使用 Demo 数据（无需 OAP）。"""
    return os.getenv("SW_DEMO_MODE", "").lower() in ("1", "true", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# SkyWalking Client
# ─────────────────────────────────────────────────────────────────────────────

class SkyWalkingClient:

    # ── 服务列表 ─────────────────────────────────────────────────────────────
    async def get_services(
        self,
        hours: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> list[dict]:
        if _demo_mode():
            import sw_mock; return sw_mock.SERVICES
        try:
            dur = _build_duration(hours, start_time, end_time)
            data = await _gql(f"""
            query {{
              getAllServices(duration: {{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}) {{
                id name group
              }}
            }}
            """)
            result = data.get("getAllServices") or []
            if not result:
                import sw_mock; return sw_mock.SERVICES
            return result
        except Exception as e:
            if _is_conn_error(e):
                logger.info("[SW] OAP 不可达，使用 Demo 服务列表: %s", e)
                import sw_mock; return sw_mock.SERVICES
            raise

    # ── 服务实例 ─────────────────────────────────────────────────────────────
    async def get_instances(self, service_id: str, hours: int = 1) -> list[dict]:
        if _demo_mode():
            import sw_mock
            svc_name = next((s["name"] for s in sw_mock.SERVICES if s["id"] == service_id), service_id)
            return sw_mock.get_instances(svc_name)
        try:
            dur = _build_duration(hours)
            data = await _gql("""
            query GetInstances($sid: ID!, $d: Duration!) {
              getServiceInstances(duration: $d, serviceId: $sid) {
                id name
                attributes { name value }
              }
            }
            """, {"sid": service_id, "d": dur})
            result = data.get("getServiceInstances") or []
            if not result:
                import sw_mock
                svc_name = next((s["name"] for s in sw_mock.SERVICES if s["id"] == service_id), service_id)
                return sw_mock.get_instances(svc_name)
            return result
        except Exception as e:
            if _is_conn_error(e):
                import sw_mock
                svc_name = next((s["name"] for s in sw_mock.SERVICES if s["id"] == service_id), service_id)
                return sw_mock.get_instances(svc_name)
            raise

    # ── 端点列表 ─────────────────────────────────────────────────────────────
    async def get_endpoints(
        self,
        service_id: str,
        keyword: str = "",
        limit: int = 50,
    ) -> list[dict]:
        if _demo_mode():
            return []
        try:
            data = await _gql("""
            query GetEndpoints($sid: ID!, $kw: String!, $limit: Int!) {
              searchEndpoint(serviceId: $sid, keyword: $kw, limit: $limit) { id name }
            }
            """, {"sid": service_id, "kw": keyword, "limit": limit})
            return data.get("searchEndpoint") or []
        except Exception as e:
            if _is_conn_error(e):
                return []
            raise

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
        if _demo_mode():
            import sw_mock
            return sw_mock.get_traces(page, page_size, service_id, error_only, trace_id)
        try:
            dur = _build_duration(hours, start_time, end_time)
            condition: dict = {
                "queryDuration": dur,
                "traceState": "ERROR" if error_only else "ALL",
                "queryOrder": "BY_START_TIME",
                "paging": {"pageNum": page, "pageSize": page_size, "needTotal": True},
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
                  segmentId endpointNames duration start isError traceIds
                }
                total
              }
            }
            """, {"c": condition})
            result = data.get("queryBasicTraces") or {}
            traces = result.get("traces") or []
            if not traces:
                import sw_mock
                return sw_mock.get_traces(page, page_size, service_id, error_only, trace_id)
            return {"traces": traces, "total": result.get("total") or 0}
        except Exception as e:
            if _is_conn_error(e):
                logger.info("[SW] OAP 不可达，使用 Demo Trace 列表: %s", e)
                import sw_mock
                return sw_mock.get_traces(page, page_size, service_id, error_only, trace_id)
            raise

    # ── 追踪详情 ─────────────────────────────────────────────────────────────
    async def get_trace_detail(self, trace_id: str) -> list[dict]:
        if _demo_mode():
            import sw_mock; return sw_mock.get_trace_detail(trace_id)
        try:
            data = await _gql("""
            query GetTrace($tid: ID!) {
              queryTrace(traceId: $tid) {
                spans {
                  traceId segmentId spanId parentSpanId
                  refs { traceId parentSegmentId parentSpanId type }
                  serviceCode serviceInstanceName
                  startTime endTime endpointName
                  type peer component isError layer
                  tags  { key value }
                  logs  { time data { key value } }
                }
              }
            }
            """, {"tid": trace_id})
            result = data.get("queryTrace") or {}
            spans = result.get("spans") or []
            if not spans:
                import sw_mock; return sw_mock.get_trace_detail(trace_id)
            return spans
        except Exception as e:
            if _is_conn_error(e):
                import sw_mock; return sw_mock.get_trace_detail(trace_id)
            raise

    # ── 服务拓扑 ─────────────────────────────────────────────────────────────
    async def get_topology(
        self,
        hours: int = 1,
        service_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        if _demo_mode():
            import sw_mock; return sw_mock.get_topology()
        try:
            dur = _build_duration(hours, start_time, end_time)
            dur_inline = f'{{start:"{dur["start"]}",end:"{dur["end"]}",step:{dur["step"]}}}'
            if service_id:
                data = await _gql(f"""
                query {{
                  getServiceTopology(serviceId: "{service_id}", duration: {dur_inline}) {{
                    nodes {{ id name type isReal }}
                    calls {{ id source target sourceComponents targetComponents detectPoints }}
                  }}
                }}
                """)
                result = data.get("getServiceTopology") or {}
            else:
                data = await _gql(f"""
                query {{
                  getGlobalTopology(duration: {dur_inline}) {{
                    nodes {{ id name type isReal }}
                    calls {{ id source target sourceComponents targetComponents detectPoints }}
                  }}
                }}
                """)
                result = data.get("getGlobalTopology") or {}
            nodes = result.get("nodes") or []
            if not nodes:
                import sw_mock; return sw_mock.get_topology()
            return {"nodes": nodes, "calls": result.get("calls") or []}
        except Exception as e:
            if _is_conn_error(e):
                logger.info("[SW] OAP 不可达，使用 Demo 拓扑: %s", e)
                import sw_mock; return sw_mock.get_topology()
            raise

    # ── 服务指标 ─────────────────────────────────────────────────────────────
    async def get_service_metrics(
        self,
        service_name: str,
        hours: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        if _demo_mode():
            import sw_mock; return sw_mock.get_metrics(service_name)
        try:
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

            if not resp_time and not throughput:
                import sw_mock; return sw_mock.get_metrics(service_name)

            return {"resp_time": resp_time, "throughput": throughput,
                    "error_rate": error_rate, "duration": dur}
        except Exception as e:
            if _is_conn_error(e):
                import sw_mock; return sw_mock.get_metrics(service_name)
            raise

    # ── 接口耗时 TopN ─────────────────────────────────────────────────────────
    async def get_endpoint_topn(
        self,
        hours: int = 24,
        top_n: int = 20,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> list[dict]:
        if _demo_mode():
            import sw_mock; return sw_mock.get_endpoint_topn(top_n)
        try:
            dur = _build_duration(hours, start_time, end_time)
            results = []
            for metric, label in (
                ("endpoint_avg", "avg_ms"),
                ("endpoint_cpm", "cpm"),
                ("endpoint_sla", "sla"),
            ):
                try:
                    data = await _gql("""
                    query TopN($d: Duration!, $name: String!, $n: Int!) {
                      getAllEndpointTopN(duration: $d, name: $name, topN: $n, order: DES) {
                        name value
                      }
                    }
                    """, {"d": dur, "name": metric, "n": top_n})
                    items = data.get("getAllEndpointTopN") or []
                    if label == "avg_ms":
                        results = items
                        for item in results:
                            item["avg_ms"] = item.pop("value", 0)
                    else:
                        lookup = {it["name"]: it["value"] for it in items}
                        for item in results:
                            item[label] = lookup.get(item["name"], 0)
                except Exception as exc:
                    logger.debug("[SW] endpoint_topn %s failed: %s", metric, exc)

            for item in results:
                raw_sla = item.get("sla", 0)
                item["sla"] = round(raw_sla / 100, 2) if raw_sla else 0

            if not results:
                import sw_mock; return sw_mock.get_endpoint_topn(top_n)
            return results
        except Exception as e:
            if _is_conn_error(e):
                import sw_mock; return sw_mock.get_endpoint_topn(top_n)
            raise


# 全局单例
sw_client = SkyWalkingClient()
