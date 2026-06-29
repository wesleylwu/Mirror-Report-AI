"""Fill an Excel template from extracted JSON text (produced by JSONgen).

Scans pipeline/templates/*.json, picks the template whose title and
section_header match the extracted document, then writes every keyed cell.

Usage:
    python XLSXgen.py <json_path> [output.xlsx]
"""
import difflib
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

import re as _re

def _fmt_item_code(text: str, opts: dict | None = None) -> str:
    """Move type tokens (e.g. '999 購入', '100 中込') onto the code line.
    Handles both multiline input (\n-separated) and single-line input (space-separated).
    Spacing is controlled by format_options in the template."""
    if not text:
        return text
    opts = opts or {}
    code_to_type  = " " * opts.get("code_to_type_spaces", 8)
    type_internal = " " * opts.get("type_internal_spaces", 1)

    # Matches lines that are ONLY digits + one word (e.g. "999 購入", "100 中込")
    # Whole line is just a type token: "999 購入"
    type_pat      = _re.compile(r"^(\d+)\s+(\S+)$")
    code_pat      = _re.compile(r"^[A-Za-z][A-Za-z0-9]{3,}")
    # Type token at START of remainder, followed by more text: "999 購入 <name>"
    start_type_pat = _re.compile(r"^(\d+)\s+(\S+)\s+")
    # Type token at END of remainder: "<name> 999 購入"
    end_type_pat  = _re.compile(r"\s+(\d+)\s+(\S+)\s*$")

    code_line, type_token, name_lines = "", "", []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if code_pat.match(stripped) and not code_line:
            parts = stripped.split(None, 1)
            code_line = parts[0]  # only the code token (e.g. "GE0006280")
            if len(parts) > 1:
                remainder = parts[1].strip()
                # Check type token at START of remainder (CODE TYPE NAME order)
                m = start_type_pat.match(remainder)
                if m and len(f"{m.group(1)} {m.group(2)}") <= 12:
                    type_token = f"{m.group(1)}{type_internal}{m.group(2)}"
                    name_part = remainder[m.end():].strip()
                    if name_part:
                        name_lines.append(name_part)
                else:
                    # Check type token at END of remainder (CODE NAME TYPE order)
                    m = end_type_pat.search(remainder)
                    if m and len(f"{m.group(1)} {m.group(2)}") <= 12:
                        type_token = f"{m.group(1)}{type_internal}{m.group(2)}"
                        name_part = remainder[:m.start()].strip()
                        if name_part:
                            name_lines.append(name_part)
                    else:
                        name_lines.append(remainder)
        else:
            m = type_pat.match(stripped)
            if m and len(stripped) <= 12:
                type_token = f"{m.group(1)}{type_internal}{m.group(2).strip()}"
            else:
                name_lines.append(stripped)

    first_line = f"{code_line}{code_to_type}{type_token}" if type_token else code_line
    rest = "\n".join(name_lines)
    return f"{first_line}\n{rest}" if rest else first_line


_SIDES = {
    "thin":   Side(style="thin"),
    "medium": Side(style="medium"),
    None:     Side(style=None),
}


def _side(s):
    return _SIDES.get(s, Side(style=None))


def _border(spec: dict) -> Border:
    return Border(
        top=_side(spec.get("top")),
        bottom=_side(spec.get("bottom")),
        left=_side(spec.get("left")),
        right=_side(spec.get("right")),
    )


