"""SkyWalking Demo Data
当 OAP 不可达时自动返回模拟的微服务链路数据，便于开发和演示。

覆盖：services / traces / trace-detail / topology / metrics / instances / endpoint-topn
"""
import random
import time
import uuid as _uuid

# ── 工具 ──────────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)

def _seg_id(seed: str) -> str:
    """生成稳定格式的 segment ID。"""
    h = abs(hash(seed)) % (10 ** 15)
    return f"{h:015d}.{random.randint(10, 99)}.{random.randint(10000, 99999)}"

def _trace_id() -> str:
    return str(_uuid.uuid4()).replace("-", "")[:32]


# ── 服务列表 ───────────────────────────────────────────────────────────────────

SERVICES = [
    {"id": "svc-gateway",      "name": "gateway-service",      "group": ""},
    {"id": "svc-order",        "name": "order-service",        "group": ""},
    {"id": "svc-payment",      "name": "payment-service",      "group": ""},
    {"id": "svc-inventory",    "name": "inventory-service",    "group": ""},
    {"id": "svc-user",         "name": "user-service",         "group": ""},
    {"id": "svc-notification", "name": "notification-service", "group": ""},
]

# ── 拓扑 ───────────────────────────────────────────────────────────────────────

TOPOLOGY = {
    "nodes": [
        {"id": "svc-gateway",      "name": "gateway-service",      "type": "SpringMVC", "isReal": True},
        {"id": "svc-order",        "name": "order-service",        "type": "SpringMVC", "isReal": True},
        {"id": "svc-payment",      "name": "payment-service",      "type": "SpringMVC", "isReal": True},
        {"id": "svc-inventory",    "name": "inventory-service",    "type": "SpringMVC", "isReal": True},
        {"id": "svc-user",         "name": "user-service",         "type": "SpringMVC", "isReal": True},
        {"id": "svc-notification", "name": "notification-service", "type": "SpringMVC", "isReal": True},
        {"id": "ext-mysql",        "name": "MySQL",                "type": "Database",  "isReal": False},
        {"id": "ext-redis",        "name": "Redis",                "type": "Cache",     "isReal": False},
        {"id": "ext-kafka",        "name": "Kafka",                "type": "MQ",        "isReal": False},
    ],
    "calls": [
        {"id": "c1",  "source": "svc-gateway",      "target": "svc-order",        "detectPoints": ["CLIENT", "SERVER"]},
        {"id": "c2",  "source": "svc-gateway",      "target": "svc-user",         "detectPoints": ["CLIENT", "SERVER"]},
        {"id": "c3",  "source": "svc-order",        "target": "svc-payment",      "detectPoints": ["CLIENT", "SERVER"]},
        {"id": "c4",  "source": "svc-order",        "target": "svc-inventory",    "detectPoints": ["CLIENT", "SERVER"]},
        {"id": "c5",  "source": "svc-order",        "target": "svc-notification", "detectPoints": ["CLIENT", "SERVER"]},
        {"id": "c6",  "source": "svc-payment",      "target": "ext-mysql",        "detectPoints": ["CLIENT"]},
        {"id": "c7",  "source": "svc-inventory",    "target": "ext-redis",        "detectPoints": ["CLIENT"]},
        {"id": "c8",  "source": "svc-inventory",    "target": "ext-mysql",        "detectPoints": ["CLIENT"]},
        {"id": "c9",  "source": "svc-user",         "target": "ext-mysql",        "detectPoints": ["CLIENT"]},
        {"id": "c10", "source": "svc-notification", "target": "ext-kafka",        "detectPoints": ["CLIENT"]},
    ],
}


# ── Trace 模板 ─────────────────────────────────────────────────────────────────

