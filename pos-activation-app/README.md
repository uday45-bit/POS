# POS Activation Status Analysis

A Streamlit application that turns a raw transaction file into a formatted,
division-wise **SBI POS Machine Activation Status** report — matching every
transaction to the correct post office, applying device-adjusted activation
thresholds, and producing a color-coded, production-ready Excel workbook.

---

## 1. What this app does

1. You pick a **Report Date** and upload the raw transaction file (CSV or
   Excel).
2. The app matches every row to the Office Master by **Office ID**, cleans
   and aggregates the data, and classifies each device-supplied office as:
   - 🟢 **GREEN** — combined transaction count or amount met the
     device-adjusted threshold
   - 🟠 **ORANGE** — some activity, but below threshold
   - 🔴 **RED** — zero activity
3. It shows a validation summary (matched/unmatched offices, duplicates,
   which raw columns were matched, warnings) and the division-wise
   consolidation table in the browser.
4. You download a single `.xlsx` workbook: a consolidation sheet + one sheet
   per division (8 sheets total), fully formatted. Division sheets follow the
   consolidation ranking (best Activation % first).
5. You can also download **division-wise "Not activated" lists as images**
   (PNG, one per division, or all in a ZIP) for sharing.

Built for **daily** use: every report covers the **1st of the Report Date's
month up to the Report Date** (e.g. Report Date 25.10.2026 -> "01.10.2026 to
25.10.2026"), and the consolidation sheet compares it with the previous
month's final status.

You do **not** need to upload the Office Master or Device Supply list every
time — those are pre-loaded, cleaned reference files committed to this
project (see `data/`). You only ever upload the transaction file for the
report you're generating.

---

## 2. Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

The `data/*.csv` reference files are already built from the Office Master
and Device Supply list you supplied. Nothing further is needed to start
generating reports.

---

## 3. The raw transaction file format

**Every column is found by searching the header row for its name** — nothing
depends on column position (the October 2026 export has "Circle ID" in
column A and "Office ID" in column I):

| Field | Header text searched for |
|---|---|
| Office the row belongs to | `Office ID` |
| SBI POS Card transaction count | `SBIPOS-CARD (Cnt)` |
| SBI POS Card transaction amount | `SBIPOS-CARD (Amt)` |
| SBI POS Bharat QR transaction count | `SBIPOS BHARATQR (Cnt)` |
| SBI POS Bharat QR transaction amount | `SBIPOS BHARATQR (Amt)` |

Matching is case/spacing/hyphen-insensitive — `"sbipos card (cnt)"` and
`"SBIPOS-CARD (Cnt)"` are the same column — and a UTF-8 BOM on the first
header is ignored. A header row is therefore **required**; if any of the
names can't be found, the app stops with a clear error listing exactly
what's missing and what headers *were* found, rather than guessing. The
validation summary's "Matched columns" panel shows which header text was
matched to which field on every run.

The file may include a `Summary (All Offices)` row — it is detected and
excluded automatically. Blank Office IDs are dropped and reported. Office
IDs that repeat are summed together. Rows for offices that aren't in the
Office Master (e.g. branch offices) are listed as "unmatched" and ignored.

---

## 4. Business rules implemented

**Per-device thresholds** (a multi-device office needs proportionally more
activity):

```
Count Threshold  = 10   × No. of POS Devices Supplied
Amount Threshold = 5000 × No. of POS Devices Supplied
```

**Activation status (per office):**

```
GREEN  = Combined Count  >= Count Threshold   OR   Combined Amount >= Amount Threshold
ORANGE = not GREEN  AND  (Combined Count > 0  OR  Combined Amount > 0)
RED    = Combined Count == 0  AND  Combined Amount == 0
```

**Row sort order within each division sheet** (a separate concern from the
status color): Group 1 (met the count threshold) -> Group 2 (didn't meet
count, but met amount threshold) -> Group 3 (neither); within a group, by
Combined Count desc, then Combined Amount desc, then Office Name asc.

**Office eligibility** is a simple 2-state model — every Master office is
either:

| Status | Meaning | Included in activation analysis? |
|---|---|---|
| Working / Eligible | Has at least one device on record | Yes |
| Device Not Supplied | No device record for this office | No |

There is no "Pending Whitelisting" or "Closed Office" status — that concept
was deliberately removed. An office that's no longer in the Office Master
(e.g. historically closed) simply isn't part of the universe at all; if its
Office ID still shows up with device evidence in the Device Supply list,
that device is excluded and reported as "orphaned" in
`reference_data_meta.json` rather than silently dropped.

**Division-wise consolidation (the first sheet)** follows the report
owner's reference proforma:
- Columns: Sl.No, Division Name, No. of POS Machines Supplied, No. of SBI
  POS – Activation Done, then two Activation % columns:
  **(A)** = the previous full month, **(B)** = the 1st of the Report Date's
  month up to the Report Date. Each header carries its period, e.g.
  `Activation % Status 01.10.2026 to 25.10.2026 (B)`.
- Both count columns are in **device units** (not office counts) — a GREEN
  office's entire device count counts as activated, since the raw
  transaction data is reported per office, not per individual device.
- Divisions are **ranked by Activation % (B) descending**; ties keep the
  configured division order; the Total row always stays last.
- Row coloring follows **(B) only**: at or above
  `config.DIVISION_ACTIVATION_CRITERIA_PCT` (50%) -> sea-green; below ->
  light pink. The Total row keeps its own blue-gray styling.
- The title is centred and embeds "Period: dd.mm.yyyy to dd.mm.yyyy" plus
  the criteria (10 / Rs.5000 / 50%), all pulled live from `src/config.py`.
- (A) shows **NA** when no matching previous-month baseline is saved (see
  section 5) — never a stale month's figures.

**Division sheets (Excel)** list every device-supplied office with its card /
QR split, thresholds and GREEN / ORANGE / RED status, in the same order as the
consolidation ranking.

**"Not activated" images** (one PNG per division): only ORANGE (some activity,
peach rows) and RED (no activity, pink rows) offices, with Sl.No, Office ID,
Office Name, No. of POS Devices Supplied, Combined Transaction Count and
Amount, under the title "List of offices under {Division} Division where SBI
POS machines Not activated for the period {1st of month} to {Report Date}".
A division where **every office is activated gets no image**. Images are
produced in consolidation-ranking order, sorted like the division sheets
(count desc, amount desc, name asc).

---

## 5. Reference data & the admin refresh panel

The permanent reference data lives in `data/*.csv`:

| File | Contents |
|---|---|
| `office_master.csv` | The Office Master: ID, name, division, type |
| `device_supply.csv` | Devices supplied per office (restricted to offices in the current Master) |
| `reference_data_meta.json` | Generation timestamp + data-quality diagnostics |

"Device Not Supplied" is **derived** (Master minus Device Supply) — there is
no separate maintained list for it.

**When the Office Master or the Device Supply list changes**, refresh these
files two ways — both accept the Master as either the original `.xlsx`
layout or a flat CSV export (with or without a `division-office-id`
column), and the Device Supply list as a flat `Division Name / Office ID /
Office Name / TID` list (one row per physical device), matched by column
name, not position:

- **In the app** — sidebar -> Admin: Refresh Reference Data -> upload
  the updated Master and Device Supply files -> Rebuild Reference Data.
- **From the command line:**
  ```bash
  python scripts/build_reference_data.py \
      --master "path/to/updated_master.csv" \
      --devices "path/to/Device_Supply_list.xlsx"
  ```

Both call the same logic (`src/reference_builder.py`), so they can never
drift apart. Re-running is always safe — it fully regenerates `data/*.csv`
from the two inputs and never invents data that isn't present in them.
Afterward, check the console output (or `data/reference_data_meta.json` ->
`data_quality_conflicts`) for `NOTE:` / `WARNING:` lines — they call out
anything needing human confirmation: a device whose Office ID has no home
in the current Master ("orphaned"), or a single device TID assigned to two
different offices in the source file (an "unresolved TID conflict" — these
are kept, flagged, and NOT auto-resolved unless a rule for that exact TID
has been confirmed and added to `CONFIRMED_TID_OFFICE` in
`reference_builder.py`).

If it finds a genuinely structural problem — a duplicate Office ID inside
the Master, or a device-supply row missing a required field — it **stops**
rather than guessing.

### Previous-month status (the (A) column) — set once a month

`data/previous_month_status.json` holds last month's division-wise Activation
% and overall Total. Daily reports just read it. Once a month (e.g. on the
1st), open the sidebar **Admin: Previous-month status (A)** panel, pick the last
day of the month being saved, and either:

- upload **last month's final raw file** — the app computes the figures with
  the normal rules (using the *current* office/device list, so they can differ
  slightly from what was reported at the time if devices changed), or
- **type the percentages** (7 divisions + Total) exactly as reported.

Then **commit `data/previous_month_status.json` to GitHub** — on a hosted app
the panel's save is lost on restart unless it's committed (same as the
reference-data panel). If the saved month isn't the month right before the
Report Date (e.g. it wasn't updated on the 1st), (A) shows NA and the UI says
why.

### Getting an update onto GitHub

If your repo already exists, do this in your **existing local clone** — it
keeps your git history intact:

```bash
cd your-existing-clone/pos-activation-app
# copy the refreshed data/*.csv (and any changed src/ files, if applicable)
# over the matching files in this folder, then:
git add -A
git commit -m "Update reference data"
git push
```

---

## 6. Project structure

```
app.py                          Streamlit UI -- the entry point
requirements.txt
.streamlit/config.toml          Theme
data/                           Reference CSVs + generation metadata (committed)
scripts/
  build_reference_data.py       CLI: rebuild data/*.csv from source files
src/
  config.py                     Divisions, thresholds, raw-column names, colors
  reference_builder.py          Reference-data extraction/reconciliation logic
  data_loader.py                Loads data/*.csv, builds the office classification
  raw_transaction.py            Reads/cleans the uploaded raw transaction file
  calculations.py                Thresholds, GREEN/ORANGE/RED, sort groups
  report.py                     Builds the consolidation + division tables
  validation.py                 Pre-generation validation & reconciliation checks
  periods.py                    Report-period helpers (month-to-date, previous month)
  previous_month.py             Previous-month baseline for the (A) column
  excel_export.py               openpyxl workbook generation & formatting
  division_images.py            "Not activated" PNG lists (matplotlib)
tests/
  test_calculations.py          Threshold & activation-status logic
  test_matching.py              Office ID matching & 2-state eligibility
  test_validation.py            Raw-file cleaning, header-name column lookup,
                                 reconciliation checks
  test_reference_builder.py     Office Master / Device Supply loading,
                                 TID-conflict resolution, orphan detection
  test_report.py                Consolidation: device-weighted counts, ranking, (A) column
  test_raw_office_id.py         Office ID found by header (not position), BOM, errors
  test_periods.py               Month-to-date / previous-month periods, labels
  test_previous_month.py        Baseline save/load, stale-month handling
  test_division_images.py       Non-activated lists, left-out divisions, PNG output
  test_excel_export.py          Sheet order, (A)/(B) headers, NA, row colouring
```

---

## 7. Running the tests

```bash
python -m unittest discover -s tests -v
```

98 tests cover: device-adjusted thresholds, all activation-status edge cases
(count-only, amount-only, combined card+QR, exact-threshold boundaries),
sort-group ordering and tie-breaks, Office ID matching (matched/unmatched),
the 2-state eligibility model, raw-file cleaning (summary-row removal,
blank-ID handling, duplicate aggregation, non-numeric handling),
header-name-based column lookup (including a test that deliberately
reorders the metric columns to prove position doesn't matter), reference
Master/Device-Supply loading in both file formats, confirmed TID-conflict
resolution, orphaned-device detection, and consolidation/division-sheet
reconciliation, the previous-month (A) baseline, the division images and
the Excel sheet order/headers.

The full pipeline has also been exercised end-to-end against synthetic
transaction files (covering every case above, plus multi-device offices and
an unmatched Office ID) and via Streamlit's `AppTest` framework driving the
actual UI (file upload -> Generate click -> download), with zero
exceptions — including the error path for a file missing a required column.

---

## 8. Notes & limitations

- Office IDs are always treated as strings throughout, so an ID with leading
  zeros will not silently lose them.
- If report generation would produce **inconsistent** totals (e.g. the
  consolidation sheet's devices-activated count doesn't match the division
  sheets), the app stops and shows the mismatch rather than downloading a
  wrong report.
- The app caches the reference data in memory; after using the Admin panel
  to rebuild it, the app automatically clears that cache and reloads.
- "No. of SBI POS – Activation Done" and "No. of POS Machines Supplied" on
  the consolidation sheet are both device counts: a GREEN office with 4
  devices contributes 4 to "Activation Done", not 1. This was a deliberate
  design choice (keeping both columns in the same unit so the percentage is
  self-consistent) — see the module docstring in `src/report.py` if this
  ever needs revisiting.
