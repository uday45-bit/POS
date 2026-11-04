"""
Division-wise "SBI POS machines Not activated" lists, rendered as PNG images
for download/sharing (separate from the Excel workbook).

One image per division that has at least one non-activated office (ORANGE or
RED). A division where every office is activated (GREEN) gets no image.
Images are produced in consolidation-ranking order (best Activation % first).

Offices are listed in the same order as the division sheets: Combined Count
desc, Combined Amount desc, then Office Name asc — so offices with some
activity (peach rows) come first and zero-activity offices (pink rows) follow.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from . import config

HEADERS = [
    "Sl.No", "Office ID", "Office Name",
    "No. of POS Devices\nSupplied", "Combined\nTransaction Count", "Combined\nTransaction Amount",
]
COL_FRACTIONS = [0.07, 0.13, 0.29, 0.17, 0.17, 0.17]

FIG_WIDTH_IN = 9.4
ROW_H_IN = 0.30
HEADER_H_IN = 0.64
TITLE_H_IN = 0.98
DPI = 150

NAVY = "#" + config.FILL_HEADER
TITLE_BLUE = "#1F4E78"
FILL_BY_STATUS = {
    config.STATUS_ORANGE: "#" + config.FILL_ORANGE,
    config.STATUS_RED: "#" + config.FILL_RED,
}
GRID = "#9E9E9E"


@dataclass
class DivisionImage:
    division: str
    filename: str
    png_bytes: bytes
    n_offices: int
    n_devices: int


def non_activated_table(division_sheet: pd.DataFrame) -> pd.DataFrame:
    """Non-activated (ORANGE + RED) offices of one division, in the division
    sheet's own display order, renumbered from 1."""
    na = division_sheet[division_sheet["activation_status"] != config.STATUS_GREEN].copy()
    na = na.reset_index(drop=True)
    na["sl_no"] = range(1, len(na) + 1)
    return na[["sl_no", "office_id", "office_name", "devices_supplied",
               "combined_count", "combined_amount", "activation_status"]]


def image_title(division: str, period_label: str) -> str:
    return (
        f"List of offices under {division} Division where\n"
        f"SBI POS machines Not activated for the period {period_label}"
    )


def _fit_font(text_artist, renderer, max_width_px: float, start_size: float, min_size: float = 6.0):
    size = start_size
    text_artist.set_fontsize(size)
    while size > min_size and text_artist.get_window_extent(renderer).width > max_width_px:
        size -= 0.5
        text_artist.set_fontsize(size)


def render_division_image(division: str, period_label: str, table: pd.DataFrame) -> bytes:
    n = len(table)
    height_in = TITLE_H_IN + HEADER_H_IN + n * ROW_H_IN
    fig = Figure(figsize=(FIG_WIDTH_IN, height_in), dpi=DPI, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FIG_WIDTH_IN)
    ax.set_ylim(height_in, 0)   # y grows downward, like a sheet
    ax.axis("off")
    renderer = fig.canvas.get_renderer()
    px_per_in = DPI

    col_w = [f * FIG_WIDTH_IN for f in COL_FRACTIONS]
    col_x = [sum(col_w[:i]) for i in range(len(col_w))]

    # ---- title block ----
    ax.add_patch(Rectangle((0, 0), FIG_WIDTH_IN, TITLE_H_IN, facecolor="white", edgecolor=GRID, linewidth=0.8))
    title = ax.text(FIG_WIDTH_IN / 2, TITLE_H_IN / 2, image_title(division, period_label),
                    ha="center", va="center", fontsize=14, fontweight="bold",
                    color=TITLE_BLUE, linespacing=1.35)
    _fit_font(title, renderer, (FIG_WIDTH_IN - 0.5) * px_per_in, 14)

    # ---- header row ----
    y0 = TITLE_H_IN
    header_texts = []
    for i, h in enumerate(HEADERS):
        ax.add_patch(Rectangle((col_x[i], y0), col_w[i], HEADER_H_IN, facecolor=NAVY, edgecolor=GRID, linewidth=0.8))
        t = ax.text(col_x[i] + col_w[i] / 2, y0 + HEADER_H_IN / 2, h, ha="center", va="center",
                    fontsize=10.5, fontweight="bold", color="white", linespacing=1.25)
        _fit_font(t, renderer, (col_w[i] - 0.1) * px_per_in, 10.5)
        header_texts.append(t)
    uniform = min(t.get_fontsize() for t in header_texts)   # same size across all headers
    for t in header_texts:
        t.set_fontsize(uniform)

    # ---- data rows ----
    for r, row in enumerate(table.itertuples(index=False)):
        y = y0 + HEADER_H_IN + r * ROW_H_IN
        fill = FILL_BY_STATUS[row.activation_status]
        values = [
            str(int(row.sl_no)), str(row.office_id), str(row.office_name),
            str(int(row.devices_supplied)), str(int(row.combined_count)),
            f"\u20b9{float(row.combined_amount):,.2f}",
        ]
        for i, v in enumerate(values):
            ax.add_patch(Rectangle((col_x[i], y), col_w[i], ROW_H_IN, facecolor=fill, edgecolor=GRID, linewidth=0.6))
            if i == 2:   # office name: left-aligned with padding
                t = ax.text(col_x[i] + 0.08, y + ROW_H_IN / 2, v, ha="left", va="center", fontsize=10, color="black")
                _fit_font(t, renderer, (col_w[i] - 0.14) * px_per_in, 10)
            else:
                ax.text(col_x[i] + col_w[i] / 2, y + ROW_H_IN / 2, v, ha="center", va="center",
                        fontsize=10, color="black")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")
    return buf.getvalue()


def _slug(division: str) -> str:
    return division.replace(" ", "_")


def build_division_images(division_sheets: dict, ranked_divisions: list, period_label: str,
                           date_for_filename: str) -> list[DivisionImage]:
    """One image per division that has non-activated offices, in the order of
    `ranked_divisions` (the consolidation ranking)."""
    images = []
    rank = 0
    for division in ranked_divisions:
        table = non_activated_table(division_sheets[division])
        if table.empty:
            continue   # 100% activated -> left out
        rank += 1
        png = render_division_image(division, period_label, table)
        images.append(DivisionImage(
            division=division,
            filename=f"{rank:02d}_{_slug(division)}_Not_Activated_{date_for_filename}.png",
            png_bytes=png,
            n_offices=len(table),
            n_devices=int(table["devices_supplied"].sum()),
        ))
    return images


def images_to_zip(images: list[DivisionImage]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for img in images:
            z.writestr(img.filename, img.png_bytes)
    return buf.getvalue()
