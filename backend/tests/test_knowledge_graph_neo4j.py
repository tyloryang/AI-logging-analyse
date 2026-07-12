import asyncio
import os
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from services import knowledge_graph as kg


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakeDriver:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])
        self.verified = False

    def verify_connectivity(self):
        self.verified = True

    def execute_query(self, cypher, **kwargs):
        self.calls.append((cypher, kwargs))
        records = self.responses.pop(0) if self.responses else []
        return records, None, []


def fake_driver_context(driver):
    @contextmanager
    def fake_context():
        yield driver, {
            "configured": True,
            "uri": "neo4j://test",
            "username": "neo4j",
            "password": "secret",
            "database": "neo4j",
        }

    return fake_context


class KnowledgeGraphNeo4jTests(unittest.TestCase):
    def test_regular_build_skips_optional_neo4j(self):
        with (
            patch.object(kg, "_build_from_cmdb", return_value={}),
            patch.object(kg, "_build_from_k8s"),
            patch.object(kg, "_build_from_skywalking", new=AsyncMock()),
            patch.object(kg, "_persist_graph"),
            patch.object(kg, "_persist_neo4j") as persist_neo4j,
            patch.object(kg, "_neo4j_settings", return_value={"configured": True}),
        ):
            result = asyncio.run(kg.build_graph())

        persist_neo4j.assert_not_called()
        self.assertFalse(result["neo4j"]["synced"])
        self.assertIn("optional backend", result["neo4j"]["skipped"])

    def test_explicit_neo4j_sync_failure_does_not_fail_build(self):
        with (
            patch.object(kg, "_build_from_cmdb", return_value={}),
            patch.object(kg, "_build_from_k8s"),
            patch.object(kg, "_build_from_skywalking", new=AsyncMock()),
            patch.object(kg, "_persist_graph"),
            patch.object(kg, "_persist_neo4j", side_effect=RuntimeError("neo4j unavailable")),
            patch.object(kg, "_neo4j_settings", return_value={"configured": True}),
        ):
            result = asyncio.run(kg.build_graph(sync_neo4j=True))

        self.assertEqual(result["nodes"], 0)
        self.assertFalse(result["neo4j"]["synced"])
        self.assertIn("neo4j unavailable", result["neo4j"]["error"])

    def test_execute_records_accepts_query_parameter(self):
        driver = FakeDriver(responses=[[FakeRecord(value="orders")]])

        records = kg._execute_records(
            driver,
            "RETURN $query AS value",
            database="neo4j",
            query="orders",
        )

        self.assertEqual(records[0]["value"], "orders")
        self.assertEqual(driver.calls[0][1]["query"], "orders")

    def test_graph_snapshot_reports_unconfigured(self):
        with patch.dict(os.environ, {"NEO4J_URI": ""}):
            result = kg.graph_snapshot(limit=10)

        self.assertFalse(result["configured"])
        self.assertFalse(result["connected"])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])

    def test_neighbors_falls_back_to_sqlite_when_neo4j_fails(self):
        sqlite_result = {
            "found": True,
            "center": {"id": "service:orders"},
            "relations": [],
            "nodes": {},
        }
        with (
            patch.object(kg, "_neo4j_settings", return_value={"configured": True}),
            patch.object(kg, "_neo4j_neighbors", side_effect=RuntimeError("neo4j unavailable")),
            patch.object(kg, "_sqlite_neighbors", return_value=sqlite_result),
        ):
            result = kg.neighbors("orders", prefer_neo4j=True)

        self.assertEqual(result["source"], "sqlite-fallback")
        self.assertEqual(result["center"]["id"], "service:orders")
        self.assertIn("neo4j unavailable", result["neo4j_error"])

    def test_neighbors_uses_sqlite_by_default(self):
        sqlite_result = {"found": False, "query": "orders"}
        with (
            patch.object(kg, "_neo4j_settings", return_value={"configured": True}),
            patch.object(kg, "_neo4j_neighbors", side_effect=AssertionError("must not call Neo4j")),
            patch.object(kg, "_sqlite_neighbors", return_value=sqlite_result),
        ):
            result = kg.neighbors("orders")

        self.assertEqual(result["source"], "sqlite")

    def test_persist_neo4j_uses_parameterized_rows(self):
        driver = FakeDriver()
        graph = kg._GraphBuilder()
        source = graph.node("service", "orders", env="prod", owner="team-a")
        target = graph.node("service", "payments", env="prod")
        graph.edge(source, target, "CALLS", protocol="http")

        with patch.object(kg, "_neo4j_driver", fake_driver_context(driver)):
            result = kg._persist_neo4j(graph)

        self.assertTrue(result["synced"])
        self.assertEqual(result["nodes"], 2)
        self.assertEqual(result["edges"], 1)
        self.assertTrue(driver.verified)
        self.assertEqual(len(driver.calls), 6)
        node_query, node_kwargs = driver.calls[2]
        edge_query, edge_kwargs = driver.calls[5]
        self.assertIn("UNWIND $rows", node_query)
        self.assertTrue(node_kwargs["rows"][0]["id"].startswith("service:"))
        self.assertIn("RELATES_TO", edge_query)
        self.assertEqual(edge_kwargs["rows"][0]["relation"], "CALLS")
        self.assertIn("source: 'manual'", driver.calls[3][0])

    def test_graph_snapshot_normalizes_nodes_and_relations(self):
        driver = FakeDriver(responses=[
            [
                FakeRecord(entity={
                    "id": "service:orders",
                    "kind": "service",
                    "name": "orders",
                    "env": "prod",
                    "source": "sxdevops",
                    "props_json": '{"owner": "team-a"}',
                }),
                FakeRecord(entity={
                    "id": "service:payments",
                    "kind": "service",
                    "name": "payments",
                    "source": "manual",
                    "props_json": "{}",
                }),
            ],
            [
                FakeRecord(
                    source="service:orders",
                    target="service:payments",
                    relation="CALLS",
                    props_json='{"protocol": "http"}',
                    source_type="manual",
                )
            ],
        ])

        with (
            patch.dict(os.environ, {"NEO4J_URI": "neo4j://test"}),
            patch.object(kg, "_neo4j_driver", fake_driver_context(driver)),
        ):
            result = kg.graph_snapshot(limit=10)

        self.assertTrue(result["connected"])
        self.assertEqual(result["stats"], {"nodes": 2, "edges": 1, "by_kind": {"service": 2}})
        self.assertEqual(result["nodes"][0]["props"], {"owner": "team-a"})
        self.assertEqual(result["edges"][0]["relation"], "CALLS")
        self.assertEqual(result["edges"][0]["props"], {"protocol": "http"})


if __name__ == "__main__":
    unittest.main()
