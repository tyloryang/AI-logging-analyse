import unittest

from routers.hosts import _build_arthas_command, _build_async_profiler_command


class JavaDiagnosticCommandTests(unittest.TestCase):
    def test_arthas_command_searches_target_process_env(self):
        command = _build_arthas_command(2605, "jvm")

        self.assertIn("proc_path=$(cat /proc/2605/environ", command)
        self.assertIn("/proc/2605/root$jhome/bin/java", command)
        self.assertIn("/proc/2605/root$dir/java", command)
        self.assertIn("PATH from target env", command)

    def test_async_profiler_command_uses_same_java_fallbacks(self):
        command = _build_async_profiler_command(2605, 5, "cpu", "/tmp/flame.html")

        self.assertIn("proc_path=$(cat /proc/2605/environ", command)
        self.assertIn("/proc/2605/root$jhome/bin/java", command)
        self.assertIn("/proc/2605/root$dir/java", command)


if __name__ == "__main__":
    unittest.main()
