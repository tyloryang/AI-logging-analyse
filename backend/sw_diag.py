#!/usr/bin/env python3
"""
SkyWalking OAP 连通性诊断脚本
运行: python sw_diag.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

OAP_URL = os.getenv("SKYWALKING_OAP_URL", "http://192.168.9.226:12800")
GRAPHQL_URL = f"{OAP_URL.rstrip('/')}/graphql"

import aiohttp

async def gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(GRAPHQL_URL, json=payload,
                          headers={"Content-Type": "application/json"}) as r:
            text = await r.text()
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {text[:300]}")
            import json
            body = json.loads(text)
            if body.get("errors"):
                raise RuntimeError(f"GraphQL errors: {body['errors']}")
            return body.get("data") or {}

def make_dur(now_dt, hours=1):
    """生成 Duration，测试不同时区偏移"""
    start = now_dt - timedelta(hours=hours)
    # step=HOUR: span=1h → span_h=1.0 → NOT > 1 → MINUTE
    span_h = hours
    if span_h > 72:
        fmt, step = "%Y-%m-%d", "DAY"
    elif span_h > 1:
        fmt, step = "%Y-%m-%d %H", "HOUR"
    else:
        fmt, step = "%Y-%m-%d %H%M", "MINUTE"
    return {"start": start.strftime(fmt), "end": now_dt.strftime(fmt), "step": step}

async def test_services(dur):
    q = f"""
    query {{
      getAllServices(duration: {{start:"{dur['start']}",end:"{dur['end']}",step:{dur['step']}}}) {{
        id name
      }}
    }}
    """
    data = await gql(q)
    return data.get("getAllServices") or []

async def test_traces(dur, service_id=None):
    condition = {
        "queryDuration": dur,
        "traceState": "ALL",
        "paging": {"pageNum": 1, "pageSize": 5},
    }
    if service_id:
        condition["serviceId"] = service_id
    data = await gql("""
    query GetTraces($c: TraceQueryCondition!) {
      queryBasicTraces(condition: $c) {
        traces { segmentId endpointNames duration start isError traceIds }
        total
      }
    }
    """, {"c": condition})
    r = data.get("queryBasicTraces") or {}
    return r.get("traces") or [], r.get("total") or 0

async def main():
    print(f"\n{'='*60}")
    print(f"SkyWalking OAP: {OAP_URL}")
    print(f"GraphQL:        {GRAPHQL_URL}")
    print(f"{'='*60}\n")

    # ── 1. 基础连通 ──
    print("► 测试基础 HTTP 连通...")
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(OAP_URL) as r:
                print(f"  HTTP GET {OAP_URL} → {r.status}")
    except Exception as e:
        print(f"  ✗ 连接失败: {e}")
        print("  请检查 OAP 端口和网络连通性\n")
        return

    # ── 2. 多时区测试 ──
    utc_now   = datetime.now(timezone.utc).replace(tzinfo=None)
    local_now = datetime.now()  # 系统本地时间

    print(f"\n► 当前时间:")
    print(f"  UTC   本地时间: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  系统  本地时间: {local_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  CST+8 推测时间: {(utc_now + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')}")

    offsets = [
        ("UTC+0 (当前代码逻辑)", 0, utc_now),
        ("本地系统时间",         None, local_now),
        ("UTC+8 (Asia/Shanghai)", 8, utc_now + timedelta(hours=8)),
    ]

    best_offset = None
    for label, offset, now_dt in offsets:
        dur = make_dur(now_dt, hours=3)  # 用3小时，step=HOUR更稳定
        print(f"\n► [{label}] Duration: {dur}")
        try:
            svcs = await test_services(dur)
            print(f"  getAllServices → {len(svcs)} 个服务", end="")
            if svcs:
                print(f": {[s['name'] for s in svcs[:5]]}")
                if best_offset is None:
                    best_offset = (label, offset, svcs)
            else:
                print()

            # 尝试查追踪
            traces, total = await test_traces(dur)
            print(f"  queryBasicTraces → total={total}, traces={len(traces)}")
            if traces:
                t = traces[0]
                print(f"  示例: endpoint={t.get('endpointNames')}, dur={t.get('duration')}ms")
        except Exception as e:
            print(f"  ✗ 错误: {e}")

    # ── 3. 结论 ──
    print(f"\n{'='*60}")
    if best_offset:
        label, offset, svcs = best_offset
        print(f"✓ 有效时区: {label}")
        if offset == 0:
            print("  → 当前代码逻辑正确，问题在别处")
        else:
            tz_str = f"+{offset}" if isinstance(offset, int) else "本地系统时间"
            print(f"  → 需要将时间偏移设为 {tz_str}")
            if isinstance(offset, int) and offset != 0:
                print(f"\n  在 .env 中添加:")
                print(f"  SW_TIMEZONE_OFFSET={offset}")
    else:
        print("✗ 所有时区测试均未找到数据")
        print("  可能原因: OAP 无追踪数据，或 Agent 未正确接入")

    print(f"{'='*60}\n")

asyncio.run(main())
