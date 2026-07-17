import unittest

from reportlab.platypus.doctemplate import LayoutError

from services.report_pdf import build_report_pdf


class InspectReportPdfTests(unittest.TestCase):
    def test_long_host_row_is_split_across_pages(self):
        hosts = []
        for index in range(25):
            process_name = (
                "process_" + "x" * 100 if index == 0 else "normal_process"
            )
            hosts.append({
                "overall": "normal",
                "ip": f"10.0.0.{index + 1}",
                "role": "Linux",
                "hostname": f"host-{index + 1}",
                "cpu_pct": 10,
                "mem_pct": 20,
                "partitions": [{
                    "mountpoint": "/",
                    "usage_pct": 40,
                    "used_gb": 40,
                    "total_gb": 100,
                }],
                "process_top10": [
                    {"service": process_name, "cpu": rank, "mem": rank}
                    for rank in range(10)
                ],
                "owner": "ops",
                "datacenter": "dc1",
            })

        report = {
            "type": "inspect",
            "title": "Long inspection row pagination test",
            "health_score": 90,
            "ai_analysis": "Overall operation is normal.",
            "host_summary": {
                "total": 25,
                "normal": 25,
                "warning": 0,
                "critical": 0,
            },
            "group_sections": [{"group_name": "Test group", "hosts": hosts}],
        }

        try:
            pdf = build_report_pdf(report)
        except LayoutError as exc:
            self.fail(
                "An oversized host row should split across pages instead of "
                f"failing PDF export: {exc}"
            )

        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
