"""Regression tests for importing a complete pasted kubeconfig."""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from services.kubeconfig_import import KubeconfigImportError, parse_and_store_kubeconfig


SAMPLE_KUBECONFIG = """\
apiVersion: v1
kind: Config
clusters:
- name: demo-cluster
  cluster:
    certificate-authority-data: ZmFrZS1jYQ==
    server: https://10.0.0.10:6443
contexts:
- name: demo-admin@demo-cluster
  context:
    cluster: demo-cluster
    namespace: demo
    user: demo-admin
current-context: demo-admin@demo-cluster
preferences: {}
users:
- name: demo-admin
  user:
    token: fake-token-for-regression-test
"""


class KubeconfigTextImportCase(unittest.TestCase):
    def test_import_derives_name_context_and_namespace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = parse_and_store_kubeconfig(SAMPLE_KUBECONFIG, "", Path(tmpdir))

            self.assertEqual(result["suggested_name"], "demo-cluster")
            self.assertEqual(result["current_context"], "demo-admin@demo-cluster")
            self.assertEqual(result["namespace"], "demo")
            self.assertEqual(result["server"], "https://10.0.0.10:6443")

            saved = Path(result["path"])
            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_text(encoding="utf-8"), SAMPLE_KUBECONFIG.strip())
            self.assertRegex(saved.name, r"^demo-cluster-[0-9a-f]{10}\.yaml$")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)

    def test_import_rejects_non_kubeconfig_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(KubeconfigImportError) as raised:
                parse_and_store_kubeconfig("apiVersion: v1\nkind: Config\n", "", Path(tmpdir))

            self.assertIn("clusters / contexts / users", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
