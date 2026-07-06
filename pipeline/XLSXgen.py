"""Render an Excel workbook from JSON produced by JSONgen.

Supports two formats:
  - New (code-based): page has a "code" key with a build_template(ws) function
  - Legacy (JSON schema): page has a "template" key with cell-grid JSON

Each page becomes a worksheet.

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
from openpyxl.utils import get_column_letter, range_boundaries


_THIN = Side(style="thin")
_BORDER_ALL = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)
_BORDER_NONE = Border()

# A4 usable column width in Excel char units (0.5" margins, Calibri 11pt)
_A4_PORTRAIT_COLS  = 100.0
_A4_LANDSCAPE_COLS = 128.0


class _NullCell:
    """Stand-in for a MergedCell position — silently swallows all writes."""
    def __setattr__(self, name, value): pass
    def __getattr__(self, name): return None


def _guard(obj):
    """Replace MergedCell instances with _NullCell, recursively for tuples."""
    if isinstance(obj, MergedCell):
        return _NullCell()
    if isinstance(obj, tuple):
        return tuple(_guard(item) for item in obj)
    return obj


class _SafeWS:
    """Proxy around openpyxl Worksheet that turns MergedCell access into no-ops.

    Claude-generated code often writes to every cell in a range (e.g. to apply
    borders) without checking whether cells are inside a merge region. This proxy
    intercepts those writes and drops them silently so execution continues.
    """
    __slots__ = ("_ws",)

    def __init__(self, ws):
        object.__setattr__(self, "_ws", ws)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_ws"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_ws"), name, value)

    def cell(self, row=None, column=None, value=None, **kw):
        ws = object.__getattribute__(self, "_ws")
        c = ws.cell(row=row, column=column)
        if isinstance(c, MergedCell):
            return _NullCell()
        if value is not None:
            c.value = value
        return c

    def __getitem__(self, key):
        return _guard(object.__getattribute__(self, "_ws")[key])

    def __setitem__(self, key, value):
        ws = object.__getattribute__(self, "_ws")
        if not isinstance(ws[key], MergedCell):
            ws[key] = value

    def iter_rows(self, **kw):
        for row in object.__getattribute__(self, "_ws").iter_rows(**kw):
            yield tuple(_NullCell() if isinstance(c, MergedCell) else c for c in row)

    def iter_cols(self, **kw):
        for col in object.__getattribute__(self, "_ws").iter_cols(**kw):
            yield tuple(_NullCell() if isinstance(c, MergedCell) else c for c in col)

    def merge_cells(self, range_string=None, start_row=None, end_row=None,
                    start_column=None, end_column=None):
        # Normalize range_string to row/col coords
        if range_string is not None:
            try:
                sc, sr, ec, er = range_boundaries(str(range_string).upper())
                start_row, end_row, start_column, end_column = sr, er, sc, ec
            except Exception:
                return

        if start_row is None:
            return

        # Single-cell merges are invalid OOXML
        if start_row == end_row and start_column == end_column:
            return

        ws = object.__getattribute__(self, "_ws")

        # Overlapping merges corrupt the file — openpyxl silently writes both,
        # producing invalid XML. Skip any range that touches an existing merge.
        for existing in ws.merged_cells.ranges:
            if not (end_row < existing.min_row or start_row > existing.max_row or
                    end_column < existing.min_col or start_column > existing.max_col):
                return

        try:
            ws.merge_cells(start_row=start_row, end_row=end_row,
                           start_column=start_column, end_column=end_column)
        except Exception:
            pass


def _post_process_sheet(ws) -> None:
    """Hide trailing empty cells, clear spacer borders, fix text wrapping and accidental fills."""
    max_col = ws.max_column or 1
    max_row = ws.max_row or 1

    # Build a set of (row, col) pairs that are anchors of full-width merges
    # (e.g. the title row A1:O1). These carry a value but shouldn't count
    # as real column content — they're just the storage cell for the title.
    half_cols = (max_col or 1) // 2
    full_width_anchors: set = set()
    for mr in ws.merged_cells.ranges:
        if (mr.max_col - mr.min_col) >= half_cols:
            full_width_anchors.add((mr.min_row, mr.min_col))

    # Find the real content boundary.
    # full_width_anchors are excluded from column tracking (so title merges don't
    # inflate eff_max_col) but their ROWS still count toward eff_max_row.
    content_rows: set = set()
    content_cols: set = set()
    for row in ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
        for cell in row:
            if isinstance(cell, MergedCell):
                continue
            if (cell.row, cell.column) in full_width_anchors:
                content_rows.add(cell.row)   # row counts, column does not
                continue
            if cell.value is not None or (cell.fill and cell.fill.fill_type == "solid"):
                content_rows.add(cell.row)
                content_cols.add(cell.column)

    eff_max_row = max(content_rows) if content_rows else max_row
    eff_max_col = max(content_cols) if content_cols else max_col

    # Hide rows/cols entirely outside the content boundary.
    # Also unhide everything inside — Claude sometimes hides blank data rows.
    for r in range(1, eff_max_row + 1):
        ws.row_dimensions[r].hidden = False
    for r in range(eff_max_row + 1, max_row + 1):
        ws.row_dimensions[r].hidden = True
    for c in range(eff_max_col + 1, max_col + 1):
        ws.column_dimensions[get_column_letter(c)].hidden = True

    # Strip borders from spacer columns: narrow (≤ 6 chars) + no real values
    # + not interior of a merge. Full-width merge anchors don't disqualify a column.
    for c in range(1, eff_max_col + 1):
        if float(ws.column_dimensions[get_column_letter(c)].width or 8.43) > 6.0:
            continue
        is_spacer = True
        for r in range(1, eff_max_row + 1):
            cell = ws.cell(row=r, column=c)
            if isinstance(cell, MergedCell):
                is_spacer = False
                break
            if cell.value is not None and (r, c) not in full_width_anchors:
                is_spacer = False
                break
        if is_spacer:
            for r in range(1, eff_max_row + 1):
                cell = ws.cell(row=r, column=c)
                if not isinstance(cell, MergedCell):
                    cell.border = _BORDER_NONE

    # Scale columns to fit the page width (columns only — row scaling distorts proportions)
    orientation = (getattr(ws.page_setup, "orientation", None) or "portrait").lower()
    target_cols = _A4_LANDSCAPE_COLS if orientation == "landscape" else _A4_PORTRAIT_COLS
    col_widths = [
        float(ws.column_dimensions[get_column_letter(c)].width or 8.43)
        for c in range(1, eff_max_col + 1)
    ]
    raw_col_total = sum(col_widths) or 1.0
    col_scale = min(1.0, target_cols / raw_col_total)
    if col_scale < 1.0:
        for c, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(c)].width = max(2.0, w * col_scale)

        # Pre-process pos_values:
        # Case A: If Column 1 (index 1, "原単位") is ONLY a type token (like "100 仕込" or "999 購入"),
        # and Column 2 (index 2, "分量") contains the unit value and the quantity merged (like "100.0000\n400.72\nkg"),
        # correct the OCR column alignment shift.
        # Case B: If Column 1 contains both the type token and the unit value (like "999 購入\n89.8383"),
        # move the type token to Column 0.
        if len(pos_values) > 1 and pos_values[0]:
            has_item_code = any(cd.get("col_index") == 0 and cd.get("format") == "item_code" for cd in col_defs)
            if has_item_code:
                val0 = str(pos_values[0])
                val1 = str(pos_values[1]) if len(pos_values) > 1 else ""
                val2 = str(pos_values[2]) if len(pos_values) > 2 else ""
                type_pat = _re.compile(r"^(\d+)\s+(\S+)$")
                
                # Check for Case A: Column 1 is just a type token, Column 2 has merged lines
                is_type_token = bool(type_pat.match(val1.strip()))
                val2_lines = [l.strip() for l in val2.split("\n") if l.strip()]
                is_val2_split = False
                if len(val2_lines) >= 2:
                    first_is_num = bool(_re.match(r"^\d+(\.\d+)?$", val2_lines[0]))
                    second_has_num = bool(_re.search(r"\d+", val2_lines[1]))
                    is_val2_split = first_is_num and second_has_num

                if is_type_token and is_val2_split:
                    # Move type token from Col 1 to Col 0
                    pos_values[0] = val0 + "\n" + val1.strip()
                    # Move unit value from Col 2 to Col 1
                    pos_values[1] = val2_lines[0]
                    # Keep remaining lines in Col 2
                    pos_values[2] = "\n".join(val2_lines[1:])
                else:
                    # Case B: Standard extraction from Column 1
                    val1_lines = val1.split("\n")
                    cleaned_val1_lines = []
                    extracted_types = []
                    for line in val1_lines:
                        stripped = line.strip()
                        if type_pat.match(stripped) and len(stripped) <= 12:
                            extracted_types.append(stripped)
                        else:
                            cleaned_val1_lines.append(line)
                    if extracted_types:
                        pos_values[1] = "\n".join(cleaned_val1_lines).strip()
                        pos_values[0] = val0 + "\n" + "\n".join(extracted_types)

        for col_def in col_defs:
            if "col_index" in col_def:
                idx = col_def["col_index"]
                value = pos_values[idx] if idx < len(pos_values) else ""
            else:
                key   = col_def.get("key", "")
                value = _fuzzy_get(row_data, key) if row_data else ""
            if col_def.get("format") == "item_code":
                value = _fmt_item_code(value, col_def.get("format_options"))
            border_spec = col_def.get("first_row_border", col_def["border"]) if is_first \
                          else col_def["border"]
            if is_last and tmpl.get("id") == "課別基準客先別売上粗利":
                border_spec = dict(border_spec)
                border_spec["bottom"] = "medium"
            _write_cell(
                ws, r, col_def["col"], col_def["end_col"], r,
                value, col_def["font"], col_def["align"], border_spec,
                fill_spec=last_row_fill,
            )
            # Strip accidental white fills
            f = cell.fill
            if (f is not None and f.fill_type == "solid"
                    and str(f.fgColor.rgb).upper() in _WHITE):
                cell.fill = PatternFill(fill_type=None)


def execute_code(code: str, ws) -> None:
    """Execute a Claude-generated build_template(ws) function in place."""
    ns: dict = {}
    exec(compile(code, "<claude_generated>", "exec"), ns)  # noqa: S102
    fn = ns.get("build_template")
    if callable(fn):
        fn(_SafeWS(ws))
    _post_process_sheet(ws)


def render_sheet(data: dict, ws) -> None:
    col_widths = data.get("col_widths") or []
    rows       = data.get("rows") or []
    orientation = str(data.get("orientation") or "portrait").lower()

    # Rows index — support both short (r/h) and long field names
    num_rows = int(data.get("num_rows") or len(rows))
    row_by_r: dict[int, dict] = {}
    for idx, row in enumerate(rows):
        r = row.get("r") or row.get("row") or (idx + 1)
        row_by_r[int(r)] = row

    # Pre-compute raw heights for all rows (needed for scaling)
    raw_heights = []
    for r in range(1, num_rows + 1):
        row = row_by_r.get(r, {})
        try:
            raw_heights.append(float(row.get("h") or row.get("height") or 15))
        except (ValueError, TypeError):
            raw_heights.append(15.0)

    # Scale factors so the sheet fills one A4 page
    if orientation == "landscape":
        target_cols = _A4_LANDSCAPE_COLS
        target_rows = _A4_LANDSCAPE_ROWS
    else:
        target_cols = _A4_PORTRAIT_COLS
        target_rows = _A4_PORTRAIT_ROWS

    raw_col_total = sum(max(1.0, float(w)) for w in col_widths) if col_widths else 1.0
    col_scale = target_cols / raw_col_total

    raw_row_total = sum(raw_heights) or 1.0
    row_scale = target_rows / raw_row_total

    # Apply scaled column widths
    for i, w in enumerate(col_widths, start=1):
        try:
            ws.column_dimensions[get_column_letter(i)].width = max(2, float(w) * col_scale)
        except (ValueError, TypeError):
            ws.column_dimensions[get_column_letter(i)].width = 8

    # Apply scaled row heights and render cells
    for row_idx in range(1, num_rows + 1):
        row    = row_by_r.get(row_idx, {})
        height = max(5.0, raw_heights[row_idx - 1] * row_scale)
        ws.row_dimensions[row_idx].height = height

        for cell_spec in (row.get("cells") or []):
            try:
                col = int(cell_spec.get("c") or cell_spec.get("col") or 1)
                span = max(1, int(cell_spec.get("s") or cell_spec.get("span") or 1))
            except (ValueError, TypeError):
                col, span = 1, 1

            # Skip if this position is already inside a previous merge
            top_left = ws.cell(row=row_idx, column=col)
            if isinstance(top_left, MergedCell):
                continue

            value = cell_spec.get("v") or cell_spec.get("value") or None
            bold = bool(cell_spec.get("b") or cell_spec.get("bold") or False)
            align = cell_spec.get("a") or cell_spec.get("align") or "left"
            fill_hex = cell_spec.get("f") or cell_spec.get("fill")
            border_style = "all" if cell_spec.get("x") else (cell_spec.get("border") or "none")
            end_col = col + span - 1

            top_left.value = value

            if span > 1:
                try:
                    ws.merge_cells(
                        start_row=row_idx, end_row=row_idx,
                        start_column=col, end_column=end_col,
                    )
                except Exception:
                    pass

            font      = Font(bold=bold)
            alignment = Alignment(horizontal=align, vertical="center")
            border    = _BORDER_ALL if border_style == "all" else _BORDER_NONE
            fill      = None
            if fill_hex:
                hex_val = str(fill_hex).lstrip("#")
                if len(hex_val) == 6:
                    try:
                        fill = PatternFill(
                            start_color=hex_val, end_color=hex_val, fill_type="solid"
                        )
                    except Exception:
                        pass

            for c in range(col, end_col + 1):
                cell = ws.cell(row=row_idx, column=c)
                if isinstance(cell, MergedCell):
                    continue  # non-top-left cells in a merge are read-only
                cell.font      = font
                cell.alignment = alignment
                cell.border    = border
                if fill:
                    cell.fill = fill

    # Page setup — A4, correct orientation, fit to one page
    ws.page_setup.paperSize  = 9  # A4
    ws.page_setup.orientation = orientation
    ws.page_setup.fitToPage  = True
    ws.page_setup.fitToWidth = 1
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

        code = page_data.get("code", "")
        if code:
            # New code-based approach — extract sheet name from code if present
            m = re.search(r'ws\.title\s*=\s*["\']([^"\']+)["\']', code)
            raw_name = m.group(1) if m else f"Sheet {idx + 1}"
            ws = wb.create_sheet(title=_unique_name(raw_name, seen))
            try:
                execute_code(code, ws)
            except Exception as e:
                print(f"Code execution failed for page {idx + 1}: {e}", file=sys.stderr)
        else:
            # Legacy JSON template approach
            tmpl = page_data.get("template") or page_data
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