# 定义 10 种典型调用场景，生成时按时间偏移错开
_SCENARIOS = [
    # (endpoint, duration_ms, is_error, service_id)
    ("POST:/api/orders/create",             245, False, "svc-order"),
    ("GET:/api/orders/{orderId}",            38, False, "svc-order"),
    ("POST:/api/payments/process",          187, False, "svc-payment"),
    ("GET:/api/users/profile",               22, False, "svc-user"),
    ("PUT:/api/inventory/reserve",           91, False, "svc-inventory"),
    ("POST:/api/notifications/send",         15, False, "svc-notification"),
    ("POST:/api/orders/create",            1342, True,  "svc-order"),   # 超时
    ("GET:/api/orders/list",                 55, False, "svc-order"),
    ("POST:/api/payments/refund",           203, False, "svc-payment"),
    ("GET:/api/inventory/stock",             31, False, "svc-inventory"),
    ("POST:/api/users/login",                44, False, "svc-user"),
    ("POST:/api/orders/cancel",              88, False, "svc-order"),
    ("GET:/api/gateway/health",               8, False, "svc-gateway"),
    ("POST:/api/orders/create",             512, False, "svc-order"),
    ("GET:/api/payments/status/{id}",        29, False, "svc-payment"),
    ("DELETE:/api/inventory/reserve/{id}",   67, False, "svc-inventory"),
    ("PUT:/api/users/password",              36, False, "svc-user"),
    ("POST:/api/notifications/batch",       142, False, "svc-notification"),
    ("GET:/api/gateway/routes",              12, False, "svc-gateway"),
    ("POST:/api/payments/process",          890, True,  "svc-payment"),  # 支付失败
]


def get_traces(
    page: int = 1,
    page_size: int = 20,
    service_id: str | None = None,
    error_only: bool = False,
    trace_id: str | None = None,
) -> dict:
    """生成分页的 Trace 列表。"""
    now = _now_ms()
    # 生成 60 条分布在最近 2h 内的 trace
    all_traces = []
    for i, (ep, dur, is_err, svc_id) in enumerate(_SCENARIOS * 3):
        offset_ms = (i * 127 + 31) % (120 * 60 * 1000)   # 均匀分布在 2h
        start_ms  = now - offset_ms
        tid       = _trace_id()
        seg       = _seg_id(f"{tid}-{i}")
        all_traces.append({
            "segmentId":     seg,
            "traceIds":      [tid],
            "endpointNames": [ep],
            "duration":      dur,
            "start":         str(start_ms),
            "isError":       is_err,
            "serviceCode":   next((s["name"] for s in SERVICES if s["id"] == svc_id), "order-service"),
        })

    # 过滤
    filtered = all_traces
    if service_id:
        svc_name = next((s["name"] for s in SERVICES if s["id"] == service_id), None)
        if svc_name:
            filtered = [t for t in filtered if t["serviceCode"] == svc_name]
    if error_only:
        filtered = [t for t in filtered if t["isError"]]
    if trace_id:
        filtered = [t for t in filtered if trace_id in t["traceIds"][0]]

    total = len(filtered)
    start = (page - 1) * page_size
    end   = start + page_size
    return {"traces": filtered[start:end], "total": total}


# ── Trace Detail (Span 瀑布图) ─────────────────────────────────────────────────

