import unittest
from unittest.mock import patch

from routers.rca import (
    ServiceDependencyRequest,
    list_service_dependencies,
    remove_service_dependency,
    upsert_service_dependency,
)


class RCAServiceDependencyRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_dependency_crud_contract(self):
        body = ServiceDependencyRequest(
            cluster="z1",
            namespace="analyse",
            service="analyse",
            dependency_type="mysql",
            target="mysql-analyse",
            source="cmdb",
            slowlog_config_id="slow-1",
        )
        created = {**body.model_dump(), "id": "dep-1"}

        with (
            patch("services.service_dependencies.load_dependencies", return_value=[created]),
            patch("services.service_dependencies.upsert_dependency", return_value=created),
            patch("services.service_dependencies.delete_dependency", return_value=True),
        ):
            listed = await list_service_dependencies()
            saved = await upsert_service_dependency(body)
            removed = await remove_service_dependency("dep-1")

        self.assertEqual(listed["data"][0]["id"], "dep-1")
        self.assertEqual(saved["data"]["slowlog_config_id"], "slow-1")
        self.assertTrue(removed["ok"])


if __name__ == "__main__":
    unittest.main()
