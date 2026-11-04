"""
The "previous month status" baseline behind the consolidation sheet's (A)
column.

A small JSON file (data/previous_month_status.json) holds last month's
division-wise Activation % (plus the overall Total). It is filled ONCE A
MONTH from the Admin panel — either computed from last month's final raw
transaction file with the normal rules, or typed in — and then committed to
the repository like the other reference data. Daily reports just read it.

If the saved baseline isn't for the month immediately before the Report
Date (e.g. nobody updated it on the 1st), the (A) column shows "NA" and the
UI says why, rather than silently showing a stale month's figures.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from .periods import period_label, previous_month_period

KEYS = list(config.DIVISIONS) + ["Total"]


@dataclass
class PreviousMonthLookup:
    pct_by_division: dict          # division/"Total" -> fraction (0-1); empty when unavailable
    period_start: dt.date
    period_end: dt.date
    available: bool
    message: str | None            # human-readable reason when unavailable, or an info note

    @property
    def label(self) -> str:
        return period_label(self.period_start, self.period_end)


def baseline_from_consolidation(consolidation_df, period_start: dt.date, period_end: dt.date, source: str) -> dict:
    """Builds a baseline from a consolidation table (one produced by
    report.build_consolidation for last month's final raw file)."""
    pct = {}
    devices_supplied, devices_activated = {}, {}
    for _, row in consolidation_df.iterrows():
        key = str(row["division"])
        pct[key] = float(row["activation_pct"])
        devices_supplied[key] = int(row["devices_supplied"])
        devices_activated[key] = int(row["devices_activated"])
    return _package(pct, period_start, period_end, source, devices_supplied, devices_activated)


def baseline_from_typed(percentages: dict, period_start: dt.date, period_end: dt.date) -> dict:
    """`percentages` are typed in PERCENT (e.g. 31.65), for every division and 'Total'."""
    missing = [k for k in KEYS if k not in percentages]
    if missing:
        raise ValueError(f"Missing percentage(s) for: {', '.join(missing)}")
    pct = {}
    for k in KEYS:
        v = float(percentages[k])
        if not 0 <= v <= 100:
            raise ValueError(f"Percentage for {k} must be between 0 and 100 (got {v}).")
        pct[k] = v / 100.0
    return _package(pct, period_start, period_end, "typed in Admin panel")


def _package(pct, period_start, period_end, source, devices_supplied=None, devices_activated=None) -> dict:
    if period_end < period_start:
        raise ValueError("Period end date is before the period start date.")
    out = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "source": source,
        "saved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "activation_pct": pct,
    }
    if devices_supplied is not None:
        out["devices_supplied"] = devices_supplied
        out["devices_activated"] = devices_activated
    return out


def save_baseline(baseline: dict, path: Path = config.PREVIOUS_MONTH_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def load_baseline(path: Path = config.PREVIOUS_MONTH_JSON):
    """Returns (baseline_dict | None, problem_text | None). Never raises —
    a missing or unreadable file just means 'no baseline'."""
    if not Path(path).exists():
        return None, None
    try:
        with open(path) as f:
            b = json.load(f)
        start = dt.date.fromisoformat(b["period_start"])
        end = dt.date.fromisoformat(b["period_end"])
        pct = b["activation_pct"]
        for k in KEYS:
            v = float(pct[k])
            if not 0 <= v <= 1:
                raise ValueError(f"{k} out of range")
        b["_start"], b["_end"] = start, end
        return b, None
    except Exception as e:  # noqa: BLE001 - any problem => treat as no baseline, but say why
        return None, f"The saved previous-month file could not be read ({e}). Please re-save it from the Admin panel."


def resolve_for_report(baseline, report_date: dt.date, problem: str | None = None) -> PreviousMonthLookup:
    """Decides what the (A) column shows for a given Report Date."""
    exp_start, exp_end = previous_month_period(report_date)

    if baseline is None:
        msg = problem or (
            "No previous-month baseline has been saved yet, so the (A) column shows NA. "
            "Set it once from the sidebar Admin panel."
        )
        return PreviousMonthLookup({}, exp_start, exp_end, False, msg)

    b_start, b_end = baseline["_start"], baseline["_end"]
    if (b_start.year, b_start.month) != (exp_start.year, exp_start.month):
        msg = (
            f"The saved previous-month baseline is for {period_label(b_start, b_end)}, but this report "
            f"needs {period_label(exp_start, exp_end)}, so the (A) column shows NA. "
            "Update the baseline from the sidebar Admin panel."
        )
        return PreviousMonthLookup({}, exp_start, exp_end, False, msg)

    return PreviousMonthLookup(
        {k: float(v) for k, v in baseline["activation_pct"].items()}, b_start, b_end, True, None
    )
