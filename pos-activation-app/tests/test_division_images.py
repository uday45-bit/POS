import sys
import unittest
import zipfile
import io
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.division_images import (
    build_division_images, image_title, images_to_zip, non_activated_table,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sheet(rows):
    """rows: (office_id, name, devices, count, amount, status) in display order"""
    return pd.DataFrame([
        {"office_id": o, "office_name": n, "devices_supplied": d, "combined_count": c,
         "combined_amount": a, "activation_status": s}
        for o, n, d, c, a, s in rows
    ])


G, O, R = config.STATUS_GREEN, config.STATUS_ORANGE, config.STATUS_RED


class TestNonActivatedTable(unittest.TestCase):
    def test_green_offices_are_excluded_and_numbering_restarts(self):
        t = non_activated_table(sheet([("1", "A", 1, 20, 0, G), ("2", "B", 1, 3, 133, O), ("3", "C", 2, 0, 0, R)]))
        self.assertEqual(list(t["office_id"]), ["2", "3"])
        self.assertEqual(list(t["sl_no"]), [1, 2])

    def test_keeps_display_order_orange_then_red(self):
        t = non_activated_table(sheet([("2", "B", 1, 3, 133, O), ("3", "C", 2, 0, 0, R)]))
        self.assertEqual(list(t["activation_status"]), [O, R])

    def test_all_green_gives_empty_table(self):
        self.assertTrue(non_activated_table(sheet([("1", "A", 1, 20, 0, G)])).empty)


class TestTitle(unittest.TestCase):
    def test_title_has_division_and_period_on_two_lines(self):
        t = image_title("Hyderabad City", "01.10.2026 to 25.10.2026")
        self.assertEqual(t.count("\n"), 1)
        self.assertIn("List of offices under Hyderabad City Division where", t)
        self.assertIn("Not activated for the period 01.10.2026 to 25.10.2026", t)
        self.assertNotIn("month of", t)


class TestBuildImages(unittest.TestCase):
    def setUp(self):
        self.sheets = {
            "Medak": sheet([("1", "Machavaram S.O", 1, 7, 410, O), ("2", "Allipur S.O", 1, 0, 0, R)]),
            "Hyderabad GPO": sheet([("9", "GPO", 7, 99, 0, G)]),               # 100% -> left out
            "Sangareddy": sheet([("5", "Hadnur S.O", 1, 9, 654.5, O)]),
        }

    def test_fully_activated_division_is_left_out_and_order_follows_ranking(self):
        imgs = build_division_images(self.sheets, ["Hyderabad GPO", "Sangareddy", "Medak"], "01.10.2026 to 25.10.2026", "20261025")
        self.assertEqual([i.division for i in imgs], ["Sangareddy", "Medak"])
        self.assertEqual([i.n_offices for i in imgs], [1, 2])
        self.assertTrue(imgs[0].filename.startswith("01_Sangareddy_Not_Activated_20261025"))
        self.assertTrue(imgs[1].filename.startswith("02_Medak_"))

    def test_images_are_real_pngs(self):
        imgs = build_division_images(self.sheets, ["Medak"], "01.10.2026 to 25.10.2026", "20261025")
        self.assertTrue(imgs[0].png_bytes.startswith(PNG_SIGNATURE))
        self.assertGreater(len(imgs[0].png_bytes), 5000)

    def test_device_total_counts_devices_not_offices(self):
        s = {"Medak": sheet([("1", "A", 2, 0, 0, R), ("2", "B", 1, 0, 0, R)])}
        imgs = build_division_images(s, ["Medak"], "x", "d")
        self.assertEqual((imgs[0].n_offices, imgs[0].n_devices), (2, 3))

    def test_no_non_activated_offices_gives_no_images(self):
        s = {"Hyderabad GPO": sheet([("9", "GPO", 7, 99, 0, G)])}
        self.assertEqual(build_division_images(s, ["Hyderabad GPO"], "x", "d"), [])

    def test_zip_contains_every_image(self):
        imgs = build_division_images(self.sheets, ["Sangareddy", "Medak"], "x", "d")
        z = zipfile.ZipFile(io.BytesIO(images_to_zip(imgs)))
        self.assertEqual(sorted(z.namelist()), sorted(i.filename for i in imgs))

    def test_long_list_and_long_names_render_without_error(self):
        rows = [(str(i), "A very long office name that goes on and on S.O " * 2, 1, 0, 1234567.5, R) for i in range(60)]
        imgs = build_division_images({"Medak": sheet(rows)}, ["Medak"], "01.10.2026 to 31.10.2026", "d")
        self.assertEqual(imgs[0].n_offices, 60)


if __name__ == "__main__":
    unittest.main()
