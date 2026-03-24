"""APScheduler 定时任务：生成运维日报 + 主机巡检日报并推送。"""
import json
import logging
from datetime import datetime, timezone

from state import (
    loki, prom, analyzer,
    REPORTS_DIR,
    FEISHU_WEBHOOK, FEISHU_KEYWORD,
    DINGTALK_WEBHOOK, DINGTALK_KEYWORD,
    APP_URL, SCHEDULE_CHANNELS,
    load_slowlog_targets,
    load_groups, load_cmdb,
)
from notifier import send_feishu, send_dingtalk, send_feishu_group_inspect

logger = logging.getLogger(__name__)


async def _build_and_save_report() -> dict:
    """生成并保存运维日报（非流式），返回完整 report dict。"""
    error_counts = await loki.count_errors_by_service(hours=24)
    error_logs   = await loki.query_error_logs(hours=24, limit=1000)
    services     = await loki.get_services()

    total_error_count = sum(error_counts.values())
    total_logs        = total_error_count * 8
    active_alerts     = len(error_counts)

    try:
        hosts       = await prom.discover_hosts()
        node_normal = sum(1 for h in hosts if h.get("state") == "up")
        node_status = {"normal": node_normal, "abnormal": len(hosts) - node_normal}
    except Exception:
        node_status = {"normal": 0, "abnormal": 0}

    health_score = await analyzer.calculate_health_score(
        total_logs, total_error_count, active_alerts, node_status["abnormal"]
    )

    now       = datetime.now(timezone.utc)
    report_id = now.strftime("%Y%m%d%H%M%S")

    report = {
        "id":            report_id,
        "title":         f"运维日报 {now.strftime('%Y-%m-%d')}",
        "created_at":    now.isoformat(),
        "health_score":  health_score,
        "total_logs":    total_logs,
        "total_errors":  total_error_count,
        "service_count": len(services),
        "active_alerts": active_alerts,
        "node_status":   node_status,
        "top10_errors":  [
            {"service": k, "count": v}
            for k, v in list(error_counts.items())[:10]
        ],
    }

    ai_parts: list[str] = []
    async for chunk in analyzer.generate_daily_report(
        error_counts=error_counts,
        total_logs=total_logs,
        service_count=len(services),
        node_status=node_status,
        active_alerts=active_alerts,
        sample_errors=error_logs,
    ):
        ai_parts.append(chunk)
    report["ai_analysis"] = "".join(ai_parts)

    report_path = REPORTS_DIR / f"{report_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def _build_inspect_report() -> dict:
    """生成主机巡检日报（用于定时推送）。"""
    try:
        results = await prom.inspect_hosts()
    except Exception as e:
        logger.warning("[scheduler] 巡检数据获取失败: %s", e)
        results = []

    total    = len(results)
    normal   = sum(1 for r in results if r.get("overall") == "normal")
    warning  = sum(1 for r in results if r.get("overall") == "warning")
    critical = sum(1 for r in results if r.get("overall") == "critical")
    summary  = {"total": total, "normal": normal, "warning": warning, "critical": critical}

    health_score = await analyzer.calculate_host_health_score(summary)

    ai_parts: list[str] = []
    try:
        async for chunk in analyzer.generate_host_inspect_report(results, summary):
            ai_parts.append(chunk)
    except Exception as e:
        logger.warning("[scheduler] 巡检 AI 分析失败: %s", e)
        ai_parts.append(f"巡检主机 {total} 台，正常 {normal}，警告 {warning}，严重 {critical}。")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "title":         f"🔍 主机巡检日报 · {now_str}",
        "health_score":  health_score,
        "ai_analysis":   "".join(ai_parts),
        "total_logs":    total,
        "total_errors":  warning + critical,
        "service_count": normal,
        "active_alerts": critical,
        "top10_errors":  [],
    }


