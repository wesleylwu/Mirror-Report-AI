"""Convert a JSON table description (from JSONgen) to an Excel file.

JSON schema (matches JSONgen output):
  {
    "header": [
      [{"label", "value", "label_span", "value_span", "bold", "font_size", "height"}, ...]
    ],
    "table": {
      "column_widths": {"col_name": width_chars},
      "row_height": 1|2|3,
      "blank_rows": int,
      "rows": [
        {"_style": "data|total|subheader|full_width", "_value": "...",
         "col_name": {"text", "bold", "font_size", "wrap"}}
      ]
    }
  }
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ── Constants ──────────────────────────────────────────────────────────────
_THIN = Side(style="thin")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
ROW_HEIGHT = 15          # default row height in points
COL_SCALE  = 1.2         # scale factor applied to column widths for readability
GREY_FILL  = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
INTERNAL   = {"_style", "_value", "_height", "_bg"}


# ── Helpers ────────────────────────────────────────────────────────────────
def _text(cell_val) -> str:
    if isinstance(cell_val, dict):
        return cell_val.get("text", "")
    return cell_val or ""


def _font_size(code: int) -> int:
    return {1: 8, 2: 10, 3: 14}.get(code, 10)


def _write(ws, text, row, c1, c2, *, bold=False, size=10,
           halign="left", valign="center", wrap=True, fill=None):
    cell = ws.cell(row=row, column=c1, value=text)
    cell.font = Font(bold=bold, size=size)
    cell.alignment = Alignment(horizontal=halign, vertical=valign, wrap_text=wrap)
    cell.border = BORDER
    if fill:
        cell.fill = fill
    if c2 > c1:
        ws.merge_cells(start_row=row, end_row=row, start_column=c1, end_column=c2)
        for gc in range(c1 + 1, c2 + 1):
            c = ws.cell(row=row, column=gc)
            c.border = BORDER
            if fill:
                c.fill = fill


def _is_fullwidth(record: dict) -> bool:
    if record.get("_style") == "full_width":
        return True
    # Claude sometimes emits _style:"subheader" with _value and no column keys
    return "_value" in record and not any(k not in INTERNAL for k in record)


# ── Main ───────────────────────────────────────────────────────────────────
def json_to_xlsx(
    json_path: str,
    xlsx_path: str,
    *,
    column_widths: dict | None = None,
    blank_rows: int = 0,
    header: list | None = None,
    row_height: int = ROW_HEIGHT,
):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    table         = data.get("table", {})
    column_widths = column_widths if column_widths is not None else table.get("column_widths") or {}
    header        = header        if header        is not None else data.get("header") or []
    blank_rows    = blank_rows    or table.get("blank_rows", 0)
    records       = table.get("rows", [])
    col_names     = list(column_widths)

    wb = Workbook()
    ws = wb.active

    # ── Grid layout ───────────────────────────────────────────────────────
    # max_span from header rows drives the fine-grained column count (n_grid).
    # Each table column gets a proportional slice of those grid columns.
    header_rows = [[r] if isinstance(r, dict) else r for r in header]

    if header_rows:
        n_grid = max(
            sum(c.get("label_span", 1) + c.get("value_span", 1) for c in row)
            for row in header_rows
        )
        n_grid = max(n_grid, len(col_names))
    else:
        n_grid = len(col_names) or 1

    # Distribute n_grid proportionally among table columns by their widths.
    total_w = sum(column_widths.values()) or 1
    gc_spans: list[int] = []
    rem = n_grid
    for i, name in enumerate(col_names):
        if i == len(col_names) - 1:
            gc_spans.append(max(1, rem))
        else:
            s = max(1, round(column_widths[name] / total_w * n_grid))
            s = min(s, rem - (len(col_names) - i - 1))
            gc_spans.append(s)
            rem -= s

    gc_start: list[int] = []
    cur = 1
    for s in gc_spans:
        gc_start.append(cur)
        cur += s
    gc_end = [gc_start[i] + gc_spans[i] - 1 for i in range(len(col_names))]

    # Set Excel column widths.
    for i, name in enumerate(col_names):
        sub_w = column_widths[name] * COL_SCALE / gc_spans[i]
        for gc in range(gc_start[i], gc_end[i] + 1):
            ws.column_dimensions[get_column_letter(gc)].width = sub_w

    # ── Header ────────────────────────────────────────────────────────────
    excel_row = 0
    for grid_row in header_rows:
        excel_row += 1
        is_title = len(grid_row) == 1 and grid_row[0].get("value_span", 0) == 0
        h_mult   = max((c.get("height", 1) for c in grid_row), default=1)
        if is_title:
            h_mult = max(h_mult, 3)

        # Build (span, text, bold, size) segments.
        segs = []
        for cell in grid_row:
            ls = cell.get("label_span", 1)
            vs = cell.get("value_span", 1)
            sz = _font_size(cell.get("font_size", 2))
            bd = cell.get("bold", is_title)
            if ls > 0:
                segs.append((ls, cell.get("label", ""), bd, sz))
            if vs > 0:
                segs.append((vs, cell.get("value", ""), False, sz))

        # Greedy proportional allocation of segments to grid columns.
        rem_span = sum(s[0] for s in segs)
        rem_cols = n_grid
        col_cur  = 1
        for idx, (span, text, bold, size) in enumerate(segs):
            if idx == len(segs) - 1:
                count = rem_cols
            else:
                count = max(1, round(span / rem_span * rem_cols))
                count = min(count, rem_cols - (len(segs) - idx - 1))
            _write(ws, text, excel_row, col_cur, col_cur + count - 1,
                   bold=bold, size=size,
                   halign="center" if is_title else "left")
            col_cur  += count
            rem_cols -= count
            rem_span -= span

        ws.row_dimensions[excel_row].height = ROW_HEIGHT * h_mult

    # ── Table column headers ──────────────────────────────────────────────
    excel_row += 1
    for i, name in enumerate(col_names):
        _write(ws, name, excel_row, gc_start[i], gc_end[i],
               bold=True, halign="center", fill=GREY_FILL)
    ws.row_dimensions[excel_row].height = ROW_HEIGHT * 2

    # ── Table rows (in order) ─────────────────────────────────────────────
    for record in records:
        excel_row += 1
        style  = record.get("_style", "data")
        r_mult = record.get("_height", 1)

        if _is_fullwidth(record):
            text  = record.get("_value", "")
            h     = record.get("_height", 2)
            _write(ws, text, excel_row, 1, n_grid,
                   bold=True, size=12, halign="center")
            ws.row_dimensions[excel_row].height = ROW_HEIGHT * h
            continue

        row_fill = GREY_FILL if style == "subheader" else None
        for i, name in enumerate(col_names):
            cv   = record.get(name, "")
            text = _text(cv)
            bold = (cv.get("bold", False) if isinstance(cv, dict) else False) \
                   or style in ("total", "subheader")
            size = _font_size(cv.get("font_size", 2) if isinstance(cv, dict) else 2)
            wrap = cv.get("wrap", True)  if isinstance(cv, dict) else True
            _write(ws, text, excel_row, gc_start[i], gc_end[i],
                   bold=bold, size=size, wrap=wrap, fill=row_fill)

        ws.row_dimensions[excel_row].height = row_height * max(r_mult, 1)

    # ── Blank template rows ───────────────────────────────────────────────
    for _ in range(blank_rows):
        excel_row += 1
        for i in range(len(col_names)):
            _write(ws, "", excel_row, gc_start[i], gc_end[i])
        ws.row_dimensions[excel_row].height = row_height

    wb.save(xlsx_path)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Convert JSON table description to Excel")
    p.add_argument("json_path")
    p.add_argument("xlsx_path", nargs="?")
    args = p.parse_args()

    xlsx_path = args.xlsx_path or str(Path(args.json_path).with_suffix(".xlsx"))
    with open(args.json_path, encoding="utf-8") as f:
        data = json.load(f)
    table = data.get("table", {})
    json_to_xlsx(
        args.json_path, xlsx_path,
        column_widths=table.get("column_widths"),
        blank_rows=table.get("blank_rows", 0),
        header=data.get("header"),
        row_height={1: 15, 2: 30, 3: 45}.get(table.get("row_height", 1), 15),
    )


if __name__ == "__main__":
    main()
