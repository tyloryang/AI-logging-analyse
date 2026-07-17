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
    load_groups, load_cmdb, load_hosts_list,
)
from notifier import send_feishu, send_dingtalk, send_feishu_group_inspect
from json_snapshot_store import write_json_file
from report_builder import (
    collect_daily_data,
    collect_inspect_data, build_inspect_meta,
    collect_slowlog_data,
    build_slowlog_ai_prompt_short,
)
from report_store import save_report_meta, cleanup_old_reports
from services.inspect_report_delivery import (
    build_public_inspect_pdf_url,
    save_group_inspect_report,
)

logger = logging.getLogger(__name__)


def _delivery_error(result: object) -> str:
    if isinstance(result, dict) and result.get("ok") is False:
        return str(result.get("msg") or "飞书推送失败")
    return ""


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
        service_error_summaries=data["service_error_summaries"],
        error_keywords=data["error_keywords"],
        interface_status=data["interface_status"],
    ):
        ai_parts.append(chunk)
    report["ai_analysis"] = "".join(ai_parts)

    report_path = REPORTS_DIR / f"{report['id']}.json"
    write_json_file(report_path, report, ensure_parent=True)
    await save_report_meta(report)
    return report


async def _build_inspect_report(data: dict | None = None) -> dict:
    """生成主机巡检日报（用于定时推送）。"""
    if data is None:
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
    write_json_file(report_path, meta, ensure_parent=True)
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

    write_json_file(REPORTS_DIR / f"{report['id']}.json", report, ensure_parent=True)
    await save_report_meta(report)
    return report


async def _send_group_inspect_notifications(
    inspect_results: list[dict], force: bool = False, group_id: str = ""
) -> list[dict]:
    """按主机分组推送巡检结果到各组飞书群。
    force=True 时忽略 schedule_enabled，适用于手动触发。
    """
    groups = load_groups()
    if not groups:
        return [{"skipped": True, "reason": "未配置主机分组"}]
    notify_results: list[dict] = []
    if group_id:
        groups = [group for group in groups if group.get("id") == group_id]
        if not groups:
            return [{"group_id": group_id, "skipped": True, "reason": "分组不存在"}]

    hosts = load_hosts_list()
    inst_to_group: dict[str, str] = {
        f"{h['ip']}:9100": h.get("group", "")
        for h in hosts
        if h.get("ip") and h.get("group")
    }

    group_results: dict[str, list[dict]] = {}
    for r in inspect_results:
        gid = r.get("group") or inst_to_group.get(r.get("instance", ""), "")
        if gid:
            group_results.setdefault(gid, []).append(r)

    for group in groups:
        gid = group["id"]
        group_name = group.get("name", gid)
        if not force and not group.get("schedule_enabled"):
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "skipped": True,
                "reason": "未启用定时推送",
            })
            continue
        results = group_results.get(gid, [])
        if not results:
            logger.info("[scheduler] 分组 '%s' 无关联主机，跳过推送", group_name)
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "skipped": True,
                "reason": "该分组无本次巡检主机",
            })
            continue
        if not group.get("feishu_webhook"):
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "skipped": True,
                "reason": "未配置飞书 Webhook",
            })
            continue

        # 生成分组维度的 AI 分析
        ai_text = ""
        total = len(results)
        normal_cnt = sum(1 for r in results if r.get("overall") == "normal")
        warning_cnt = sum(1 for r in results if r.get("overall") == "warning")
        critical_cnt = sum(1 for r in results if r.get("overall") == "critical")
        group_summary = {
            "total": total, "normal": normal_cnt,
            "warning": warning_cnt, "critical": critical_cnt,
            "group_name": group_name,
        }
        try:
            ai_parts: list[str] = []
            async for chunk in analyzer.generate_inspection_summary(results, group_summary):
                ai_parts.append(chunk)
            ai_text = "".join(ai_parts).strip()
            logger.info("[scheduler] 分组 '%s' AI 分析生成完毕（%d 字符）", group_name, len(ai_text))
        except Exception as e:
            logger.warning("[scheduler] 分组 '%s' AI 分析失败，降级为规则摘要: %s", group_name, e)
            ai_text = (
                f"本次巡检分组「{group_name}」共 {total} 台主机，"
                f"正常 {normal_cnt} 台、警告 {warning_cnt} 台、严重 {critical_cnt} 台。"
            )

        try:
            group_report = await save_group_inspect_report(
                results=results,
                group_id=gid,
                group_name=group_name,
                ai_text=ai_text,
            )
        except Exception as exc:
            error_message = str(exc) or repr(exc)
            logger.exception(
                "[scheduler] 分组 '%s' 巡检报告保存失败，跳过推送",
                group_name,
            )
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "stage": "persist",
                "error": error_message,
                "push": {"ok": False, "msg": error_message},
            })
            continue
        report_url = build_public_inspect_pdf_url(group_report["id"], APP_URL)
        if not report_url:
            logger.warning(
                "[scheduler] APP_URL 未配置，分组 '%s' 巡检卡片不附带 PDF 链接",
                group_name,
            )

        try:
            res = await send_feishu_group_inspect(
                group_name=group_name,
                results=results,
                webhook_url=group["feishu_webhook"],
                keyword=group.get("feishu_keyword", ""),
                ai_text=ai_text,
                report_url=report_url,
            )
        except Exception as exc:
            error_message = str(exc) or repr(exc)
            logger.exception("[scheduler] 分组 '%s' 飞书巡检推送失败", group_name)
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "stage": "delivery",
                "error": error_message,
                "push": {"ok": False, "msg": error_message},
            })
            continue
        delivery_error = _delivery_error(res)
        if delivery_error:
            logger.error(
                "[scheduler] 分组 '%s' 飞书巡检推送失败: %s",
                group_name,
                delivery_error,
            )
            notify_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "stage": "delivery",
                "error": delivery_error,
                "push": res,
            })
            continue
        logger.info("[scheduler] 分组 '%s' 飞书巡检推送: %s", group_name, res)
        notify_results.append({
            "group_id": gid,
            "group_name": group_name,
            "hosts": len(results),
            "push": res,
        })

    return notify_results


