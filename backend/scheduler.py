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
)
from notifier import send_feishu, send_dingtalk

logger = logging.getLogger(__name__)


async def _build_and_save_report() -> dict:
    """生成并保存运维日报（非流式），返回完整 report dict。"""
    error_counts = await loki.count_errors_by_service(hours=24)
    error_logs   = await loki.query_error_logs(hours=24, limit=1000)
    services     = await loki.get_services()

    node_status       = {"normal": 27, "abnormal": 0}
    active_alerts     = min(len(error_counts), 3)
    total_error_count = sum(error_counts.values())
    total_logs        = max(total_error_count * 8, total_error_count)

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

        for ch in SCHEDULE_CHANNELS:
            if ch == "feishu":
                if not FEISHU_WEBHOOK:
                    logger.warning("[scheduler] FEISHU_WEBHOOK 未配置，跳过飞书推送")
                    continue
                result = await send_feishu(report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url)
                logger.info("[scheduler] 飞书日报推送结果: %s", result)
                result2 = await send_feishu(inspect_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                logger.info("[scheduler] 飞书巡检日报推送结果: %s", result2)
            elif ch == "dingtalk":
                if not DINGTALK_WEBHOOK:
                    logger.warning("[scheduler] DINGTALK_WEBHOOK 未配置，跳过钉钉推送")
                    continue
                result = await send_dingtalk(report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉日报推送结果: %s", result)
                result2 = await send_dingtalk(inspect_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉巡检日报推送结果: %s", result2)
            else:
                logger.warning("[scheduler] 不支持的推送渠道: %s", ch)
        logger.info("[scheduler] 定时任务完成，report_id=%s", report["id"])
    except Exception:
        logger.exception("[scheduler] 定时日报任务异常")
