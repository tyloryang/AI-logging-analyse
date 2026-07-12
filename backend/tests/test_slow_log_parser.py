import unittest

from slow_log_parser import parse_slow_log


SLOW_LOG = """# Time: 2026-07-10T10:00:00.000000Z
# User@Host: app[app] @ localhost [127.0.0.1]  Id: 1
# Query_time: 2.000000  Lock_time: 0.000000 Rows_sent: 1 Rows_examined: 10
SELECT id FROM orders WHERE id = 1;
# Time: 2026-07-10T10:04:30.000000Z
# User@Host: app[app] @ localhost [127.0.0.1]  Id: 2
# Query_time: 3.000000  Lock_time: 0.000000 Rows_sent: 1 Rows_examined: 20
SELECT id FROM orders WHERE id = 2;
# Time: 2026-07-10T10:06:00.000000Z
# User@Host: app[app] @ localhost [127.0.0.1]  Id: 3
# Query_time: 4.000000  Lock_time: 0.000000 Rows_sent: 1 Rows_examined: 30
SELECT id FROM orders WHERE id = 3;
"""


class SlowLogTimeRangeCase(unittest.TestCase):
    def test_datetime_range_filters_to_exact_minutes(self):
        entries = parse_slow_log(
            SLOW_LOG,
            date_from="2026-07-10T10:01:00",
            date_to="2026-07-10T10:05:00",
        )

        self.assertEqual([entry["time_str"] for entry in entries], ["2026-07-10 10:04:30"])

    def test_date_only_range_still_includes_the_whole_day(self):
        entries = parse_slow_log(
            SLOW_LOG,
            date_from="2026-07-10",
            date_to="2026-07-10",
        )

        self.assertEqual(len(entries), 3)


if __name__ == "__main__":
    unittest.main()
