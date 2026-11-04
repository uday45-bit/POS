"""Office ID is found by header name (not position) — the October 2026 export
has 'Circle ID' in column A and 'Office ID' in column I."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.raw_transaction import load_raw_transaction_file

METRICS = "SBIPOS-CARD (Cnt),SBIPOS-CARD (Amt),SBIPOS BHARATQR (Cnt),SBIPOS BHARATQR (Amt)"


def up(text, name="t.csv", bom=False):
    data = text.encode("utf-8-sig" if bom else "utf-8")
    b = io.BytesIO(data)
    b.name = name
    return b


class TestOfficeIdByHeader(unittest.TestCase):
    def test_office_id_in_a_later_column_with_circle_id_in_column_a(self):
        header = f"Circle ID,Circle Name,Division Name,Office ID,Office Name,{METRICS}"
        rows = [
            header,
            "30300001,Telangana,Medak Division,11111111,Alpha SO,5,100,0,0",
            "30300001,Telangana,Medak Division,22222222,Beta SO,0,0,3,40",
        ]
        r = load_raw_transaction_file(up("\n".join(rows)))
        self.assertEqual(sorted(r.cleaned["office_id"]), ["11111111", "22222222"])   # NOT the circle id
        self.assertEqual(r.matched_columns["office_id"], "Office ID")
        a = r.cleaned[r.cleaned.office_id == "11111111"].iloc[0]
        self.assertEqual(a["sbipos_card_count"], 5)
        self.assertEqual(a["sbipos_card_amount"], 100)

    def test_summary_row_found_via_office_name_column(self):
        header = f"Circle ID,Office ID,Office Name,{METRICS}"
        rows = [header, "30300001,11111111,Alpha SO,5,100,0,0", "30300001,,Summary (All Offices),999,999,999,999"]
        r = load_raw_transaction_file(up("\n".join(rows)))
        self.assertEqual(r.dropped_summary_rows, 1)
        self.assertEqual(len(r.cleaned), 1)

    def test_missing_office_id_header_raises_clear_error(self):
        header = f"Circle ID,Office Name,{METRICS}"
        with self.assertRaises(ValueError) as ctx:
            load_raw_transaction_file(up(f"{header}\n30300001,Alpha SO,5,100,0,0"))
        self.assertIn("Office ID", str(ctx.exception))

    def test_utf8_bom_on_first_header_is_harmless(self):
        header = f"\ufeffOffice ID,Office Name,{METRICS}"   # BOM glued to the Office ID header
        r = load_raw_transaction_file(up(f"{header}\n11111111,Alpha SO,5,100,0,0", bom=True))
        self.assertEqual(r.cleaned.iloc[0]["office_id"], "11111111")

    def test_office_id_header_matching_ignores_case_and_spacing(self):
        header = f"office  id,Office Name,{METRICS}"
        r = load_raw_transaction_file(up(f"{header}\n11111111,Alpha SO,5,100,0,0"))
        self.assertEqual(r.cleaned.iloc[0]["office_id"], "11111111")


if __name__ == "__main__":
    unittest.main()
