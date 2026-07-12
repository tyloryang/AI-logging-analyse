import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from services import rca_engine
from services.rca_engine import (
    _rg_code_hits,
    _run_git_command,
    _slowlog_hypotheses,
    _notify_rca_completion,
    analyze_stream,
)


class RCAEngineSubprocessOutputCase(unittest.TestCase):
    @patch("services.rca_engine.shutil.which", return_value="rg")
    @patch("services.rca_engine.subprocess.run")
    def test_code_search_tolerates_none_stdout(self, run_mock, _which_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=["rg"],
            returncode=1,
            stdout=None,
            stderr=None,
        )

        self.assertEqual(_rg_code_hits(["checkout-service"]), [])

    @patch("services.rca_engine.subprocess.run")
    def test_git_context_tolerates_none_stdout(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=None,
            stderr=None,
        )

        self.assertEqual(_run_git_command(["log", "--oneline", "-n", "1"]), [])


class RCAEngineStreamCase(unittest.IsolatedAsyncioTestCase):
    async def test_compatibility_stream_tolerates_none_result(self):
        with (
            patch("services.rca_engine.run_rca", new=AsyncMock(return_value="rca-test")),
            patch("services.rca_engine.get_rca", return_value={"result": None}),
        ):
            chunks = [chunk async for chunk in analyze_stream(service="checkout-service")]

        self.assertEqual(chunks, [])


class RCAEngineSlowlogHypothesisCase(unittest.TestCase):
    def test_slowlog_candidates_become_ranked_root_cause_hypotheses(self):
        hypotheses = _slowlog_hypotheses({
            "slowlog": {
                "candidates": [{
                    "rank": 1,
                    "score": 90,
                    "confidence": "high",
                    "query_time": 48.0,
                    "sql_fingerprint": "select large_object from analyse_payload",
                    "evidence": [
                        {"rule": "time_overlap", "score": 25, "detail": "时间重叠"},
                        {"rule": "db_user", "score": 10, "detail": "用户匹配"},
                    ],
                }],
            },
        })

        self.assertEqual(hypotheses[0]["rank"], 1)
        self.assertEqual(hypotheses[0]["score"], 90)
        self.assertEqual(hypotheses[0]["confidence"], "high")
        self.assertIn("48", hypotheses[0]["title"])
        self.assertEqual(hypotheses[0]["validation_status"], "supported")


class RCAEngineTwoStagePersistenceCase(unittest.IsolatedAsyncioTestCase):
    async def test_run_persists_facts_before_final_hypotheses(self):
        async def fake_collect_context(**kwargs):
            await kwargs["on_facts"]({
                "phase": "facts_ready",
                "facts_ready_ms": 120,
                "sections": {
                    "kubernetes": {"title": "K8s", "summary": "Pod restarted", "items": []},
                },
                "collector_states": {
                    "kubernetes": {"status": "completed", "latency_ms": 100, "error": ""},
                    "slowlog": {"status": "collecting", "latency_ms": None, "error": ""},
                },
            })
            return {
                "kubernetes": {"title": "K8s", "summary": "Pod restarted", "items": []},
                "slowlog": {"title": "Slowlog", "summary": "not configured", "items": [], "status": "unconfigured"},
                "_collection": {
                    "collector_states": {
                        "kubernetes": {"status": "completed", "latency_ms": 100, "error": ""},
                        "slowlog": {"status": "unconfigured", "latency_ms": 150, "error": ""},
                    },
                    "facts_ready_ms": 120,
                    "evidence_ready_ms": 150,
                },
            }

        hypotheses = [{
            "id": "hyp_1",
            "rank": 1,
            "agent_name": "Validator-1",
            "category": "resource_bottleneck",
            "title": "Pod restart",
            "description": "Pod restart",
            "score": 70,
            "validation_status": "possible",
            "validation_summary": "Pod restarted",
            "evidence": ["restart=2"],
            "commands": [],
        }]

        with tempfile.TemporaryDirectory() as tmp, \
            patch.object(rca_engine, "_RCA_FILE", Path(tmp) / "rca.json"), \
            patch.object(rca_engine, "collect_context", side_effect=fake_collect_context), \
            patch.object(rca_engine, "_generate_hypotheses", new=AsyncMock(return_value=hypotheses)), \
            patch.object(rca_engine, "_record_rca_event"):
            rca_id = await rca_engine.run_rca(
                service="analyse",
                alert_name="InterfaceSlow",
                source_type="alert",
                source_labels={"cluster": "z1", "namespace": "analyse"},
            )
            record = rca_engine.get_rca(rca_id)

        self.assertEqual(record["phase"], "analysis_ready")
        self.assertEqual(record["sla"]["facts_ready_ms"], 120)
        self.assertEqual(record["collector_states"]["slowlog"]["status"], "unconfigured")
        self.assertTrue(any(item["stage"] == "facts_ready" for item in record["timeline"]))

    async def test_completion_notification_routes_top_candidate_to_matching_group(self):
        sender = AsyncMock(return_value={"ok": True})
        record = {
            "id": "rca-1",
            "alert_group_id": "group-1",
            "service": "analyse",
            "hypotheses": [{"title": "slow sql", "confidence": "high", "score": 90}],
        }

        with patch.dict("os.environ", {"AIOPS_PUBLIC_URL": "https://aiops.example"}, clear=False):
            await _notify_rca_completion(
                record,
                group_loader=lambda _group_id: {"id": "group-1"},
                target_resolver=lambda _group: [{
                    "webhook_url": "https://feishu.example/hook",
                    "keyword": "AIOps",
                    "group_name": "ops",
                }],
                sender=sender,
            )

        sender.assert_awaited_once()
        self.assertIn("rca_id=rca-1", sender.await_args.kwargs["report_url"])
        self.assertEqual(sender.await_args.kwargs["target_name"], "ops")


if __name__ == "__main__":
    unittest.main()
