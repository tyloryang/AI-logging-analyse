import asyncio
import unittest
from types import SimpleNamespace

from services.rca_evidence import (
    build_match_window,
    collect_kubernetes_evidence,
    collect_slowlog_evidence,
    collect_two_stage,
    rank_slowlog_candidates,
)
from services import service_dependencies
from services.service_dependencies import resolve_dependency


class ServiceDependencyResolutionTests(unittest.TestCase):
    def test_runtime_source_wins_and_conflicts_are_preserved(self):
        records = [
            {
                "id": "dep-cmdb",
                "cluster": "z1",
                "namespace": "analyse",
                "service": "analyse",
                "dependency_type": "mysql",
                "target": "mysql-cmdb",
                "source": "cmdb",
            },
            {
                "id": "dep-runtime",
                "cluster": "z1",
                "namespace": "analyse",
                "service": "analyse",
                "dependency_type": "mysql",
                "target": "mysql-runtime",
                "source": "pod_runtime",
            },
        ]

        result = resolve_dependency(
            records,
            cluster="z1",
            namespace="analyse",
            service="analyse",
            dependency_type="mysql",
        )

        self.assertEqual(result["selected"]["id"], "dep-runtime")
        self.assertEqual(result["conflicts"][0]["id"], "dep-cmdb")
        self.assertEqual(result["confidence_penalty"], 10)

    def test_dependency_records_can_be_created_updated_and_deleted(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            service_dependencies,
            "_DATA_FILE",
            Path(tmp) / "dependencies.json",
        ):
            created = service_dependencies.upsert_dependency({
                "cluster": "z1",
                "namespace": "analyse",
                "service": "analyse",
                "dependency_type": "mysql",
                "target": "mysql-analyse",
                "source": "cmdb",
            })
            service_dependencies.upsert_dependency({**created, "slowlog_config_id": "slow-1"})
            loaded = service_dependencies.load_dependencies()
            removed = service_dependencies.delete_dependency(created["id"])

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["slowlog_config_id"], "slow-1")
        self.assertTrue(removed)


class MatchWindowTests(unittest.TestCase):
    def test_trace_window_is_preferred(self):
        result = build_match_window(
            alert_started_at="2026-07-12T10:01:00Z",
            trace_started_at="2026-07-12T10:00:00Z",
            trace_ended_at="2026-07-12T10:00:50Z",
        )

        self.assertEqual(result["source"], "trace")
        self.assertEqual(result["started_at"], "2026-07-12T10:00:00+00:00")
        self.assertEqual(result["ended_at"], "2026-07-12T10:00:50+00:00")
        self.assertFalse(result["confidence_capped"])

    def test_alert_window_falls_back_to_minus_90_plus_30_seconds(self):
        result = build_match_window(alert_started_at="2026-07-12T10:01:00Z")

        self.assertEqual(result["source"], "alert")
        self.assertEqual(result["started_at"], "2026-07-12T09:59:30+00:00")
        self.assertEqual(result["ended_at"], "2026-07-12T10:01:30+00:00")
        self.assertTrue(result["confidence_capped"])


