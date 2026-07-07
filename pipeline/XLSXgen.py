"""Render an Excel workbook from JSON produced by JSONgen.

Each page in the JSON must have a "template" key containing the declarative
cell-grid schema output by the model.

Usage:
    python XLSXgen.py <json_path> [output.xlsx]
"""
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_THIN = Side(style="thin")
_BORDER_ALL = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)
_BORDER_NONE = Border()

# A4 usable column width in Excel char units (0.5" margins, Calibri 11pt)
_A4_PORTRAIT_COLS  = 100.0
_A4_LANDSCAPE_COLS = 128.0


def render_sheet(data: dict, ws) -> None:
    col_widths  = data.get("col_widths") or []
    rows        = data.get("rows") or []
    orientation = str(data.get("orientation") or "portrait").lower()
    sheet_name  = data.get("sheet_name")
    if sheet_name:
        try:
            ws.title = str(sheet_name)[:31]
        except Exception:
            pass

    # Expand "repeat" shorthand: {"h":N,"repeat":K,"cells":[...]} → K identical rows
    expanded_rows = []
    for row in rows:
        count = int(row.get("repeat") or 1)
        if count > 1:
            base = {k: v for k, v in row.items() if k != "repeat"}
            expanded_rows.extend([base] * count)
        else:
            expanded_rows.append(row)
    rows = expanded_rows

    num_rows = int(data.get("num_rows") or len(rows))
    row_by_r: dict[int, dict] = {}
    for idx, row in enumerate(rows):
        r = row.get("r") or row.get("row") or (idx + 1)
        row_by_r[int(r)] = row

    # Scale columns down to fit A4 (never scale up)
    target_cols = _A4_LANDSCAPE_COLS if orientation == "landscape" else _A4_PORTRAIT_COLS
    raw_col_total = sum(max(1.0, float(w)) for w in col_widths) if col_widths else 1.0
    col_scale = target_cols / raw_col_total

    for i, w in enumerate(col_widths, start=1):
        try:
            ws.column_dimensions[get_column_letter(i)].width = max(4.0, float(w) * col_scale)
        except (ValueError, TypeError):
            ws.column_dimensions[get_column_letter(i)].width = 8.0

    def _render_cell_spec(cell_spec, row_idx):
        try:
            col   = int(cell_spec.get("c") or cell_spec.get("col") or 1)
            span  = max(1, int(cell_spec.get("s") or cell_spec.get("span") or 1))
            rspan = max(1, int(cell_spec.get("rs") or cell_spec.get("rowspan") or 1))
        except (ValueError, TypeError):
            col, span, rspan = 1, 1, 1

        top_left = ws.cell(row=row_idx, column=col)
        if isinstance(top_left, MergedCell):
            return

        value      = cell_spec.get("v") or cell_spec.get("value") or None
        bold       = bool(cell_spec.get("b") or cell_spec.get("bold") or False)
        align      = cell_spec.get("a") or cell_spec.get("align") or "left"
        fill_hex   = cell_spec.get("f") or cell_spec.get("fill")
        x          = cell_spec.get("x") if "x" in cell_spec else cell_spec.get("border")
        end_col    = col + span - 1
        end_row    = row_idx + rspan - 1

        top_left.value     = value
        top_left.font      = Font(bold=bold)
        top_left.alignment = Alignment(horizontal=align, vertical="center", wrap_text=False)

        if fill_hex:
            hex_val = str(fill_hex).lstrip("#")
            if len(hex_val) == 6:
                try:
                    top_left.fill = PatternFill(
                        start_color=hex_val, end_color=hex_val, fill_type="solid"
                    )
                except Exception:
                    pass

        # Normalize model output: string "true"/"false" instead of JSON boolean
        if isinstance(x, str):
            if x.lower() == "true":
                x = True
            elif x.lower() in ("false", "none"):
                x = False

        # Determine per-side border flags
        if x is True or x == "all" or x == "tlbr":
            wt = wb = wl = wr = True
        elif isinstance(x, str) and x:
            wt = "t" in x; wb = "b" in x; wl = "l" in x; wr = "r" in x
        else:
            wt = wb = wl = wr = False

        # Stamp borders on every EDGE cell of the span BEFORE merging.
        # openpyxl only lets us style the top-left after merge_cells(), so
        # the right/bottom edges of a multi-cell span must be written now,
        # while all positions are still regular Cell objects.
        for r in range(row_idx, end_row + 1):
            for c in range(col, end_col + 1):
                target = ws.cell(row=r, column=c)
                if isinstance(target, MergedCell):
                    continue
                prev = target.border
                target.border = Border(
                    top    = _THIN if (wt and r == row_idx)  else prev.top,
                    bottom = _THIN if (wb and r == end_row)  else prev.bottom,
                    left   = _THIN if (wl and c == col)      else prev.left,
                    right  = _THIN if (wr and c == end_col)  else prev.right,
                )

        # Merge after borders are stamped
        if span > 1 or rspan > 1:
            try:
                ws.merge_cells(
                    start_row=row_idx, end_row=end_row,
                    start_column=col,  end_column=end_col,
                )
            except Exception:
                pass

    # Render rows and cells
    for row_idx in range(1, num_rows + 1):
        row = row_by_r.get(row_idx, {})
        try:
            height = float(row.get("h") or row.get("height") or 15)
        except (ValueError, TypeError):
            height = 15.0
        ws.row_dimensions[row_idx].height = max(5.0, height)

        for cell_spec in (row.get("cells") or []):
            _render_cell_spec(cell_spec, row_idx)

    # Bump column widths to fit cell text (CJK chars ≈ 2 units, ASCII ≈ 1)
    num_cols = len(col_widths)
    half_cols = num_cols // 2
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            cell = ws.cell(row=r, column=c)
            if not cell.value or isinstance(cell, MergedCell):
                continue
            text = str(cell.value)
            # Skip cells that are part of a wide merge spanning more than half the columns
            mr_spans = [mr for mr in ws.merged_cells.ranges
                        if mr.min_row <= r <= mr.max_row
                        and mr.min_col <= c <= mr.max_col
                        and (mr.max_col - mr.min_col + 1) > half_cols]
            if mr_spans:
                continue
            needed = sum(2.0 if ord(ch) > 127 else 1.0 for ch in text) * 0.75 + 1
            current = float(ws.column_dimensions[get_column_letter(c)].width or 8.0)
            if needed > current:
                ws.column_dimensions[get_column_letter(c)].width = min(needed, 30.0)

    # Page setup — A4, correct orientation, fit to one page
    ws.page_setup.paperSize   = 9  # A4
    ws.page_setup.orientation = orientation
    ws.page_setup.fitToPage   = True
    ws.page_setup.fitToWidth  = 1
    ws.page_setup.fitToHeight = 1
    ws.page_margins.left   = 0.5
    ws.page_margins.right  = 0.5
    ws.page_margins.top    = 0.5
    ws.page_margins.bottom = 0.5


