"""Render an Excel workbook directly from JSONgen's extracted JSON.

No template matching: each page's title, header rows, and table are written
generically, in the order the data appears, with plain styling (bold title,
label/value header pairs, a bordered data table, autosized columns).

Usage:
    python XLSXgen.py <json_path> [output.xlsx]
"""
import json
import re as _re
import sys
import unicodedata as _ud
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _vwidth(s: str) -> int:
    """Approximate rendered width: full-width/wide chars count as 2, others 1."""
    return sum(2 if _ud.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


_THIN = Side(style="thin")
_BORDER_ALL = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)


_NAMED_FILLS = {
    "none": None,
    "light_gray": "EDEDED",
    "light_blue": "D9E1F2",
    "light_yellow": "FFF2CC",
    "light_green": "E2EFDA",
    "light_orange": "FCE4D6",
}


def _set_cell(ws, row: int, col: int, value, *, bold: bool = False, size: int = 10,
              h: str = "left", v: str = "center", wrap: bool = False,
              border: bool = False, end_col: int | None = None, end_row: int | None = None,
              fill: str | None = None) -> None:
    if isinstance(value, (dict, list)):
        value = None
    else:
        value = value or None
    is_negative = isinstance(value, str) and value.strip().startswith("-")
    end_col = end_col or col
    end_row = end_row or row
    ws.cell(row=row, column=col, value=value)
    if end_col > col or end_row > row:
        ws.merge_cells(start_row=row, end_row=end_row, start_column=col, end_column=end_col)
    for r in range(row, end_row + 1):
        for c in range(col, end_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(bold=bold, size=size, color="FF0000" if is_negative else "000000")
            cell.alignment = Alignment(horizontal=h, vertical=v, wrap_text=wrap)
            if border:
                cell.border = _BORDER_ALL
            if fill:
                cell.fill = PatternFill(start_color=fill, end_color=fill, fill_type="solid")


def render_sheet(data: dict, ws) -> None:
    """Write title, header rows, and table directly from extracted JSON — no
    template lookup, everything rendered positionally in the order it appears."""
    title = data.get("title") or ""
    section = data.get("section_header") or ""
    header_rows = data.get("header") or []
    table = data.get("table") or {}
    columns = table.get("columns") or []
    rows = table.get("rows") or []

    # Drop blank spacer cells (label AND value both empty) — they only exist
    # upstream to keep extraction positionally consistent, not to occupy cells.
    rendered_header_rows: list[list[tuple[str, str]]] = []
    for row in header_rows:
        pairs = [
            ((cell or {}).get("label", ""), (cell or {}).get("value", ""))
            for cell in (row or [])
            if (cell or {}).get("label") or (cell or {}).get("value")
        ]
        rendered_header_rows.append(pairs)

    n_cols = max([len(columns), 1] + [len(pairs) * 2 for pairs in rendered_header_rows])

    r = 1
    if title:
        ws.row_dimensions[r].height = 22
        _set_cell(ws, r, 1, title, bold=True, size=14, h="center", end_col=n_cols)
        r += 1
    if section:
        ws.row_dimensions[r].height = 18
        _set_cell(ws, r, 1, section, bold=True, size=12, h="center", end_col=n_cols)
        r += 1

    LINE_H = 15  # points per line of text

    def _row_h(*values) -> float:
        max_lines = max(
            (str(v).count("\n") + 1 for v in values if v is not None and str(v)),
            default=1,
        )
        return max_lines * LINE_H

    for pairs in rendered_header_rows:
        all_vals = [s for label, value in pairs for s in (label, value)]
        ws.row_dimensions[r].height = _row_h(*all_vals)
        c = 1
        for label, value in pairs:
            _set_cell(ws, r, c, label, bold=True, size=10, h="right")
            _set_cell(ws, r, c + 1, value, size=10, h="left")
            c += 2
        r += 1

    r += 1  # blank separator row before the table

    if columns:
        ws.row_dimensions[r].height = _row_h(*columns)
        for c, name in enumerate(columns, start=1):
            _set_cell(ws, r, c, name, bold=True, h="center", border=True)
        r += 1

    def _unwrap(row):
        """Strip any extra single-element list wrappers the model adds around a row.
        Stops when the inner value is a scalar or a multi-element list."""
        while (
            isinstance(row, list)
            and len(row) == 1
            and not isinstance(row[0], (str, int, float, type(None)))
        ):
            row = row[0]
        return row

    rows = [_unwrap(r) for r in rows]

    # First pass: collect style from the first occurrence of each tag
    tag_styles: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict) and "_tag" in row and "_style" in row:
            tag = row["_tag"]
            if tag not in tag_styles:
                s = row["_style"] or {}
                tag_styles[tag] = {
                    "bold": bool(s.get("bold", False)),
                    "fill": _NAMED_FILLS.get(s.get("fill", "none")),
                    "h": s.get("align", "left"),
                }

    table_width = max(len(columns), 1)
    for row in rows:
        if isinstance(row, dict) and "_full_width" in row:
            ws.row_dimensions[r].height = _row_h(row["_full_width"])
            _set_cell(ws, r, 1, row["_full_width"], bold=True, h="center", wrap=True,
                      border=True, end_col=table_width)
        elif isinstance(row, dict) and "_tag" in row:
            raw = row.get("values") or []
            cells = [c if isinstance(c, (str, int, float)) else "" for c in raw]
            ws.row_dimensions[r].height = _row_h(*cells)
            style = tag_styles.get(row["_tag"], {"bold": False, "fill": None, "h": "left"})
            for c in range(1, table_width + 1):
                value = cells[c - 1] if c - 1 < len(cells) else ""
                _set_cell(ws, r, c, value, bold=style["bold"], h=style["h"],
                          wrap=True, border=True, fill=style["fill"])
        else:
            raw = row if isinstance(row, list) else []
            cells = [c if isinstance(c, (str, int, float)) else "" for c in raw]
            ws.row_dimensions[r].height = _row_h(*cells)
            for c in range(1, table_width + 1):
                value = cells[c - 1] if c - 1 < len(cells) else ""
                _set_cell(ws, r, c, value, wrap=True, border=True)
        r += 1

    # Column widths — autosized from header + table content.
    # Measure the longest *line* within each cell (split on \n) after collapsing
    # runs of spaces so padded OCR text doesn't inflate column widths.
    def _measure(s: str) -> int:
        s = str(s)
        return max((_vwidth(" ".join(line.split())) for line in s.splitlines()), default=0)

    widths: dict[int, int] = {}
    for c, name in enumerate(columns, start=1):
        widths[c] = max(widths.get(c, 0), _measure(name))
    for row in rows:
        if isinstance(row, dict) and "_tag" in row:
            raw = row.get("values") or []
            cells = [c if isinstance(c, (str, int, float)) else "" for c in raw]
        elif isinstance(row, dict):
            continue
        else:
            cells = row if isinstance(row, list) else []
        for c, value in enumerate(cells, start=1):
            widths[c] = max(widths.get(c, 0), _measure(str(value)))
    for c, w in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = max(6, w + 2)


def json_to_xlsx(json_path: str, xlsx_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    wb = Workbook()
    default_sheet = wb.active

    pages = data.get("pages")
    if pages is None:
        pages = [data]

    for idx, page_data in enumerate(pages):
        title = page_data.get("title", f"Sheet {idx+1}")
        clean_title = _re.sub(r'[:\\/?*\[\]]', '', title)[:30].strip() or f"Page {idx+1}"

        orig_title = clean_title
        ctr = 1
        while clean_title in wb.sheetnames:
            suffix = f"_{ctr}"
            clean_title = orig_title[:30 - len(suffix)] + suffix
            ctr += 1

        ws = wb.create_sheet(title=clean_title)
        render_sheet(page_data, ws)

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
