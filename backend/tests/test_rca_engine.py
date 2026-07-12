import subprocess
import unittest
from unittest.mock import AsyncMock, patch

from services.rca_engine import _rg_code_hits, _run_git_command, analyze_stream


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


if __name__ == "__main__":
    unittest.main()
