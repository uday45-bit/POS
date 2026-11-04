import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.periods import current_period, dot_date, period_label, previous_month_period


class TestPeriods(unittest.TestCase):
    def test_current_period_is_first_of_month_to_report_date(self):
        s, e = current_period(dt.date(2026, 10, 25))
        self.assertEqual((s, e), (dt.date(2026, 10, 1), dt.date(2026, 10, 25)))

    def test_report_date_on_the_first(self):
        s, e = current_period(dt.date(2026, 11, 1))
        self.assertEqual(s, e)

    def test_previous_month_period(self):
        self.assertEqual(previous_month_period(dt.date(2026, 10, 25)), (dt.date(2026, 9, 1), dt.date(2026, 9, 30)))

    def test_previous_month_across_year_boundary(self):
        self.assertEqual(previous_month_period(dt.date(2027, 1, 15)), (dt.date(2026, 12, 1), dt.date(2026, 12, 31)))

    def test_previous_month_handles_february(self):
        self.assertEqual(previous_month_period(dt.date(2027, 3, 5)), (dt.date(2027, 2, 1), dt.date(2027, 2, 28)))

    def test_labels_use_dd_mm_yyyy_with_dots(self):
        self.assertEqual(dot_date(dt.date(2026, 10, 5)), "05.10.2026")
        self.assertEqual(period_label(dt.date(2026, 10, 1), dt.date(2026, 10, 25)), "01.10.2026 to 25.10.2026")


if __name__ == "__main__":
    unittest.main()