def _write_cell(ws, row: int, col: int, end_col: int, end_row: int,
                value: str, font_spec: dict, align_spec: dict, border_spec: dict):
    font = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 10))
    align = Alignment(
        horizontal=align_spec.get("h", "left"),
        vertical=align_spec.get("v", "center"),
        wrap_text=align_spec.get("wrap", True),
    )
    outer = _border(border_spec)
    no_side = Side(style=None)

    ws.cell(row=row, column=col, value=value or None)

    if end_col > col or end_row > row:
        ws.merge_cells(start_row=row, end_row=end_row, start_column=col, end_column=end_col)

    for r in range(row, end_row + 1):
        for c in range(col, end_col + 1):
            is_top    = r == row
            is_bottom = r == end_row
            is_left   = c == col
            is_right  = c == end_col
            cell = ws.cell(row=r, column=c)
            cell.font = Font(bold=font.bold, size=font.size)
            cell.alignment = Alignment(
                horizontal=align.horizontal,
                vertical=align.vertical,
                wrap_text=align.wrap_text,
            )
            cell.border = Border(
                top=outer.top       if is_top    else no_side,
                bottom=outer.bottom if is_bottom else no_side,
                left=outer.left     if is_left   else no_side,
                right=outer.right   if is_right  else no_side,
            )


def _fuzzy_get(d: dict, key: str, cutoff: float = 0.45,
               _used: set | None = None) -> str:
    """Return d[key] if it exists, otherwise return the value whose key best
    matches `key` by sequence similarity (above cutoff). Returns '' if nothing
    matches well enough. Pass a shared `_used` set to prevent the same source
    key from being consumed by two different template keys."""
    if key in d:
        return d[key]
    candidates = [k for k in d.keys() if _used is None or k not in _used]
    matches = difflib.get_close_matches(key, candidates, n=1, cutoff=cutoff)
    if matches:
        if _used is not None:
            _used.add(matches[0])
        return d[matches[0]]
    return ""


# ── Template discovery ────────────────────────────────────────────────────────