class SlowlogCandidateRankingTests(unittest.TestCase):
    def test_candidates_keep_top_three_with_explainable_score(self):
        dependency = {
            "target": "mysql-analyse",
            "host": "10.0.0.9",
            "db_user": "analyse_user",
            "sql_keywords": ["large_object"],
            "confidence_penalty": 0,
        }
        entries = [
            {
                "id": 1,
                "time_dt": "2026-07-12T10:00:10",
                "user": "analyse_user",
                "host": "10.0.0.9",
                "query_time": 48.0,
                "sql": "select large_object from analyse_payload where id = 1",
            },
            {
                "id": 2,
                "time_dt": "2026-07-12T10:00:20",
                "user": "other",
                "host": "10.0.0.9",
                "query_time": 20.0,
                "sql": "select * from audit_log",
            },
            {
                "id": 3,
                "time_dt": "2026-07-12T10:00:30",
                "user": "other",
                "host": "10.0.0.8",
                "query_time": 5.0,
                "sql": "select * from health_check",
            },
            {
                "id": 4,
                "time_dt": "2026-07-12T09:30:00",
                "user": "analyse_user",
                "host": "10.0.0.9",
                "query_time": 60.0,
                "sql": "select large_object from old_payload",
            },
        ]
        window = build_match_window(
            alert_started_at="2026-07-12T10:01:00Z",
            trace_started_at="2026-07-12T10:00:00Z",
            trace_ended_at="2026-07-12T10:00:50Z",
        )

        ranked = rank_slowlog_candidates(
            entries,
            dependency=dependency,
            match_window=window,
            response_duration_sec=50.0,
        )

        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["entry_id"], 1)
        self.assertEqual(ranked[0]["score"], 100)
        self.assertEqual(ranked[0]["confidence"], "high")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertTrue(any(item["rule"] == "time_overlap" for item in ranked[0]["evidence"]))

    def test_alert_fallback_caps_confidence_at_medium(self):
        ranked = rank_slowlog_candidates(
            [{
                "id": 1,
                "time_dt": "2026-07-12T10:00:10",
                "user": "analyse_user",
                "host": "10.0.0.9",
                "query_time": 48.0,
                "sql": "select large_object from analyse_payload",
            }],
            dependency={
                "target": "mysql-analyse",
                "host": "10.0.0.9",
                "db_user": "analyse_user",
                "sql_keywords": ["large_object"],
            },
            match_window=build_match_window(alert_started_at="2026-07-12T10:01:00Z"),
            response_duration_sec=50.0,
        )

        self.assertGreaterEqual(ranked[0]["score"], 80)
        self.assertEqual(ranked[0]["confidence"], "medium")


class TwoStageCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_facts_are_published_without_waiting_for_slow_collector(self):
        published = []
        release_slow = asyncio.Event()

        async def fast():
            return {"title": "K8s", "summary": "pod restarted"}

        async def slow():
            await release_slow.wait()
            return {"title": "Slowlog", "summary": "candidate ready"}

        def publish(snapshot):
            published.append(snapshot)
            release_slow.set()

        result = await collect_two_stage(
            {"kubernetes": fast, "slowlog": slow},
            facts_deadline_sec=0.02,
            final_deadline_sec=1.0,
            on_facts=publish,
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["collector_states"]["kubernetes"]["status"], "completed")
        self.assertEqual(published[0]["collector_states"]["slowlog"]["status"], "collecting")
        self.assertEqual(result["collector_states"]["slowlog"]["status"], "completed")
        self.assertEqual(result["sections"]["slowlog"]["summary"], "candidate ready")


class EvidenceCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_slowlog_without_dependency_is_explicitly_unconfigured(self):
        result = await collect_slowlog_evidence(
            service="analyse",
            labels={"cluster": "z1", "namespace": "analyse"},
            dependency_records=[],
            slowlog_configs=[],
        )

        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["candidates"], [])
        self.assertIn("依赖", result["summary"])

    async def test_slowlog_collects_ranked_candidates_from_mapped_config(self):
        async def reader(_config, _date_from, _date_to):
            return [{
                "id": 9,
                "time_dt": "2026-07-12T10:00:30",
                "user": "analyse_user",
                "host": "10.0.0.9",
                "query_time": 48.0,
                "sql": "select large_object from analyse_payload",
            }]

        result = await collect_slowlog_evidence(
            service="analyse",
            labels={
                "cluster": "z1",
                "namespace": "analyse",
                "startsAt": "2026-07-12T10:01:00Z",
                "trace_started_at": "2026-07-12T10:00:00Z",
                "trace_ended_at": "2026-07-12T10:00:50Z",
                "request_duration_seconds": "50",
            },
            dependency_records=[{
                "id": "dep-1",
                "cluster": "z1",
                "namespace": "analyse",
                "service": "analyse",
                "dependency_type": "mysql",
                "target": "mysql-analyse",
                "source": "cmdb",
                "slowlog_config_id": "slow-1",
                "source_host": "10.0.0.9",
                "db_user": "analyse_user",
                "sql_keywords": ["large_object"],
            }],
            slowlog_configs=[{"id": "slow-1", "host_ip": "10.0.0.20"}],
            read_entries=reader,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["candidates"][0]["entry_id"], 9)
        self.assertEqual(result["candidates"][0]["confidence"], "high")

    async def test_trace_id_is_resolved_to_request_time_before_slowlog_matching(self):
        trace_end_iso = "2026-07-12T10:00:50+00:00"

        async def trace_loader(trace_id):
            self.assertEqual(trace_id, "trace-1")
            return [
                {"startTime": 1783840800000, "endTime": 1783840840000},
                {"startTime": 1783840805000, "endTime": 1783840850000},
            ]

        async def reader(_config, _date_from, _date_to):
            return [{
                "id": 1,
                "time_dt": trace_end_iso,
                "query_time": 5.0,
                "sql": "select * from analyse_payload",
            }]

        result = await collect_slowlog_evidence(
            service="analyse",
            labels={
                "cluster": "z1",
                "namespace": "analyse",
                "startsAt": "2026-07-12T10:01:00Z",
                "trace_id": "trace-1",
            },
            dependency_records=[{
                "id": "dep-1",
                "cluster": "z1",
                "namespace": "analyse",
                "service": "analyse",
                "dependency_type": "mysql",
                "target": "mysql-analyse",
                "source": "cmdb",
                "slowlog_config_id": "slow-1",
            }],
            slowlog_configs=[{"id": "slow-1", "host_ip": "10.0.0.20"}],
            read_entries=reader,
            trace_loader=trace_loader,
        )

        self.assertEqual(result["match_window"]["source"], "trace")
        self.assertFalse(result["match_window"]["confidence_capped"])
        self.assertFalse(any(item["rule"] == "duration" for item in result["candidates"][0]["evidence"]))

    async def test_kubernetes_collects_pod_restart_metrics_and_events(self):
        pod = SimpleNamespace(
            metadata=SimpleNamespace(
                name="analyse-abc",
                namespace="analyse",
                labels={"app": "analyse"},
                creation_timestamp=None,
            ),
            spec=SimpleNamespace(node_name="node-1"),
            status=SimpleNamespace(
                phase="Running",
                pod_ip="10.1.0.8",
                host_ip="10.0.0.5",
                container_statuses=[SimpleNamespace(
                    name="analyse",
                    restart_count=2,
                    last_state=SimpleNamespace(
                        terminated=SimpleNamespace(reason="OOMKilled", finished_at="2026-07-12T09:58:00Z", exit_code=137)
                    ),
                )],
            ),
        )
        event = SimpleNamespace(
            type="Warning",
            reason="BackOff",
            message="Back-off restarting failed container",
            count=3,
            last_timestamp="2026-07-12T09:58:05Z",
            event_time=None,
            first_timestamp=None,
            series=None,
            reporting_component="kubelet",
            reporting_instance="node-1",
            source=None,
            involved_object=SimpleNamespace(kind="Pod", name="analyse-abc"),
            metadata=SimpleNamespace(namespace="analyse", creation_timestamp=None),
        )

        class Core:
            def list_namespaced_pod(self, namespace, **_kwargs):
                self.namespace = namespace
                return SimpleNamespace(items=[pod])

            def list_namespaced_event(self, namespace, **_kwargs):
                return SimpleNamespace(items=[event])

        result = await collect_kubernetes_evidence(
            service="analyse",
            labels={"cluster": "z1", "namespace": "analyse", "pod": "analyse-abc"},
            load_clusters=lambda: [{"id": "cluster-1", "name": "z1"}],
            get_client=lambda _cluster_id: (Core(), object()),
            metrics_loader=lambda _cluster_id, _namespace: {
                ("analyse", "analyse-abc"): {"cpu_usage_cores": 0.8, "memory_usage_bytes": 536870912}
            },
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pods"][0]["restarts"], 2)
        self.assertEqual(result["pods"][0]["last_restart_reason"], "OOMKilled")
        self.assertEqual(result["pods"][0]["cpu_usage_cores"], 0.8)
        self.assertEqual(result["events"][0]["reason"], "BackOff")


if __name__ == "__main__":
    unittest.main()