def _build_spans(trace_id: str, is_error: bool, total_dur: int) -> list[dict]:
    """
    构造一次完整的微服务链路 Span：
    gateway → order-service → payment-service → MySQL
                           → inventory-service → Redis
                           → notification-service → Kafka
    """
    t0   = _now_ms() - 60_000   # 1 分钟前
    segs = {svc: _seg_id(f"{trace_id}-{svc}") for svc in
            ["gateway", "order", "payment", "inventory", "notification"]}

    # 各服务耗时分配
    gw_dur   = max(total_dur, 10)
    ord_dur  = int(gw_dur  * 0.92)
    pay_dur  = int(ord_dur * 0.52)
    inv_dur  = int(ord_dur * 0.30)
    ntf_dur  = int(ord_dur * 0.10)
    mysql_pay= int(pay_dur * 0.70)
    redis_dur= int(inv_dur * 0.40)
    mysql_inv= int(inv_dur * 0.45)
    kafka_dur= int(ntf_dur * 0.60)

    pay_err = is_error and total_dur > 500   # 超时时支付出错

    spans = []

    def sp(seg, span_id, parent_span_id, svc, instance, ep, stype, layer,
           start_off, dur, is_err=False, component="Spring MVC",
           peer="", tags=None, refs=None):
        spans.append({
            "segmentId":          seg,
            "spanId":             span_id,
            "parentSpanId":       parent_span_id,
            "serviceCode":        svc,
            "serviceInstanceName":instance,
            "startTime":          t0 + start_off,
            "endTime":            t0 + start_off + dur,
            "endpointName":       ep,
            "type":               stype,
            "layer":              layer,
            "isError":            is_err,
            "component":          component,
            "peer":               peer,
            "tags":               tags or [],
            "logs":               [],
            "refs":               refs or [],
        })

    # ① gateway-service  Entry  span
    sp(segs["gateway"], 0, -1, "gateway-service", "gateway@10.0.1.1",
       "POST:/api/orders/create", "Entry", "Http", 0, gw_dur,
       tags=[{"key":"http.method","value":"POST"},{"key":"http.status","value":"200"},
             {"key":"url","value":"/api/orders/create"}])

    # ② gateway → order (Exit)
    sp(segs["gateway"], 1, 0, "gateway-service", "gateway@10.0.1.1",
       "order-service:/api/orders/create", "Exit", "Http", 2, ord_dur,
       component="OpenFeign", peer="order-service:8081")

    # ③ order-service Entry
    sp(segs["order"], 0, -1, "order-service", "order@10.0.1.2",
       "POST:/api/orders/create", "Entry", "Http", 3, ord_dur - 2,
       tags=[{"key":"http.method","value":"POST"}],
       refs=[{"parentSegmentId": segs["gateway"], "parentSpanId": 1}])

    # ④ order → payment (Exit)
    sp(segs["order"], 1, 0, "order-service", "order@10.0.1.2",
       "payment-service:/api/payments/process", "Exit", "Http", 5, pay_dur,
       component="OpenFeign", peer="payment-service:8082")

    # ⑤ payment Entry
    sp(segs["payment"], 0, -1, "payment-service", "payment@10.0.1.3",
       "POST:/api/payments/process", "Entry", "Http", 6, pay_dur - 2,
       is_err=pay_err,
       tags=[{"key":"http.method","value":"POST"},
             {"key":"http.status","value":"500" if pay_err else "200"}],
       refs=[{"parentSegmentId": segs["order"], "parentSpanId": 1}])

    # ⑥ payment → MySQL
    sp(segs["payment"], 1, 0, "payment-service", "payment@10.0.1.3",
       "INSERT payment_records", "Exit", "Database", 8, mysql_pay,
       is_err=pay_err,
       component="MySQL/JDBC", peer="mysql:3306",
       tags=[{"key":"db.type","value":"sql"},
             {"key":"db.statement","value":"INSERT INTO payment_records(order_id,amount,status) VALUES(?,?,?)"}])

    # ⑦ order → inventory (Exit)，与 payment 并行，偏移 3ms
    sp(segs["order"], 2, 0, "order-service", "order@10.0.1.2",
       "inventory-service:/api/inventory/reserve", "Exit", "Http",
       5 + pay_dur + 3, inv_dur, component="OpenFeign", peer="inventory-service:8083")

    # ⑧ inventory Entry
    sp(segs["inventory"], 0, -1, "inventory-service", "inventory@10.0.1.4",
       "PUT:/api/inventory/reserve", "Entry", "Http", 6 + pay_dur + 3, inv_dur - 2,
       refs=[{"parentSegmentId": segs["order"], "parentSpanId": 2}])

    # ⑨ inventory → Redis
    sp(segs["inventory"], 1, 0, "inventory-service", "inventory@10.0.1.4",
       "GET stock:{sku_id}", "Exit", "Cache", 8 + pay_dur + 3, redis_dur,
       component="Lettuce/Redis", peer="redis:6379",
       tags=[{"key":"db.type","value":"Redis"},{"key":"cache.cmd","value":"GET"}])

    # ⑩ inventory → MySQL (写库存变更)
    sp(segs["inventory"], 2, 0, "inventory-service", "inventory@10.0.1.4",
       "UPDATE inventory", "Exit", "Database", 8 + pay_dur + 3 + redis_dur + 2, mysql_inv,
       component="MySQL/JDBC", peer="mysql:3306",
       tags=[{"key":"db.type","value":"sql"},
             {"key":"db.statement","value":"UPDATE inventory SET quantity=quantity-? WHERE sku_id=?"}])

    # ⑪ order → notification (async Exit)
    ntf_start = 5 + pay_dur + inv_dur + 6
    sp(segs["order"], 3, 0, "order-service", "order@10.0.1.2",
       "notification-service:/api/notifications/send", "Exit", "Http",
       ntf_start, ntf_dur, component="OpenFeign", peer="notification-service:8084")

    # ⑫ notification Entry
    sp(segs["notification"], 0, -1, "notification-service", "notification@10.0.1.5",
       "POST:/api/notifications/send", "Entry", "Http", ntf_start + 1, ntf_dur - 2,
       refs=[{"parentSegmentId": segs["order"], "parentSpanId": 3}])

    # ⑬ notification → Kafka
    sp(segs["notification"], 1, 0, "notification-service", "notification@10.0.1.5",
       "order-events publish", "Exit", "MQ", ntf_start + 2, kafka_dur,
       component="kafka-producer", peer="kafka:9092",
       tags=[{"key":"mq.topic","value":"order-events"},{"key":"mq.broker","value":"kafka:9092"}])

    return spans


