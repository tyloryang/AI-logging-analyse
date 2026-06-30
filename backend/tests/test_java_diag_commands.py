import unittest

from routers.hosts import (
    _build_arthas_command,
    _build_async_profiler_command,
    _sync_info_to_inspection_result,
)


class JavaDiagnosticCommandTests(unittest.TestCase):
    def test_arthas_command_searches_target_process_env(self):
        command = _build_arthas_command(2605, "jvm")

        self.assertNotIn("\x00", command)
        self.assertIn("tr '\\0' '\\n'", command)
        self.assertIn("proc_path=$(cat /proc/2605/environ", command)
        self.assertIn("/proc/2605/root$jhome/bin/java", command)
        self.assertIn("/proc/2605/root$dir/java", command)
        self.assertIn("PATH from target env", command)

    def test_arthas_command_keeps_custom_quotes_shell_safe(self):
        command = _build_arthas_command(
            2605,
            "ognl '@java.lang.System@getProperty(\"java.version\")'",
        )

        self.assertNotIn("\x00", command)
        self.assertIn("tr '\\0' '\\n'", command)
        self.assertIn("--command 'ognl '", command)

    def test_async_profiler_command_uses_same_java_fallbacks(self):
        command = _build_async_profiler_command(2605, 5, "cpu", "/tmp/flame.html")

        self.assertNotIn("\x00", command)
        self.assertIn("tr '\\0' '\\n'", command)
        self.assertIn("proc_path=$(cat /proc/2605/environ", command)
        self.assertIn("/proc/2605/root$jhome/bin/java", command)
        self.assertIn("/proc/2605/root$dir/java", command)

    def test_ssh_sync_info_maps_to_inspection_result(self):
        result = _sync_info_to_inspection_result(
            {"ip": "10.0.0.8", "hostname": "app-1", "cpu_cores": 4},
            {
                "hostname": "app-1",
                "os_version": "Linux 6.1",
                "cpu_cores": 4,
                "memory_gb": 8,
                "disk_gb": 100,
                "cpu_usage_pct": 12.5,
                "memory_usage_pct": 64.2,
                "load1": 0.4,
                "load5": 0.5,
                "load15": 0.6,
                "network_rx_bps": 1048576,
                "network_tx_bps": 2097152,
                "disk_io_read_bps": 3145728,
                "disk_io_write_bps": 4194304,
                "tcp_connections": 12,
                "tcp_time_wait": 3,
                "disk_usage": [
                    {"mount": "/", "size_gb": 100, "used_gb": 50, "avail_gb": 50, "used_pct": 50},
                ],
            },
        )

        self.assertEqual(result["metrics_source"], "ssh_python")
        self.assertEqual(result["metrics"]["cpu_usage"], 12.5)
        self.assertEqual(result["metrics"]["mem_usage"], 64.2)
        self.assertEqual(result["metrics"]["net_recv_mbps"], 1.0)
        self.assertEqual(result["metrics"]["disk_write_mbps"], 4.0)
        self.assertEqual(result["partitions"][0]["mountpoint"], "/")


if __name__ == "__main__":
    unittest.main()
