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
from report_builder import (
    collect_daily_data,
    collect_inspect_data, build_inspect_meta,
    collect_slowlog_data,
    build_slowlog_ai_prompt_short,
)
from report_store import save_report_meta, cleanup_old_reports

logger = logging.getLogger(__name__)


async def _build_and_save_report() -> dict:
    """生成并保存运维日报（非流式），返回完整 report dict。"""
    data = await collect_daily_data()
    report = data["meta"]

    ai_parts: list[str] = []
    async for chunk in analyzer.generate_daily_report(
        error_counts=data["error_counts"],
        total_logs=data["total_logs"],
        service_count=data["service_count"],
        node_status=data["node_status"],
        active_alerts=data["active_alerts"],
        sample_errors=data["error_logs"],
    ):
        ai_parts.append(chunk)
    report["ai_analysis"] = "".join(ai_parts)

    report_path = REPORTS_DIR / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await save_report_meta(report)
    return report


async def _build_inspect_report() -> dict:
    """生成主机巡检日报（用于定时推送）。"""
    data = await collect_inspect_data()
    meta = build_inspect_meta(data)

    ai_parts: list[str] = []
    try:
        async for chunk in analyzer.generate_host_inspect_report(
            data["results"], data["summary"]
        ):
            ai_parts.append(chunk)
    except Exception as e:
        logger.warning("[scheduler] 巡检 AI 分析失败: %s", e)
        s = data["summary"]
        ai_parts.append(
            f"巡检主机 {s['total']} 台，正常 {s['normal']}，"
            f"警告 {s['warning']}，严重 {s['critical']}。"
        )

    meta["ai_analysis"] = "".join(ai_parts)
    meta["type"] = "inspect"

    report_path = REPORTS_DIR / f"{meta['id']}.json"
    report_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    await save_report_meta(meta)
    return meta


async def _build_slowlog_report() -> dict | None:
    """生成慢日志分析报告（非流式，用于定时推送）。未配置目标则返回 None。"""
    config = load_slowlog_targets()
    if not config.get("enabled") or not config.get("targets"):
        return None

    data = await collect_slowlog_data(config)
    if data is None:
        return None

    report = {k: v for k, v in data.items() if not k.startswith("_")}

    if data.get("_all_entries"):
        prompt = build_slowlog_ai_prompt_short(data)
        ai_parts: list[str] = []
        try:
            async for chunk in analyzer.provider.stream(prompt, max_tokens=600):
                ai_parts.append(chunk)
        except Exception as e:
            ai_parts.append(f"AI 分析失败: {e}")
        report["ai_analysis"] = "".join(ai_parts)
    else:
        report["ai_analysis"] = (
            f"分析时段 {data['date_from']}~{data['date_to']} 内未找到满足条件的慢查询。"
        )

    (REPORTS_DIR / f"{report['id']}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    await save_report_meta(report)
    return report


async def _send_group_inspect_notifications(inspect_results: list[dict]) -> None:
    """按主机分组，将巡检结果分别推送到对应分组的飞书群。"""
    groups = load_groups()
    if not groups:
        return
    cmdb = load_cmdb()

    inst_to_group: dict[str, str] = {
        inst: meta.get("group", "")
        for inst, meta in cmdb.items()
        if meta.get("group")
    }

    group_results: dict[str, list[dict]] = {}
    for r in inspect_results:
        gid = inst_to_group.get(r.get("instance", ""), "")
        if gid:
            group_results.setdefault(gid, []).append(r)

    for group in groups:
        gid = group["id"]
        results = group_results.get(gid, [])
        if not results:
            continue
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
                logger.info("[scheduler] 飞书日报推送: %s", result)
                result2 = await send_feishu(inspect_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                logger.info("[scheduler] 飞书巡检推送: %s", result2)
                if slowlog_report:
                    result3 = await send_feishu(slowlog_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                    logger.info("[scheduler] 飞书慢日志推送: %s", result3)
            elif ch == "dingtalk":
                if not DINGTALK_WEBHOOK:
                    logger.warning("[scheduler] DINGTALK_WEBHOOK 未配置，跳过钉钉推送")
                    continue
                result = await send_dingtalk(report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉日报推送: %s", result)
                result2 = await send_dingtalk(inspect_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉巡检推送: %s", result2)
                if slowlog_report:
                    result3 = await send_dingtalk(slowlog_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                    logger.info("[scheduler] 钉钉慢日志推送: %s", result3)
            else:
                logger.warning("[scheduler] 不支持的推送渠道: %s", ch)

        await _send_group_inspect_notifications(raw_inspect_results)

        # 清理超期报告文件
        from state import REPORT_RETENTION_DAYS
        if REPORT_RETENTION_DAYS > 0:
            deleted = await cleanup_old_reports(REPORTS_DIR, REPORT_RETENTION_DAYS)
            if deleted:
                logger.info("[scheduler] 已清理 %d 条超期报告（>%d天）", deleted, REPORT_RETENTION_DAYS)

        logger.info("[scheduler] 定时任务完成，report_id=%s", report["id"])

    except Exception as exc:
        logger.exception("[scheduler] 定时日报任务异常")
        # ── 优化 8：定时任务失败发送告警 ──────────────────────────────
        _err_msg = f"⚠️ 定时报告任务失败：{exc}"
        err_report = {
            "title": "定时报告生成失败",
            "health_score": 0,
            "ai_analysis": _err_msg,
            "total_logs": 0, "total_errors": 0,
            "service_count": 0, "active_alerts": 0, "top10_errors": [],
        }
        for ch in SCHEDULE_CHANNELS:
            try:
                if ch == "feishu" and FEISHU_WEBHOOK:
                    await send_feishu(err_report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD)
                elif ch == "dingtalk" and DINGTALK_WEBHOOK:
                    await send_dingtalk(err_report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
            except Exception:
                pass