def _load_templates() -> list[dict]:
    templates_dir = Path(__file__).parent / "templates"
    templates = []
    for path in sorted(templates_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            templates.append(json.load(f))
    return templates


def _match_template(data: dict, templates: list[dict]) -> dict:
    title   = (data.get("title") or "").strip()
    section = (data.get("section_header") or "").strip()

    for tmpl in templates:
        m = tmpl.get("match", {})
        t_title   = (m.get("title") or "").strip()
        t_section = (m.get("section_header") or "").strip()
        if t_title == title and t_section == section:
            return tmpl

    # Fallback: match on title only
    for tmpl in templates:
        m = tmpl.get("match", {})
        if (m.get("title") or "").strip() == title:
            return tmpl

    # Last resort fallback: default to the first template if available
    if templates:
        import sys
        print(
            f"Warning: No template found for title={title!r} section={section!r}. "
            f"Falling back to default template: {templates[0].get('id')}",
            file=sys.stderr
        )
        return templates[0]

    raise ValueError(
        f"No template found for title={title!r} section={section!r}. "
        f"Available: {[t.get('id') for t in templates]}"
    )


# ── Sheet builder ─────────────────────────────────────────────────────────────

def fill_template(tmpl: dict, data: dict, ws) -> None:
    header_vals = data.get("header", {})
    table       = data.get("table", {})
    table_rows  = table.get("rows", [])

    # Column widths
    for col_letter, width in tmpl.get("column_widths", {}).items():
        ws.column_dimensions[col_letter].width = width

    # ── Header rows ───────────────────────────────────────────────────────────
    _used_header_keys: set = set()
    for row_spec in tmpl.get("header", []):
        r = row_spec["row"]
        ws.row_dimensions[r].height = row_spec.get("height", 15)
        for cell in row_spec["cells"]:
            if cell.get("fixed"):
                value = cell.get("value", "")
            else:
                value = _fuzzy_get(header_vals, cell.get("key", ""),
                                   _used=_used_header_keys)
            _write_cell(
                ws, r, cell["col"], cell["end_col"], r,
                value, cell["font"], cell["align"], cell["border"],
            )

    # ── Column headers (span two rows) ────────────────────────────────────────
    ch = tmpl.get("col_headers", {})
    r1 = ch.get("start_row", 0)
    r2 = ch.get("end_row", r1)
    heights = ch.get("row_heights", [15, 15])
    if r1:
        ws.row_dimensions[r1].height = heights[0] if heights else 15
    if r2 and r2 != r1:
        ws.row_dimensions[r2].height = heights[1] if len(heights) > 1 else 15
    for cell in ch.get("cells", []):
        _write_cell(
            ws, r1, cell["col"], cell["end_col"], r2,
            cell["value"], cell["font"], cell["align"], cell["border"],
        )

    # ── Data rows ─────────────────────────────────────────────────────────────
    dr = tmpl.get("data_rows", {})
    start    = dr.get("start_row", r2 + 1 if r2 else 1)
    count    = dr.get("count", 0)
    row_h    = dr.get("row_height", 30)
    col_defs = dr.get("columns", [])

    # Column header names — used to filter out misidentified full_width rows
    col_header_names = {c["value"] for c in ch.get("cells", [])}

    # Strip any _full_width rows whose text is just a column header name
    table_rows = [
        rw for rw in table_rows
        if not ("_full_width" in rw and rw["_full_width"].strip() in col_header_names)
    ]

    # Number of rows to render: at least template count, expand for extra data
    data_count = len([rw for rw in table_rows if "_full_width" not in rw])
    n_rows = max(count, data_count)

    for i in range(n_rows):
        r = start + i
        ws.row_dimensions[r].height = row_h
        row_data = table_rows[i] if i < len(table_rows) else {}
        is_first = (i == 0)

        if "_full_width" in row_data:
            # Rare: full-width text row — write across all cols
            n_cols = tmpl.get("n_cols", 24)
            first_col = col_defs[0]["col"] if col_defs else 1
            last_col  = col_defs[-1]["end_col"] if col_defs else n_cols
            border_spec = col_defs[0].get("border", {}) if col_defs else {}
            _write_cell(
                ws, r, first_col, last_col, r,
                row_data["_full_width"],
                {"bold": False, "size": 10},
                {"h": "center", "v": "center", "wrap": True},
                border_spec,
            )
            continue

        for col_def in col_defs:
            key         = col_def.get("key", "")
            value       = _fuzzy_get(row_data, key) if row_data else ""
            if col_def.get("format") == "item_code":
                value = _fmt_item_code(value, col_def.get("format_options"))
            border_spec = col_def.get("first_row_border", col_def["border"]) if is_first \
                          else col_def["border"]
            _write_cell(
                ws, r, col_def["col"], col_def["end_col"], r,
                value, col_def["font"], col_def["align"], border_spec,
            )

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = tmpl.get("footer")
    if footer:
        # If we added extra data rows, shift the footer down accordingly
        extra = max(0, n_rows - count)
        for cell in footer["cells"]:
            fr = footer["row"] + extra
            ws.row_dimensions[fr].height = footer.get("height", 30)
            _write_cell(
                ws, fr, cell["col"], cell["end_col"], fr,
                cell.get("value", ""),
                cell["font"], cell["align"], cell["border"],
            )


def json_to_xlsx(json_path: str, xlsx_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    wb = Workbook()
    default_sheet = wb.active

    pages = data.get("pages")
    if pages is None:
        pages = [data]

    templates = _load_templates()

    for idx, page_data in enumerate(pages):
        tmpl = _match_template(page_data, templates)
        title = page_data.get("title", f"Sheet {idx+1}")
        clean_title = _re.sub(r'[:\\/?*\[\]]', '', title)[:30].strip() or f"Page {idx+1}"

        # Ensure sheet name uniqueness
        orig_title = clean_title
        ctr = 1
        while clean_title in wb.sheetnames:
            suffix = f"_{ctr}"
            clean_title = orig_title[:30 - len(suffix)] + suffix
            ctr += 1

        ws = wb.create_sheet(title=clean_title)
        fill_template(tmpl, page_data, ws)

    if len(wb.worksheets) > 1:
        wb.remove(default_sheet)

    wb.save(xlsx_path)
    print(f"Saved {xlsx_path}", file=__import__('sys').stderr)


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
