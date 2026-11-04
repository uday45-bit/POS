"""
Reads and cleans the raw transaction file the user uploads.

EVERY column the app needs is found by SEARCHING THE HEADER ROW for its
name — nothing is identified by position, because export layouts shift (the
October 2026 export has "Circle ID" in column A and "Office ID" in column I):

    Office ID                -> the office the row belongs to
    SBIPOS-CARD (Cnt)        -> SBI POS Card transaction count
    SBIPOS-CARD (Amt)        -> SBI POS Card transaction amount
    SBIPOS BHARATQR (Cnt)    -> SBI POS Bharat QR transaction count
    SBIPOS BHARATQR (Amt)    -> SBI POS Bharat QR transaction amount

Matching is case/spacing/hyphen-insensitive (see _normalise_header) so
"SBIPOS-CARD (Cnt)", "sbipos card (cnt)" and "SBIPOS  CARD(CNT)" are all the
same column. A header row is therefore required; if any name can't be found,
loading stops with a clear error listing what was found instead, rather than
guessing a position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from . import config


@dataclass
class RawLoadResult:
    raw_row_count: int
    cleaned: pd.DataFrame               # aggregated by office_id, numeric columns clean
    dropped_summary_rows: int
    dropped_blank_office_id_rows: int
    duplicate_office_id_count: int
    duplicate_office_ids: list
    header_warnings: list = field(default_factory=list)
    non_numeric_cells_zeroed: int = 0
    matched_columns: dict = field(default_factory=dict)  # internal name -> actual header text found


def _normalise_header(s) -> str:
    """Case/spacing/hyphen-insensitive normalisation for header matching:
    'SBIPOS-CARD (Cnt)', 'sbipos card (cnt)' and 'SBIPOS  CARD(CNT)' all
    normalise to the same string. A UTF-8 BOM (which Excel/CSV exports often
    prepend to the first header) is stripped too."""
    return re.sub(r"[\s\-]+", "", str(s).replace("\ufeff", "").upper())


def _find_required_columns(header_row: pd.Series) -> tuple[dict, list]:
    """Searches the header row for each of config.RAW_EXPECTED_HEADERS.
    Returns (internal_name -> column_index, list_of_not_found_internal_names)."""
    normalised_to_idx = {}
    for idx, cell in enumerate(header_row):
        normalised_to_idx.setdefault(_normalise_header(cell), idx)

    found, missing = {}, []
    for internal_name, target_text in config.RAW_EXPECTED_HEADERS.items():
        idx = normalised_to_idx.get(_normalise_header(target_text))
        if idx is None:
            missing.append(internal_name)
        else:
            found[internal_name] = idx
    return found, missing


def _find_optional_column(header_row: pd.Series, header_text: str):
    target = _normalise_header(header_text)
    for idx, cell in enumerate(header_row):
        if _normalise_header(cell) == target:
            return idx
    return None


def _to_numeric_safe(series: pd.Series) -> tuple[pd.Series, int]:
    """Convert to numeric; blanks/non-numeric become 0."""
    converted = pd.to_numeric(series, errors="coerce")
    non_numeric_count = int(converted.isna().sum() - series.isna().sum())
    converted = converted.fillna(0)
    return converted, max(non_numeric_count, 0)


def load_raw_transaction_file(uploaded_file) -> RawLoadResult:
    """`uploaded_file` is a Streamlit UploadedFile (file-like, has .name)."""
    name = getattr(uploaded_file, "name", "")
    if name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=None, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        df = pd.read_excel(uploaded_file, header=None, dtype=str, engine="openpyxl")
        df = df.fillna("")

    if df.shape[1] < config.MIN_RAW_COLUMNS or len(df) == 0:
        raise ValueError(
            f"The uploaded file only has {df.shape[1]} column(s) and {len(df)} row(s), "
            "which isn't enough to contain a header row plus the required columns. "
            "Please check that the correct raw transaction file was uploaded."
        )

    # A header row is required — it's how every needed column is found.
    header_row = df.iloc[0]
    found_cols, missing_cols = _find_required_columns(header_row)
    if missing_cols:
        missing_names = [config.RAW_EXPECTED_HEADERS[m] for m in missing_cols]
        available = [str(c).replace("\ufeff", "").strip() for c in header_row if str(c).strip() != ""]
        raise ValueError(
            "Could not find the following required column(s) in the file's header row: "
            + ", ".join(f"'{m}'" for m in missing_names)
            + ". Columns found in the header row: "
            + (", ".join(f"'{a}'" for a in available) if available else "(none)")
            + ". Please check the file has a header row with these exact column names "
            "(matching is not case- or spacing-sensitive)."
        )

    body = df.iloc[1:].reset_index(drop=True)
    raw_row_count = len(body)

    name_idx = _find_optional_column(header_row, config.RAW_OFFICE_NAME_HEADER)
    work = pd.DataFrame({
        "office_id": body.iloc[:, found_cols["office_id"]].astype(str).str.strip(),
        "office_name_raw": (
            body.iloc[:, name_idx].astype(str).str.strip() if name_idx is not None else ""
        ),
        "sbipos_card_count": body.iloc[:, found_cols["sbipos_card_count"]],
        "sbipos_card_amount": body.iloc[:, found_cols["sbipos_card_amount"]],
        "sbipos_bharatqr_count": body.iloc[:, found_cols["sbipos_bharatqr_count"]],
        "sbipos_bharatqr_amount": body.iloc[:, found_cols["sbipos_bharatqr_amount"]],
    })

    # 1) Drop the "Summary (All Offices)" row(s): by Office Name when that
    #    column exists, and as a fallback by that text appearing anywhere in the row.
    summary_mask = work["office_name_raw"].str.lower().isin(config.SUMMARY_ROW_OFFICE_NAME_MARKERS)
    row_text_lower = body.astype(str).apply(lambda r: " ".join(r).lower(), axis=1)
    summary_mask = summary_mask | row_text_lower.str.contains("summary (all offices)", regex=False)
    dropped_summary_rows = int(summary_mask.sum())
    work = work[~summary_mask].reset_index(drop=True)

    # 2) Clean Office ID: string, trimmed, preserve leading zeros, ignore blanks.
    blank_mask = (work["office_id"] == "") | (work["office_id"].str.lower() == "nan")
    dropped_blank_office_id_rows = int(blank_mask.sum())
    work = work[~blank_mask].reset_index(drop=True)

    # 3) Duplicate Office IDs — report BEFORE aggregating.
    dup_counts = work["office_id"].value_counts()
    duplicate_office_ids = sorted(dup_counts[dup_counts > 1].index.tolist())
    duplicate_office_id_count = int((dup_counts > 1).sum())

    # 4) Numeric conversion — blank/non-numeric -> 0.
    metric_cols = ["sbipos_card_count", "sbipos_card_amount", "sbipos_bharatqr_count", "sbipos_bharatqr_amount"]
    non_numeric_total = 0
    for col in metric_cols:
        work[col], n_bad = _to_numeric_safe(work[col])
        non_numeric_total += n_bad

    # 5) Aggregate by Office ID (sum) — handles true duplicates naturally.
    cleaned = work.groupby("office_id", as_index=False)[metric_cols].sum()

    matched_columns = {
        internal_name: str(header_row.iloc[idx]).replace("\ufeff", "").strip()
        for internal_name, idx in found_cols.items()
    }

    return RawLoadResult(
        raw_row_count=raw_row_count,
        cleaned=cleaned,
        dropped_summary_rows=dropped_summary_rows,
        dropped_blank_office_id_rows=dropped_blank_office_id_rows,
        duplicate_office_id_count=duplicate_office_id_count,
        duplicate_office_ids=duplicate_office_ids,
        header_warnings=[],
        non_numeric_cells_zeroed=non_numeric_total,
        matched_columns=matched_columns,
    )
