"""Date helpers shared by the UI, the Excel export and the image export.

Every report covers "the 1st of the Report Date's month up to the Report
Date" (daily month-to-date use), and the (A) comparison column covers the
full previous calendar month.
"""

from __future__ import annotations

import datetime as dt


def dot_date(d) -> str:
    """dd.mm.yyyy, as used in every report heading."""
    return d.strftime("%d.%m.%Y")


def month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


def current_period(report_date: dt.date) -> tuple[dt.date, dt.date]:
    """1st of the Report Date's month -> the Report Date."""
    return month_start(report_date), report_date


def previous_month_period(report_date: dt.date) -> tuple[dt.date, dt.date]:
    """The full calendar month before the Report Date's month (works across
    a year boundary: a January date gives 01.12 to 31.12 of the year before)."""
    end = month_start(report_date) - dt.timedelta(days=1)
    return month_start(end), end


def period_label(start: dt.date, end: dt.date) -> str:
    """e.g. '01.10.2026 to 25.10.2026'"""
    return f"{dot_date(start)} to {dot_date(end)}"