async def run_group_schedule_job() -> list[dict]:
    """每分钟检查各分组的定时推送计划，到点则巡检对应主机并推送。"""
    from datetime import datetime
    now_hhmm = datetime.now().strftime("%H:%M")
    groups = load_groups()
    due_groups = [
        g for g in groups
        if g.get("schedule_enabled") and g.get("schedule_time", "") == now_hhmm
    ]
    if not due_groups:
        return []

    hosts_all = load_hosts_list()
    job_results: list[dict] = []
    for group in due_groups:
        gid = group["id"]
        group_name = group.get("name", gid)
        instances = [f"{h['ip']}:9100" for h in hosts_all if h.get("group") == gid and h.get("ip")]
        if not instances:
            logger.info("[group_schedule] 分组 '%s' 无关联主机，跳过", group_name)
            job_results.append({
                "group_id": gid,
                "group_name": group_name,
                "skipped": True,
                "reason": "该分组无关联主机",
            })
            continue

        logger.info("[group_schedule] 分组 '%s' 开始巡检 %d 台主机", group_name, len(instances))
        try:
            inspect_data = await collect_inspect_data(
                instances=instances,
                group_id=gid,
                group_name=group_name,
            )
            results = inspect_data["results"]
        except Exception as exc:
            error_message = str(exc) or repr(exc)
            logger.exception("[group_schedule] 分组 '%s' 巡检失败", group_name)
            job_results.append({
                "group_id": gid,
                "group_name": group_name,
                "stage": "inspect",
                "error": error_message,
                "push": {"ok": False, "msg": error_message},
            })
            continue

        group_summary = inspect_data["summary"]
        total = group_summary.get("total", 0)
        normal = group_summary.get("normal", 0)
        warning = group_summary.get("warning", 0)
        critical = group_summary.get("critical", 0)

        ai_text = ""
        try:
            ai_parts: list[str] = []
            async for chunk in analyzer.generate_inspection_summary(results, group_summary):
                ai_parts.append(chunk)
            ai_text = "".join(ai_parts).strip()
        except Exception as e:
            logger.warning("[group_schedule] 分组 '%s' AI 分析失败: %s", group_name, e)
            ai_text = (
                f"分组「{group_name}」共 {total} 台主机，"
                f"正常 {normal} 台、警告 {warning} 台、严重 {critical} 台。"
            )

        if group.get("feishu_webhook"):
            try:
                group_report = await save_group_inspect_report(
                    results=results,
                    group_id=gid,
                    group_name=group_name,
                    ai_text=ai_text,
                )
            except Exception as exc:
                error_message = str(exc) or repr(exc)
                logger.exception(
                    "[group_schedule] 分组 '%s' 巡检报告保存失败，跳过推送",
                    group_name,
                )
                job_results.append({
                    "group_id": gid,
                    "group_name": group_name,
                    "hosts": len(results),
                    "stage": "persist",
                    "error": error_message,
                    "push": {"ok": False, "msg": error_message},
                })
                continue
            report_url = build_public_inspect_pdf_url(group_report["id"], APP_URL)
            if not report_url:
                logger.warning(
                    "[group_schedule] APP_URL 未配置，分组 '%s' 巡检卡片不附带 PDF 链接",
                    group_name,
                )
            try:
                res = await send_feishu_group_inspect(
                    group_name=group_name,
                    results=results,
                    webhook_url=group["feishu_webhook"],
                    keyword=group.get("feishu_keyword", ""),
                    ai_text=ai_text,
                    report_url=report_url,
                )
            except Exception as exc:
                error_message = str(exc) or repr(exc)
                logger.exception("[group_schedule] 分组 '%s' 飞书推送失败", group_name)
                job_results.append({
                    "group_id": gid,
                    "group_name": group_name,
                    "hosts": len(results),
                    "stage": "delivery",
                    "error": error_message,
                    "push": {"ok": False, "msg": error_message},
                })
                continue
            delivery_error = _delivery_error(res)
            if delivery_error:
                logger.error(
                    "[group_schedule] 分组 '%s' 飞书推送失败: %s",
                    group_name,
                    delivery_error,
                )
                job_results.append({
                    "group_id": gid,
                    "group_name": group_name,
                    "hosts": len(results),
                    "stage": "delivery",
                    "error": delivery_error,
                    "push": res,
                })
                continue
            logger.info("[group_schedule] 分组 '%s' 飞书推送: %s", group_name, res)
            job_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "push": res,
            })
        else:
            job_results.append({
                "group_id": gid,
                "group_name": group_name,
                "hosts": len(results),
                "skipped": True,
                "reason": "未配置飞书 Webhook",
            })

    return job_results


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
        inspect_data = await collect_inspect_data()
        inspect_report = await _build_inspect_report(inspect_data)
        inspect_report_url = build_public_inspect_pdf_url(inspect_report["id"], APP_URL)
        raw_inspect_results = inspect_data["results"]

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
                if not inspect_report_url:
                    logger.warning(
                        "[scheduler] APP_URL 未配置，飞书巡检卡片不附带 PDF 链接"
                    )
                result = await send_feishu(report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url)
                logger.info("[scheduler] 飞书日报推送: %s", result)
                result2 = await send_feishu(
                    inspect_report,
                    FEISHU_WEBHOOK,
                    keyword=FEISHU_KEYWORD,
                    report_url=inspect_report_url,
                )
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
        # repr(exc) 保留异常类型名，避免 asyncio.TimeoutError 等无消息异常显示为空
        _exc_desc = repr(exc) if not str(exc) else f"{type(exc).__name__}: {exc}"
        _err_msg = f"⚠️ 定时报告任务失败：{_exc_desc}"
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
