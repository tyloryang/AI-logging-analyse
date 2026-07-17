import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import scheduler
from routers import reports


async def _empty_summary_stream(results, summary):
    if False:
        yield ""


async def _one_chunk_report_stream(results, summary):
    yield "运行正常。"


class SchedulerInspectNotificationLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_schedule_passes_saved_inspect_pdf_url(self):
        daily = {"id": "daily_1", "type": "daily"}
        inspect = {"id": "inspect_1", "type": "inspect"}
        send_feishu = AsyncMock(return_value={"ok": True})
        with (
            patch.object(scheduler, "SCHEDULE_CHANNELS", ["feishu"]),
            patch.object(scheduler, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(scheduler, "_build_and_save_report", AsyncMock(return_value=daily)),
            patch.object(
                scheduler,
                "collect_inspect_data",
                AsyncMock(return_value={"results": []}),
            ),
            patch.object(scheduler, "_build_inspect_report", AsyncMock(return_value=inspect)),
            patch.object(scheduler, "_build_slowlog_report", AsyncMock(return_value=None)),
            patch.object(scheduler, "send_feishu", send_feishu),
            patch.object(
                scheduler,
                "_send_group_inspect_notifications",
                AsyncMock(return_value=[]),
            ),
            patch("state.REPORT_RETENTION_DAYS", 0),
        ):
            await scheduler.scheduled_report_job()

        self.assertEqual(len(send_feishu.await_args_list), 2)
        self.assertEqual(
            send_feishu.await_args_list[1].kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_1.pdf",
        )

    async def test_dingtalk_only_schedule_does_not_warn_about_feishu_pdf(self):
        send_dingtalk = AsyncMock(return_value={"ok": True})
        with (
            patch.object(scheduler, "SCHEDULE_CHANNELS", ["dingtalk"]),
            patch.object(scheduler, "DINGTALK_WEBHOOK", "https://dingtalk.example/hook"),
            patch.object(scheduler, "APP_URL", ""),
            patch.object(
                scheduler,
                "_build_and_save_report",
                AsyncMock(return_value={"id": "daily_1", "type": "daily"}),
            ),
            patch.object(
                scheduler,
                "collect_inspect_data",
                AsyncMock(return_value={"results": []}),
            ),
            patch.object(
                scheduler,
                "_build_inspect_report",
                AsyncMock(return_value={"id": "inspect_1", "type": "inspect"}),
            ),
            patch.object(scheduler, "_build_slowlog_report", AsyncMock(return_value=None)),
            patch.object(scheduler, "send_dingtalk", send_dingtalk),
            patch.object(
                scheduler,
                "_send_group_inspect_notifications",
                AsyncMock(return_value=[]),
            ),
            patch("state.REPORT_RETENTION_DAYS", 0),
        ):
            with self.assertNoLogs(scheduler.logger, level="WARNING"):
                await scheduler.scheduled_report_job()

        self.assertEqual(len(send_dingtalk.await_args_list), 2)

    async def test_group_notification_saves_before_sending_link(self):
        events = []

        async def save_report(results, group_id, group_name, ai_text):
            events.append("saved")
            self.assertEqual(group_id, "grp-1")
            self.assertEqual(group_name, "核心组")
            return {"id": "inspect_1_grp-1", "type": "inspect"}

        async def send_group(**kwargs):
            events.append("sent")
            self.assertEqual(
                kwargs["report_url"],
                "https://aiops.example/api/public/report/inspect/inspect_1_grp-1.pdf",
            )
            return {"ok": True}

        result = [{"group": "grp-1", "overall": "normal", "checks": []}]
        with (
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(
                scheduler,
                "load_groups",
                return_value=[{
                    "id": "grp-1",
                    "name": "核心组",
                    "schedule_enabled": True,
                    "feishu_webhook": "https://feishu.example/hook",
                }],
            ),
            patch.object(scheduler, "load_hosts_list", return_value=[]),
            patch.object(
                scheduler.analyzer,
                "generate_inspection_summary",
                _empty_summary_stream,
            ),
            patch.object(scheduler, "save_group_inspect_report", save_report, create=True),
            patch.object(scheduler, "send_feishu_group_inspect", send_group),
        ):
            await scheduler._send_group_inspect_notifications(result)

        self.assertEqual(events, ["saved", "sent"])

    async def test_per_group_schedule_saves_and_links_group_report(self):
        events = []
        results = [{"group": "grp-1", "overall": "normal", "checks": []}]
        inspect_data = {
            "results": results,
            "summary": {"total": 1, "normal": 1, "warning": 0, "critical": 0},
        }

        async def save_report(**kwargs):
            events.append("saved")
            return {"id": "inspect_1_grp-1", "type": "inspect"}

        async def send_group(**kwargs):
            events.append("sent")
            self.assertEqual(
                kwargs["report_url"],
                "https://aiops.example/api/public/report/inspect/inspect_1_grp-1.pdf",
            )
            return {"ok": True}

        with (
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(
                scheduler,
                "load_groups",
                return_value=[{
                    "id": "grp-1",
                    "name": "核心组",
                    "schedule_enabled": True,
                    "schedule_time": datetime.now().strftime("%H:%M"),
                    "feishu_webhook": "https://feishu.example/hook",
                }],
            ),
            patch.object(
                scheduler,
                "load_hosts_list",
                return_value=[{"ip": "10.0.0.8", "group": "grp-1"}],
            ),
            patch.object(
                scheduler,
                "collect_inspect_data",
                AsyncMock(return_value=inspect_data),
            ),
            patch.object(
                scheduler.analyzer,
                "generate_inspection_summary",
                _empty_summary_stream,
            ),
            patch.object(scheduler, "save_group_inspect_report", save_report, create=True),
            patch.object(scheduler, "send_feishu_group_inspect", send_group),
        ):
            await scheduler.run_group_schedule_job()

        self.assertEqual(events, ["saved", "sent"])


class ReportRouterInspectNotificationLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_inspect_push_uses_public_pdf_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_1.json").write_text(
                json.dumps({
                    "id": "inspect_1",
                    "type": "inspect",
                    "host_summary": {},
                }),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(reports, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report(
                    "inspect_1", reports.NotifyRequest(channels=["feishu"])
                )

        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_1.pdf",
        )

    async def test_manual_non_inspect_push_keeps_existing_ui_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "daily_1.json").write_text(
                json.dumps({"id": "daily_1", "type": "daily"}),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(reports, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report(
                    "daily_1", reports.NotifyRequest(channels=["feishu"])
                )

        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/report/daily_1",
        )

    async def test_manual_dingtalk_push_remains_unchanged(self):
        report = {"id": "inspect_1", "type": "inspect"}
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_1.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", ""),
                patch.object(reports, "DINGTALK_WEBHOOK", "https://dingtalk.example/hook"),
                patch.object(reports, "send_dingtalk", sender),
            ):
                with self.assertNoLogs(reports.logger, level="WARNING"):
                    await reports.notify_report(
                        "inspect_1", reports.NotifyRequest(channels=["dingtalk"])
                    )

        sender.assert_awaited_once_with(
            report,
            "https://dingtalk.example/hook",
            keyword=reports.DINGTALK_KEYWORD,
        )

    async def test_manual_group_non_inspect_push_keeps_existing_ui_link(self):
        report = {"id": "daily_1", "type": "daily"}
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "daily_1.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(
                    reports,
                    "load_groups",
                    return_value=[{
                        "id": "grp-1",
                        "name": "核心组",
                        "feishu_webhook": "https://feishu.example/hook",
                    }],
                ),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report_groups("daily_1", group_id="grp-1")

        self.assertEqual(sender.await_args.args[0], report)
        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/report/daily_1",
        )

    async def test_empty_app_url_still_sends_card_without_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_1.json").write_text(
                json.dumps({"id": "inspect_1", "type": "inspect", "host_summary": {}}),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", ""),
                patch.object(reports, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
                patch.object(reports, "send_feishu", sender),
            ):
                with self.assertLogs(reports.logger, level="WARNING") as logs:
                    await reports.notify_report(
                        "inspect_1", reports.NotifyRequest(channels=["feishu"])
                    )

        sender.assert_awaited_once()
        self.assertEqual(sender.await_args.kwargs["report_url"], "")
        self.assertTrue(any("APP_URL" in message for message in logs.output))

    async def test_empty_app_url_still_sends_group_card_without_link(self):
        group_report = {
            "id": "inspect_group",
            "type": "inspect",
            "group_id": "grp-1",
            "all_hosts": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_group.json").write_text(
                json.dumps(group_report),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", ""),
                patch.object(
                    reports,
                    "load_groups",
                    return_value=[{
                        "id": "grp-1",
                        "name": "核心组",
                        "feishu_webhook": "https://feishu.example/hook",
                    }],
                ),
                patch.object(reports, "send_feishu", sender),
            ):
                with self.assertLogs(reports.logger, level="WARNING") as logs:
                    await reports.notify_report_groups(
                        "inspect_group", group_id="grp-1"
                    )

        sender.assert_awaited_once()
        self.assertEqual(sender.await_args.kwargs["report_url"], "")
        self.assertTrue(any("APP_URL" in message for message in logs.output))

    async def test_cached_generated_group_push_uses_cached_report_id(self):
        sender = AsyncMock(return_value={"ok": True})
        cached = {
            "id": "inspect_cached_grp-1",
            "type": "inspect",
            "group_id": "grp-1",
            "all_hosts": [{"overall": "normal", "checks": []}],
            "ai_analysis": "运行正常。",
        }
        with (
            patch.object(reports, "APP_URL", "https://aiops.example"),
            patch.object(
                reports,
                "load_groups",
                return_value=[{
                    "id": "grp-1",
                    "name": "核心组",
                    "feishu_webhook": "https://feishu.example/hook",
                }],
            ),
            patch.object(
                reports,
                "load_cmdb",
                return_value={"10.0.0.8:9100": {"group": "grp-1"}},
            ),
            patch.object(reports, "_find_latest_group_inspect_report", return_value=cached),
            patch.object(reports, "send_feishu_group_inspect", sender),
        ):
            await reports.generate_inspect_report_all_groups()

        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_cached_grp-1.pdf",
        )

    async def test_new_generated_group_push_saves_before_sending_link(self):
        events = []
        full_results = [{
            "group": "grp-1",
            "group_name": "核心组",
            "overall": "normal",
            "checks": [],
        }]
        inspect_data = {
            "results": full_results,
            "summary": {"total": 1, "normal": 1, "warning": 0, "critical": 0},
            "top_issues": [],
            "abnormal_hosts": [],
            "health_score": 100,
        }

        async def save_report(**kwargs):
            events.append("saved")
            self.assertIs(kwargs["results"], full_results)
            self.assertEqual(kwargs["group_id"], "grp-1")
            self.assertEqual(kwargs["group_name"], "核心组")
            self.assertEqual(kwargs["ai_text"], "运行正常。")
            return {"id": "inspect_saved_grp-1", "type": "inspect"}

        async def send_group(*args, **kwargs):
            events.append("sent")
            self.assertEqual(
                kwargs["report_url"],
                "https://aiops.example/api/public/report/inspect/inspect_saved_grp-1.pdf",
            )
            return {"ok": True}

        with (
            patch.object(reports, "APP_URL", "https://aiops.example"),
            patch.object(
                reports,
                "load_groups",
                return_value=[{
                    "id": "grp-1",
                    "name": "核心组",
                    "feishu_webhook": "https://feishu.example/hook",
                }],
            ),
            patch.object(
                reports,
                "load_cmdb",
                return_value={"10.0.0.8:9100": {"group": "grp-1"}},
            ),
            patch.object(reports, "_find_latest_group_inspect_report", return_value=None),
            patch.object(
                reports,
                "collect_inspect_data",
                AsyncMock(return_value=inspect_data),
            ),
            patch.object(
                reports.analyzer,
                "generate_host_inspect_report",
                _one_chunk_report_stream,
            ),
            patch.object(reports, "save_group_inspect_report", save_report, create=True),
            patch.object(reports, "send_feishu_group_inspect", send_group),
        ):
            await reports.generate_inspect_report_all_groups()

        self.assertEqual(events, ["saved", "sent"])

    async def test_manual_group_push_saves_and_sends_group_specific_report(self):
        full_report = {
            "id": "inspect_all",
            "type": "inspect",
            "group_id": "",
            "created_at": "2026-07-17T01:01:01+00:00",
            "all_hosts": [{
                "ip": "10.0.0.8",
                "group": "grp-1",
                "group_name": "核心组",
                "overall": "normal",
                "checks": [],
            }],
            "group_analyses": [{
                "group_id": "grp-1",
                "group_name": "核心组",
                "ai_analysis": "运行正常。",
            }],
        }
        delivery_report = {
            "id": "inspect_group",
            "type": "inspect",
            "group_id": "grp-1",
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_all.json").write_text(
                json.dumps(full_report, ensure_ascii=False),
                encoding="utf-8",
            )
            save_group = AsyncMock(return_value=delivery_report)
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(
                    reports,
                    "load_groups",
                    return_value=[{
                        "id": "grp-1",
                        "name": "核心组",
                        "feishu_webhook": "https://feishu.example/hook",
                    }],
                ),
                patch.object(
                    reports,
                    "load_cmdb",
                    return_value={"10.0.0.8": {"group": "grp-1"}},
                ),
                patch.object(
                    reports,
                    "save_group_inspect_report",
                    save_group,
                    create=True,
                ),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report_groups("inspect_all", group_id="grp-1")

        save_group.assert_awaited_once()
        save_kwargs = save_group.await_args.kwargs
        self.assertEqual(save_kwargs["group_id"], "grp-1")
        self.assertEqual(save_kwargs["group_name"], "核心组")
        self.assertEqual(save_kwargs["ai_text"], "运行正常。")
        self.assertEqual(save_kwargs["results"][0]["ip"], "10.0.0.8")
        self.assertIs(sender.await_args.args[0], delivery_report)
        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_group.pdf",
        )

    async def test_manual_group_push_reuses_original_group_specific_report(self):
        group_report = {
            "id": "inspect_existing_group",
            "type": "inspect",
            "group_id": "grp-1",
            "group_name": "核心组",
            "all_hosts": [{
                "group": "grp-1",
                "overall": "normal",
                "checks": [],
            }],
            "ai_analysis": "运行正常。",
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_existing_group.json").write_text(
                json.dumps(group_report, ensure_ascii=False),
                encoding="utf-8",
            )
            save_group = AsyncMock()
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(
                    reports,
                    "load_groups",
                    return_value=[{
                        "id": "grp-1",
                        "name": "核心组",
                        "feishu_webhook": "https://feishu.example/hook",
                    }],
                ),
                patch.object(
                    reports,
                    "save_group_inspect_report",
                    save_group,
                    create=True,
                ),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report_groups(
                    "inspect_existing_group", group_id="grp-1"
                )

        save_group.assert_not_awaited()
        self.assertEqual(sender.await_args.args[0]["id"], "inspect_existing_group")
        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_existing_group.pdf",
        )


if __name__ == "__main__":
    unittest.main()