async def _build_slowlog_report() -> dict | None:
    """生成慢日志分析报告（非流式，用于定时推送）。未配置目标则返回 None。"""
    from datetime import date as date_cls, timedelta
    from slow_log_parser import parse_slow_log, build_summary
    from sql_cluster import cluster_slow_queries
    from routers.slowlog import _read_remote_file, _resolve_credential

    config  = load_slowlog_targets()
    if not config.get("enabled") or not config.get("targets"):
        return None

    date_days     = max(1, int(config.get("date_days", 1)))
    threshold_sec = float(config.get("threshold_sec", 1.0))
    alert_sec     = float(config.get("alert_sec", 10.0))
    today         = date_cls.today()
    date_from     = (today - timedelta(days=date_days - 1)).strftime("%Y-%m-%d")
    date_to       = today.strftime("%Y-%m-%d")

    host_results: list[dict] = []
    all_entries:  list[dict] = []
    errors:       list[dict] = []

    for t in config["targets"]:
        host_ip  = (t.get("host_ip") or "").strip()
        log_path = t.get("log_path") or "/mysqldata/mysql/data/3306/mysql-slow.log"
        if not host_ip:
            continue
        try:
            username, password, host, port = _resolve_credential(
                host_ip,
                credential_id=t.get("credential_id", ""),
                username=t.get("ssh_user", ""),
                password=t.get("ssh_password", ""),
                port=int(t.get("ssh_port", 22)),
            )
            text    = await _read_remote_file(host, port, username, password, log_path)
            entries = parse_slow_log(
                text, date_from=date_from, date_to=date_to,
                threshold_sec=threshold_sec, alert_sec=alert_sec,
            )
            try:
                clusters = cluster_slow_queries(entries)
            except Exception:
                clusters = []
            summary = build_summary(entries)
            for e in entries:
                all_entries.append({**e, "_host_ip": host_ip})
            host_results.append({
                "host_ip":        host_ip,
                "total":          summary.get("total", 0),
                "alert_count":    summary.get("alert_count", 0),
                "avg_query_time": summary.get("avg_query_time", 0),
                "max_query_time": summary.get("max_query_time", 0),
                "top_clusters": [
                    {k: c[k] for k in ("rank", "template", "count", "total_time", "avg_time", "max_time", "alert_count")}
                    for c in clusters[:5]
                ],
            })
        except Exception as e:
            logger.warning("[scheduler][slowlog] %s 失败: %s", host_ip, e)
            errors.append({"host_ip": host_ip, "error": str(e)})

    total_queries = sum(r["total"] for r in host_results)
    alert_queries = sum(r["alert_count"] for r in host_results)
    avg_qt = (
        sum(r["avg_query_time"] * r["total"] for r in host_results) / total_queries
        if total_queries else 0.0
    )
    max_qt = max((r["max_query_time"] for r in host_results), default=0.0)

    if total_queries == 0:
        health_score = 50
    else:
        deduct = 0
        ratio = alert_queries / total_queries
        if ratio > 0.3:   deduct += 40
        elif ratio > 0.1: deduct += 20
        if max_qt > 60:   deduct += 20
        elif max_qt > 30: deduct += 10
        if avg_qt > 10:   deduct += 15
        elif avg_qt > 5:  deduct += 8
        health_score = max(0, 100 - deduct)

    top_slow_brief = [
        {
            "host_ip":       e.get("_host_ip", ""),
            "query_time":    e.get("query_time", 0),
            "rows_examined": e.get("rows_examined", 0),
            "sql_brief":     e.get("sql", "")[:200],
        }
        for e in sorted(all_entries, key=lambda e: e.get("query_time", 0), reverse=True)[:10]
    ]

    now       = datetime.now(timezone.utc)
    now_str   = now.strftime("%Y-%m-%d")
    report_id = "slowlog_" + now.strftime("%Y%m%d%H%M%S")

    report: dict = {
        "id":             report_id,
        "type":           "slowlog",
        "title":          f"MySQL 慢日志报告 {now_str}",
        "created_at":     now.isoformat(),
        "health_score":   health_score,
        "date_from":      date_from,
        "date_to":        date_to,
        "total_queries":  total_queries,
        "alert_queries":  alert_queries,
        "avg_query_time": round(avg_qt, 2),
        "max_query_time": round(max_qt, 3),
        "hosts_count":    len(host_results),
        "host_results":   host_results,
        "top_slow":       top_slow_brief,
        "errors":         errors,
    }

    # AI 分析
    if all_entries:
        prompt = (
            f"你是 MySQL 数据库性能专家，请简要分析以下慢查询汇总并给出优化建议。\n"
            f"时间段：{date_from} ~ {date_to}，主机 {len(host_results)} 台，"
            f"慢查询 {total_queries} 条，告警 {alert_queries} 条，最大耗时 {round(max_qt, 1)}s。\n"
        )
        for hr in host_results:
            prompt += f"- {hr['host_ip']}：{hr['total']} 条，{hr['alert_count']} 告警\n"
        if top_slow_brief:
            prompt += "\nTOP 5：\n"
            for i, s in enumerate(top_slow_brief[:5], 1):
                prompt += f"[{i}] {s['host_ip']} {s['query_time']}s  SQL: {s['sql_brief'][:150]}\n"
        prompt += "\n请给出整体评估和关键优化建议（200字以内）。使用中文。"

        ai_parts: list[str] = []
        try:
            async for chunk in analyzer.provider.stream(prompt, max_tokens=600):
                ai_parts.append(chunk)
        except Exception as e:
            ai_parts.append(f"AI 分析失败: {e}")
        report["ai_analysis"] = "".join(ai_parts)
    else:
        report["ai_analysis"] = f"分析时段 {date_from}~{date_to} 内未找到满足条件的慢查询。"

    (REPORTS_DIR / f"{report_id}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


async def _send_group_inspect_notifications(inspect_results: list[dict]) -> None:
    """按主机分组，将巡检结果分别推送到对应分组的飞书群。"""
    groups = load_groups()
    if not groups:
        return
    cmdb = load_cmdb()

    # 建立 instance -> group_id 映射
    inst_to_group: dict[str, str] = {
        inst: meta.get("group", "")
        for inst, meta in cmdb.items()
        if meta.get("group")
    }

    # 按 group_id 聚合巡检结果
    group_results: dict[str, list[dict]] = {}
    for r in inspect_results:
        gid = inst_to_group.get(r.get("instance", ""), "")
        if gid:
            group_results.setdefault(gid, []).append(r)

    # 逐组推送
    for group in groups:
        gid = group["id"]
        results = group_results.get(gid, [])
        if not results:
            continue
        # 只在有告警主机时推送（正常则静默）
        has_alert = any(r.get("overall") != "normal" for r in results)
        if not has_alert:
            logger.info("[scheduler] 分组 '%s' 全部主机正常，跳过推送", group["name"])
            continue

        if group.get("feishu_webhook"):
            res = await send_feishu_group_inspect(
                group_name=group["name"],
                results=results,
                webhook_url=group["feishu_webhook"],
                keyword=group.get("feishu_keyword", ""),
            )
            logger.info("[scheduler] 分组 '%s' 飞书巡检推送: %s", group["name"], res)


async def scheduled_report_job() -> None:
    """定时任务入口：生成运维日报 + 主机巡检日报，推送到已配置的渠道。"""
    if not SCHEDULE_CHANNELS:
        logger.info("[scheduler] SCHEDULE_CHANNELS 未配置，跳过推送")
        return
    logger.info("[scheduler] 开始生成定时日报 ...")
    try:
        report = await _build_and_save_report()
        report_url = f"{APP_URL}/report/{report['id']}" if APP_URL else ""

        logger.info("[scheduler] 开始生成主机巡检日报 ...")
        inspect_report = await _build_inspect_report()

        # 获取巡检原始结果，用于按分组推送
        try:
            raw_inspect_results = await prom.inspect_hosts()
        except Exception as e:
            logger.warning("[scheduler] 获取巡检原始结果失败: %s", e)
            raw_inspect_results = []

        logger.info("[scheduler] 开始生成慢日志报告 ...")
        try:
            slowlog_report = await _build_slowlog_report()
        except Exception as e:
            logger.warning("[scheduler] 慢日志报告生成失败: %s", e)
            slowlog_report = None

        for ch in SCHEDULE_CHANNELS:
            if ch == "feishu":
                if not FEISHU_WEBHOOK:
                    logger.warning("[scheduler] FEISHU_WEBHOOK 未配置，跳过飞书推送")
                    continue
                result = await send_feishu(report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url)
                logger.info("[scheduler] 飞书日报推送结果: %s", result)
                result2 = await send_feishu(inspect_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                logger.info("[scheduler] 飞书巡检日报推送结果: %s", result2)
                if slowlog_report:
                    result3 = await send_feishu(slowlog_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                    logger.info("[scheduler] 飞书慢日志报告推送结果: %s", result3)
            elif ch == "dingtalk":
                if not DINGTALK_WEBHOOK:
                    logger.warning("[scheduler] DINGTALK_WEBHOOK 未配置，跳过钉钉推送")
                    continue
                result = await send_dingtalk(report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉日报推送结果: %s", result)
                result2 = await send_dingtalk(inspect_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉巡检日报推送结果: %s", result2)
                if slowlog_report:
                    result3 = await send_dingtalk(slowlog_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                    logger.info("[scheduler] 钉钉慢日志报告推送结果: %s", result3)
            else:
                logger.warning("[scheduler] 不支持的推送渠道: %s", ch)

        # 按分组推送巡检告警到各自的飞书群
        await _send_group_inspect_notifications(raw_inspect_results)

        logger.info("[scheduler] 定时任务完成，report_id=%s", report["id"])
    except Exception:
        logger.exception("[scheduler] 定时日报任务异常")