def get_trace_detail(trace_id: str) -> list[dict]:
    """根据 trace_id 生成 Span 列表（通过 hash 决定是否含错误）。"""
    is_error  = abs(hash(trace_id)) % 7 == 0
    total_dur = (abs(hash(trace_id)) % 1800) + 80
    return _build_spans(trace_id, is_error, total_dur)


def get_topology() -> dict:
    return TOPOLOGY


# ── 指标 ───────────────────────────────────────────────────────────────────────

def _wave(base: float, amp: float, points: int, noise: float = 0.1) -> list[float]:
    """生成带噪声的正弦波数据，模拟真实监控曲线。"""
    import math
    return [
        round(max(0, base + amp * math.sin(2 * math.pi * i / points)
                       + random.uniform(-noise * base, noise * base)), 2)
        for i in range(points)
    ]

_SVC_METRICS = {
    "gateway-service":      (45,   120, 0.1),
    "order-service":        (180,  280, 1.8),
    "payment-service":      (145,  190, 2.5),
    "inventory-service":    (75,   120, 0.5),
    "user-service":         (30,   85,  0.2),
    "notification-service": (12,   40,  0.3),
}

def get_metrics(service_name: str) -> dict:
    base_resp, base_tps, base_err = _SVC_METRICS.get(
        service_name, (80, 100, 1.0)
    )
    pts = 30
    return {
        "resp_time":  [{"value": v} for v in _wave(base_resp, base_resp * 0.4, pts)],
        "throughput": [{"value": v} for v in _wave(base_tps,  base_tps  * 0.3, pts)],
        "error_rate": [{"value": v} for v in _wave(base_err,  base_err  * 0.6, pts)],
    }

def get_instances(service_name: str) -> list[dict]:
    count = {"gateway-service": 2, "order-service": 3, "payment-service": 2}.get(service_name, 1)
    instances = []
    for i in range(1, count + 1):
        ip = f"10.0.1.{10 + i}"
        instances.append({
            "id":   f"{service_name}-{i}",
            "name": f"{service_name}@{ip}",
            "attributes": [
                {"name": "OS Name",    "value": "Linux"},
                {"name": "JVM",        "value": f"OpenJDK 17.0.{i + 6}"},
                {"name": "Host IP",    "value": ip},
                {"name": "Start Time", "value": "2026-04-01 08:00:00"},
            ],
        })
    return instances


# ── 接口耗时 TopN ──────────────────────────────────────────────────────────────

ENDPOINT_TOPN = [
    {"name": "order-service: POST:/api/orders/create",              "avg_ms": 245, "sla": 97.8},
    {"name": "payment-service: POST:/api/payments/process",         "avg_ms": 187, "sla": 96.5},
    {"name": "inventory-service: PUT:/api/inventory/reserve",       "avg_ms": 91,  "sla": 99.1},
    {"name": "payment-service: POST:/api/payments/refund",          "avg_ms": 203, "sla": 98.0},
    {"name": "order-service: GET:/api/orders/list",                 "avg_ms": 55,  "sla": 99.7},
    {"name": "notification-service: POST:/api/notifications/batch", "avg_ms": 142, "sla": 99.3},
    {"name": "user-service: POST:/api/users/login",                 "avg_ms": 44,  "sla": 99.9},
    {"name": "gateway-service: GET:/api/gateway/routes",            "avg_ms": 12,  "sla": 100.0},
    {"name": "order-service: POST:/api/orders/cancel",              "avg_ms": 88,  "sla": 99.5},
    {"name": "inventory-service: GET:/api/inventory/stock",         "avg_ms": 31,  "sla": 99.8},
]

def get_endpoint_topn(top_n: int = 20) -> list[dict]:
    return ENDPOINT_TOPN[:top_n]
