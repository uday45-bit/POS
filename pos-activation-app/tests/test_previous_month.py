import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.previous_month import (
    baseline_from_consolidation, baseline_from_typed, load_baseline, resolve_for_report, save_baseline,
)

SEPT = (dt.date(2026, 9, 1), dt.date(2026, 9, 30))


def typed(pct=50.0):
    return {k: pct for k in config.DIVISIONS + ["Total"]}


class TestBaseline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "prev.json"

    def test_typed_baseline_round_trip(self):
        t = typed(); t["Medak"] = 12.20
        save_baseline(baseline_from_typed(t, *SEPT), self.tmp)
        b, problem = load_baseline(self.tmp)
        self.assertIsNone(problem)
        self.assertAlmostEqual(b["activation_pct"]["Medak"], 0.1220)
        self.assertEqual(b["_start"], SEPT[0])

    def test_typed_percentage_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            baseline_from_typed(typed(150), *SEPT)

    def test_typed_missing_division_rejected(self):
        t = typed(); del t["Medak"]
        with self.assertRaises(ValueError):
            baseline_from_typed(t, *SEPT)

    def test_from_consolidation(self):
        cons = pd.DataFrame([
            {"division": d, "activation_pct": 0.5, "devices_supplied": 10, "devices_activated": 5}
            for d in config.DIVISIONS + ["Total"]
        ])
        b = baseline_from_consolidation(cons, *SEPT, "computed from x.csv")
        self.assertEqual(b["activation_pct"]["Total"], 0.5)
        self.assertEqual(b["devices_activated"]["Medak"], 5)

    def test_missing_file_means_no_baseline_and_no_error(self):
        b, problem = load_baseline(self.tmp)
        self.assertIsNone(b)
        self.assertIsNone(problem)

    def test_corrupt_file_reports_a_problem_not_a_crash(self):
        self.tmp.write_text("{not json")
        b, problem = load_baseline(self.tmp)
        self.assertIsNone(b)
        self.assertIn("could not be read", problem)


class TestResolveForReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "prev.json"
        save_baseline(baseline_from_typed(typed(40.0), *SEPT), self.tmp)
        self.baseline, _ = load_baseline(self.tmp)

    def test_matching_month_is_available(self):
        r = resolve_for_report(self.baseline, dt.date(2026, 10, 25))
        self.assertTrue(r.available)
        self.assertAlmostEqual(r.pct_by_division["Medak"], 0.40)
        self.assertEqual(r.label, "01.09.2026 to 30.09.2026")

    def test_stale_baseline_gives_na_and_a_message(self):
        r = resolve_for_report(self.baseline, dt.date(2026, 11, 2))   # needs October
        self.assertFalse(r.available)
        self.assertEqual(r.pct_by_division, {})
        self.assertIn("01.09.2026 to 30.09.2026", r.message)
        self.assertEqual(r.label, "01.10.2026 to 31.10.2026")   # header shows what the report NEEDS

    def test_no_baseline_gives_na(self):
        r = resolve_for_report(None, dt.date(2026, 10, 25))
        self.assertFalse(r.available)
        self.assertIn("No previous-month baseline", r.message)

    def test_baseline_ending_before_month_end_still_matches_by_month(self):
        save_baseline(baseline_from_typed(typed(), dt.date(2026, 9, 1), dt.date(2026, 9, 29)), self.tmp)
        b, _ = load_baseline(self.tmp)
        r = resolve_for_report(b, dt.date(2026, 10, 3))
        self.assertTrue(r.available)
        self.assertEqual(r.label, "01.09.2026 to 29.09.2026")


if __name__ == "__main__":
    unittest.main()
