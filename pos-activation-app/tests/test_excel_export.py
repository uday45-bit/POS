import io
import sys
import unittest
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.excel_export import build_workbook, workbook_to_bytes
from src.report import build_consolidation, build_division_sheets
from src.calculations import run_full_calculation


def make_inputs(prev=None):
    rows, calc_rows = [], []
    # one office per division; activity differs so the ranking is non-trivial
    activity = {"Secunderabad": 0, "Hyderabad South East": 30, "Hyderabad City": 0, "Sangareddy": 5,
                "Medak": 0, "Hyderabad GPO": 40, "Hyderabad Sorting": 0}
    for i, d in enumerate(config.DIVISIONS):
        rows.append({"office_id": str(1000 + i), "office_name": f"{d} SO", "division": d,
                     "devices_supplied": 1, "device_status": config.DEVICE_STATUS_WORKING_ELIGIBLE})
    universe = pd.DataFrame(rows)
    raw = pd.DataFrame([{"office_id": str(1000 + i), "sbipos_card_count": activity[d], "sbipos_card_amount": 0,
                         "sbipos_bharatqr_count": 0, "sbipos_bharatqr_amount": 0}
                        for i, d in enumerate(config.DIVISIONS)])
    calc = run_full_calculation(universe, raw)
    cons = build_consolidation(universe, calc, prev)
    return cons, build_division_sheets(calc)


class TestWorkbook(unittest.TestCase):
    def load(self, prev=None):
        cons, sheets = make_inputs(prev)
        wb = build_workbook(cons, sheets, "01.10.2026", "25.10.2026", "01.09.2026 to 30.09.2026")
        return cons, openpyxl.load_workbook(io.BytesIO(workbook_to_bytes(wb)))

    def test_division_sheets_follow_consolidation_ranking(self):
        cons, wb = self.load()
        ranked = [d for d in cons["division"] if d != "Total"]
        self.assertEqual(wb.sheetnames, [config.CONSOLIDATION_SHEET_NAME] + ranked)
        # South East and GPO are both 100% (a tie keeps the configured order),
        # then every 0% division after them.
        self.assertEqual(ranked[:2], ["Hyderabad South East", "Hyderabad GPO"])
        self.assertEqual(len(wb.sheetnames), 8)

    def test_headers_carry_periods_with_a_before_b(self):
        _, wb = self.load()
        ws = wb[config.CONSOLIDATION_SHEET_NAME]
        headers = [c.value for c in ws[2]][:6]
        self.assertEqual(headers[4], "Activation % Status 01.09.2026 to 30.09.2026 (A)")
        self.assertEqual(headers[5], "Activation % Status 01.10.2026 to 25.10.2026 (B)")
        self.assertIn("Period: 01.10.2026 to 25.10.2026", ws["A1"].value)
        self.assertEqual(ws["A1"].alignment.horizontal, "center")

    def test_column_a_shows_na_when_no_baseline(self):
        _, wb = self.load()
        ws = wb[config.CONSOLIDATION_SHEET_NAME]
        self.assertEqual({ws.cell(row=r, column=5).value for r in range(3, 11)}, {"NA"})

    def test_column_a_shows_percentages_when_baseline_given(self):
        prev = {d: 0.3165 for d in config.DIVISIONS}; prev["Total"] = 0.3505
        _, wb = self.load(prev)
        ws = wb[config.CONSOLIDATION_SHEET_NAME]
        self.assertAlmostEqual(ws.cell(row=3, column=5).value, 0.3165)
        self.assertEqual(ws.cell(row=3, column=5).number_format, "0.00%")
        self.assertAlmostEqual(ws.cell(row=10, column=5).value, 0.3505)

    def test_row_colour_follows_b_not_a(self):
        prev = {d: 0.99 for d in config.DIVISIONS}; prev["Total"] = 0.99      # high (A) everywhere
        cons, wb = self.load(prev)
        ws = wb[config.CONSOLIDATION_SHEET_NAME]
        for r in range(3, 10):
            b = ws.cell(row=r, column=6).value
            expected = config.FILL_DIVISION_MEETS_CRITERIA if b >= 0.5 else config.FILL_DIVISION_BELOW_CRITERIA
            self.assertTrue(ws.cell(row=r, column=2).fill.fgColor.rgb.endswith(expected))


if __name__ == "__main__":
    unittest.main()
