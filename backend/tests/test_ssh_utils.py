import unittest

from ssh_utils import ssh_connect_options


class SSHConnectOptionsCase(unittest.TestCase):
    def test_disables_local_ssh_config_by_default(self):
        opts = ssh_connect_options(host="127.0.0.1", username="root")
        self.assertIsNone(opts["config"])
        self.assertIsNone(opts["known_hosts"])
        self.assertIsNone(opts["client_keys"])
        self.assertIsNone(opts["agent_path"])
        self.assertEqual(opts["host"], "127.0.0.1")
        self.assertEqual(opts["username"], "root")


if __name__ == "__main__":
    unittest.main()
