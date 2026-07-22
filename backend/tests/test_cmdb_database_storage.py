import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import state
from services import cmdb_store


class CmdbDatabaseStorageCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_db_path = cmdb_store._DB_PATH
        self.original_paths = {
            "CMDB_FILE": state.CMDB_FILE,
            "CREDENTIALS_FILE": state.CREDENTIALS_FILE,
            "GROUPS_FILE": state.GROUPS_FILE,
            "USER_GROUPS_FILE": state.USER_GROUPS_FILE,
        }
        cmdb_store._DB_PATH = self.root / "cmdb.db"
        cmdb_store._schema_ready = False
        cmdb_store.invalidate_cache()
        state.CMDB_FILE = self.root / "cmdb_hosts.json"
        state.CREDENTIALS_FILE = self.root / "ssh_credentials.json"
        state.GROUPS_FILE = self.root / "groups.json"
        state.USER_GROUPS_FILE = self.root / "user_groups.json"

    def tearDown(self):
        cmdb_store._DB_PATH = self.original_db_path
        cmdb_store._schema_ready = False
        cmdb_store.invalidate_cache()
        for name, path in self.original_paths.items():
            setattr(state, name, path)
        self.temp_dir.cleanup()

    def test_cmdb_saves_all_collections_without_json_files(self):
        hosts = [{"id": "h1", "ip": "10.0.0.1", "hostname": "db-1"}]
        groups = [{"id": "g1", "name": "数据库", "schedule_enabled": False}]
        credentials = [{"id": "c1", "name": "root", "password": "encrypted"}]
        user_groups = {"u1": ["g1"], "u2": []}

        state.save_hosts_list(hosts)
        state.save_groups(groups)
        state.save_credentials(credentials)
        state.save_user_groups(user_groups)

        self.assertEqual(state.load_hosts_list(), hosts)
        self.assertEqual(state.load_groups()[0]["id"], "g1")
        self.assertEqual(state.load_credentials(), credentials)
        self.assertEqual(state.load_user_groups(), user_groups)
        self.assertFalse(state.CMDB_FILE.exists())
        self.assertFalse(state.CREDENTIALS_FILE.exists())
        self.assertFalse(state.GROUPS_FILE.exists())
        self.assertFalse(state.USER_GROUPS_FILE.exists())

    def test_legacy_json_is_imported_once_then_ignored(self):
        legacy = {
            state.CMDB_FILE: [{"id": "h1", "ip": "10.0.0.1", "hostname": "web-1"}],
            state.CREDENTIALS_FILE: [{"id": "c1", "name": "ops", "password": "encrypted"}],
            state.GROUPS_FILE: [{"id": "g1", "name": "生产"}],
            state.USER_GROUPS_FILE: {"u1": ["g1"]},
        }
        for path, payload in legacy.items():
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        state.migrate_cmdb_storage()

        for path in legacy:
            path.write_text("[]" if path != state.USER_GROUPS_FILE else "{}", encoding="utf-8")

        self.assertEqual(state.load_hosts_list()[0]["id"], "h1")
        self.assertEqual(state.load_credentials()[0]["id"], "c1")
        self.assertEqual(state.load_groups()[0]["id"], "g1")
        self.assertEqual(state.load_user_groups(), {"u1": ["g1"]})

    def test_deleted_records_and_empty_assignments_stay_in_database(self):
        state.save_hosts_list([{"id": "h1", "ip": "10.0.0.1"}])
        state.save_groups([{"id": "g1", "name": "生产"}, {"id": "g2", "name": "测试"}])
        state.save_credentials([{"id": "c1", "name": "root"}, {"id": "c2", "name": "ops"}])
        state.save_user_groups({"u1": ["g1"], "u2": []})

        state.save_hosts_list([])
        state.save_groups([{"id": "g2", "name": "测试"}])
        state.save_credentials([{"id": "c1", "name": "root"}])
        cmdb_store.invalidate_cache()

        self.assertEqual(state.load_hosts_list(), [])
        self.assertEqual([group["id"] for group in state.load_groups()], ["g2"])
        self.assertEqual([credential["id"] for credential in state.load_credentials()], ["c1"])
        self.assertEqual(state.load_user_groups(), {"u1": ["g1"], "u2": []})

    def test_legacy_migration_does_not_swallow_database_write_failures(self):
        state.GROUPS_FILE.write_text(
            json.dumps([{"id": "g1", "name": "生产"}], ensure_ascii=False),
            encoding="utf-8",
        )
        state.USER_GROUPS_FILE.write_text(
            json.dumps({"u1": ["g1"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        with patch.object(cmdb_store, "save_groups", side_effect=RuntimeError("db unavailable")):
            with self.assertRaisesRegex(RuntimeError, "db unavailable"):
                state.load_groups()

        with patch.object(cmdb_store, "save_user_groups", side_effect=RuntimeError("db unavailable")):
            with self.assertRaisesRegex(RuntimeError, "db unavailable"):
                state.load_user_groups()

    def test_legacy_source_resolution_does_not_copy_json(self):
        legacy = self.root / "cmdb_hosts.json"
        legacy.write_text("[]", encoding="utf-8")
        data_dir = self.root / "data"
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.object(state, "DATA_DIR", data_dir), patch.dict(
                os.environ, {"CMDB_FILE": ""}, clear=False
            ):
                resolved = state._resolve_legacy_source_path("CMDB_FILE", "cmdb_hosts.json")
                resolved_path = resolved.resolve()
        finally:
            os.chdir(original_cwd)

        self.assertEqual(resolved_path, legacy.resolve())
        self.assertFalse((data_dir / "cmdb_hosts.json").exists())


if __name__ == "__main__":
    unittest.main()