def _unique_name(base: str, seen: set) -> str:
    clean = re.sub(r'[:\\/?*\[\]]', "", base)[:30].strip() or "Sheet"
    name, ctr = clean, 1
    while name in seen:
        suffix = f"_{ctr}"
        name = clean[: 30 - len(suffix)] + suffix
        ctr += 1
    seen.add(name)
    return name


def json_to_xlsx(json_path: str, xlsx_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    wb = Workbook()
    default_sheet = wb.active
    seen: set = set()

    pages = data.get("pages")
    if pages is None:
        pages = [data]

    for idx, page_data in enumerate(pages):
        if "error" in page_data:
            continue

        tmpl = page_data.get("template")
        if not tmpl or not isinstance(tmpl, dict):
            print(f"Page {idx + 1}: no template, skipping", file=sys.stderr)
            continue

        raw_name = str(tmpl.get("sheet_name") or f"Sheet {idx + 1}")
        ws = wb.create_sheet(title=_unique_name(raw_name, seen))
        render_sheet(tmpl, ws)

    if len(wb.worksheets) > 1:
        wb.remove(default_sheet)

    wb.save(xlsx_path)
    print(f"Saved {xlsx_path}", file=sys.stderr)


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("json_path")
    p.add_argument("xlsx_path", nargs="?")
    args = p.parse_args()
    xlsx_path = args.xlsx_path or str(Path(args.json_path).with_suffix(".xlsx"))
    json_to_xlsx(args.json_path, xlsx_path)


if __name__ == "__main__":
    main()
