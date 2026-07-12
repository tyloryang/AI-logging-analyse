import unittest
from unittest.mock import patch

from ssh_utils import ssh_connect_options


class SSHConnectOptionsCase(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_verifies_host_keys_by_default(self):
        opts = ssh_connect_options(host="127.0.0.1", username="root")
        self.assertIsNone(opts["config"])
        self.assertNotIn("known_hosts", opts)
        self.assertIsNone(opts["client_keys"])
        self.assertIsNone(opts["agent_path"])
        self.assertEqual(opts["host"], "127.0.0.1")
        self.assertEqual(opts["username"], "root")

    @patch.dict("os.environ", {"SSH_STRICT_HOST_KEY_CHECKING": "0"}, clear=True)
    def test_allows_explicit_host_key_opt_out(self):
        opts = ssh_connect_options()
        self.assertIsNone(opts["known_hosts"])

    @patch.dict(
        "os.environ",
        {"SSH_KNOWN_HOSTS": "C:/secure/known_hosts"},
        clear=True,
    )
    def test_uses_configured_known_hosts_file(self):
        opts = ssh_connect_options()
        self.assertEqual(opts["known_hosts"], "C:/secure/known_hosts")


if __name__ == "__main__":
    unittest.main()
