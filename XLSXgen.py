"""Convert a JSON array of objects into a new Excel spreadsheet.

Usage:
    python XLSXgen.py <input.json> [output.xlsx] [--column-width N] [--row-height N]

If no output path is given, the spreadsheet is written next to the
input file with the same name and a .xlsx extension.
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

CHECKBOX_FORMAT = '"☑";;"☐"'
DEFAULT_COLUMN_WIDTH = 20
DEFAULT_ROW_HEIGHT = 15

# Unicode blocks for scripts that read right-to-left.
_RTL_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0700, 0x074F),  # Syriac
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB1D, 0xFB4F),  # Hebrew presentation forms
    (0xFB50, 0xFDFF),  # Arabic presentation forms A
    (0xFE70, 0xFEFF),  # Arabic presentation forms B
)

# A number immediately followed by a short trailing unit word, e.g. "360.00
# kg" or "24 lbs" -- split onto its own line so the unit doesn't get crammed
# next to the number in a narrow numeric column.
_NUMBER_UNIT_PATTERN = re.compile(r"^(-?[\d,]*\.?\d+)\s+([^\s\d][^\s]*)$")

# Two or more consecutive spaces inside a value usually means the source data
# was manually column-aligned with spaces (e.g. a code padded out to line up
# with a label after it). A proportional font breaks that alignment, so such
# cells get a monospace font instead, only when this pattern is detected.
_MULTI_SPACE_PATTERN = re.compile(r" {2,}")
MONOSPACE_FONT = Font(name="Consolas")

# Sentinel JSON value marking a cell whose source text couldn't be read at
# all (as opposed to a value that was legibly read as zero). The cell is left
# blank but filled red, so an illegible source field stays visually distinct
# from a genuine zero instead of silently looking the same.
ILLEGIBLE = "<ILLEGIBLE>"
ILLEGIBLE_FILL = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")

HEADER_FONT = Font(bold=True, color="000000")
TOTAL_FONT = Font(bold=True)
TOTAL_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
SUBHEADER_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
# Single-line cells vertically center within a row that's been resized taller
# to fit a wrapped neighbor, rather than sticking to the top. Cells that wrap
# *themselves* stay top-aligned instead, so their own first line starts at
# the top of the row and reads down naturally.
DATA_ALIGNMENT = Alignment(vertical="center")
MULTILINE_ALIGNMENT = Alignment(wrap_text=True, vertical="top")
MULTILINE_RTL_ALIGNMENT = Alignment(wrap_text=True, vertical="top", horizontal="right", readingOrder=2)
RTL_ALIGNMENT = Alignment(vertical="center", horizontal="right", readingOrder=2)
THIN_SIDE = Side(style="thin")
THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
# A heavier border for the table's outer perimeter and the line separating the
# header from the data, so the grid reads with the same visual weight as a
# printed form's frame, instead of every line being the same thin weight.
MEDIUM_SIDE = Side(style="medium")


def _table_border(row: int, col: int, last_col: int, bottom_row: int, table_start: int = 1) -> Border:
    """Border for a cell at (row, col) in a table whose outer edge runs from
    `table_start`/col 1 to `bottom_row`/`last_col`, with a heavier line separating
    the header (rows table_start and table_start+1) from the data (row table_start+2+) too.
    Must be computed once and assigned once -- openpyxl silently drops a *second* `.border =`
    assignment to the same cell, and separately drops border sides set on a
    cell that isn't the top-left "anchor" of a merged range (so this can't
    be applied as a touch-up pass after the fact, and the header/data
    separator is implemented as row table_start+2's top edge rather than table_start+1's bottom
    edge, since header cells are routinely merge non-anchors but data rows never are)."""
    return Border(
        left=MEDIUM_SIDE if col == 1 else THIN_SIDE,
        right=MEDIUM_SIDE if col == last_col else THIN_SIDE,
        top=MEDIUM_SIDE if row in (table_start, table_start + 2) else THIN_SIDE,
        bottom=MEDIUM_SIDE if row == bottom_row else THIN_SIDE,
    )


def _display_width(text: str) -> int:
    """Count display width treating East Asian wide/fullwidth characters
    (Chinese, Japanese, Korean, full-width forms, most emoji) as 2 columns
    wide, since Excel renders them roughly twice as wide as Latin letters."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _is_rtl(text: str) -> bool:
    """True if `text` is predominantly Hebrew/Arabic/Syriac script, so it
    should be right-aligned with right-to-left reading order."""
    rtl_count = sum(1 for ch in text if any(start <= ord(ch) <= end for start, end in _RTL_RANGES))
    letters = sum(1 for ch in text if ch.isalpha())
    return letters > 0 and rtl_count > letters / 2


def _split_trailing_unit(text: str) -> str:
    """If `text` is a number directly followed by a short unit-like word
    (e.g. "360.00 kg"), move the unit onto its own line. Multi-line values
    and values with more than one space-separated word after the number are
    left alone, so this only fires for the simple "<number> <unit>" shape."""
    if "\n" in text:
        return text
    match = _NUMBER_UNIT_PATTERN.match(text)
    return f"{match.group(1)}\n{match.group(2)}" if match else text


def _wrapped_line_count(text: str, column_width: int) -> int:
    """Estimate how many visual lines `text` will occupy once Excel wraps it
    to fit `column_width`: each explicit newline starts a new line, and any
    segment longer than the column (in display width, so wide scripts like
    CJK count double) wraps into multiple lines on its own."""
    lines = 0
    for segment in text.split("\n"):
        lines += max(1, -(-_display_width(segment) // column_width))  # ceil division
    return lines


def _flatten(record: dict, prefix: str = "") -> tuple[dict, set]:
    """Flatten nested dicts into dot-notated keys. A list of strings is
    treated as a set of flags: each item becomes its own True/False column
    (e.g. Tags: ["vip"] -> Tags.vip = True), tracked in the returned flag-key
    set so missing flags can default to False rather than blank."""
    flat = {}
    flag_keys = set()
    for key, value in record.items():
        flat_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            sub_flat, sub_flag_keys = _flatten(value, flat_key)
            flat.update(sub_flat)
            flag_keys.update(sub_flag_keys)
        elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            for item in value:
                item_key = f"{flat_key}.{item}"
                flat[item_key] = True
                flag_keys.add(item_key)
        elif isinstance(value, list):
            flat[flat_key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[flat_key] = value
    return flat, flag_keys


def _group_headers(flat_records: list[dict]) -> list[tuple[str | None, list[str]]]:
    """Group dot-notated keys by their top-level prefix, gathering every key
    for a given prefix into one group regardless of where it first appears."""
    group_order: list[str] = []
    group_headers: dict[str, list[str]] = {}
    for record in flat_records:
        for key in record:
            top = key.split(".", 1)[0] if "." in key else key
            if top not in group_headers:
                group_headers[top] = []
                group_order.append(top)
            if key not in group_headers[top]:
                group_headers[top].append(key)

    groups = []
    for top in group_order:
        keys = group_headers[top]
        is_nested = "." in keys[0]
        groups.append((top if is_nested else None, keys))
    return groups


def json_to_xlsx(
    json_path: str,
    xlsx_path: str,
    column_width: float = DEFAULT_COLUMN_WIDTH,
    row_height: float = DEFAULT_ROW_HEIGHT,
    footer: str | None = None,
    column_widths: dict[str, float] | None = None,
    column_alignments: dict[str, str] | None = None,
    column_vertical_alignments: dict[str, str] | None = None,
    column_number_formats: dict[str, str] | None = None,
    column_fills: dict[str, str] | None = None,
    row_fills: dict[int, str] | None = None,
    column_font_colors: dict[str, str] | None = None,
    row_font_colors: dict[int, str] | None = None,
    row_number_formats: dict[int, str] | None = None,
    blank_rows: int = 0,
    header: list[dict[str, str]] | None = None,
) -> None:
    """`column_widths`, `column_alignments`, `column_vertical_alignments`,
    `column_number_formats`, `column_fills`, and `column_font_colors` are
    keyed by leaf header name (e.g. "City" for a nested "Address.City" field)
    and override the `column_width` default / the automatic horizontal/
    vertical alignment / Excel's default "General" number format / the
    (none) fill color / the default black text color for that one column --
    use them to match a physical form's column proportions, per-field text
    alignment (e.g. right-aligning a numeric column, or vertically centering
    a column whose paper counterpart is centered while its neighbors are
    top-aligned), fixed decimal precision (e.g. "0.0000" so a value like 100
    still displays as "100.0000" instead of Excel trimming the trailing
    zeros), shading (e.g. a light gray fill on a "totals" style column), and
    text color (e.g. red for a column of negative adjustments) -- fill/font
    colors are given as hex RGB strings like "D9D9D9" or "FF0000". This only
    colors/shades a cell when a color is actually given for that column/row;
    there's no automatic rule (e.g. nothing colors negative numbers red on
    its own). `row_fills`/`row_font_colors` are keyed by 1-indexed data row
    number (1 = the first record) instead, for shading/coloring whole rows --
    e.g. a summary/total row. `row_number_formats` is the row-keyed
    counterpart to `column_number_formats`, for tables where the metric type
    varies by row instead of by column (e.g. a transposed table with months
    as columns and a "growth rate" row that needs a "%" format while the
    other rows are plain currency) -- it takes precedence over a column-level
    format when both apply to the same cell. `blank_rows` adds that many
    empty rows after the data, still bordered and aligned like the data rows,
    matching a paper form's pre-printed empty rows reserved for entries to be
    filled in later by hand."""
    column_widths = column_widths or {}
    column_alignments = column_alignments or {}
    column_vertical_alignments = column_vertical_alignments or {}
    column_number_formats = column_number_formats or {}
    column_fills = column_fills or {}
    column_font_colors = column_font_colors or {}
    row_font_colors = row_font_colors or {}
    row_fills = row_fills or {}
    row_number_formats = row_number_formats or {}
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Support both the legacy flat array format and the new structured format.
    if isinstance(raw, list):
        records = raw
    else:
        records = raw.get("table", {}).get("rows", [])
        if not column_widths:
            column_widths = raw.get("table", {}).get("column_widths") or {}
        if not blank_rows:
            blank_rows = raw.get("table", {}).get("blank_rows", 0)
        if header is None:
            header = raw.get("header")

    # Normalise records: cell values may be plain strings or rich cell objects.
    # Strip internal keys before flattening so they don't become columns.
    INTERNAL_KEYS = {"_style", "_value", "_height", "_bg"}

    def _cell_text(cell_val) -> str:
        if isinstance(cell_val, dict):
            return cell_val.get("text", "")
        return cell_val if cell_val is not None else ""

    def _normalised_record(record: dict) -> dict:
        return {k: _cell_text(v) for k, v in record.items() if k not in INTERNAL_KEYS}

    flat_records = []
    flag_keys: set = set()
    for record in records:
        flat, record_flag_keys = _flatten(_normalised_record(record))
        flat_records.append(flat)
        flag_keys.update(record_flag_keys)

    groups = _group_headers(flat_records)
    headers = [header for _, group_keys in groups for header in group_keys]
    leaf_names = [header.rsplit(".", 1)[-1] for header in headers]
    col_widths = [column_widths.get(leaf, column_width) for leaf in leaf_names]

    wb = Workbook()
    ws = wb.active

    # Render the header key-value grid above the main table if present.
    # Each header row is a list of {"label", "value", "label_span", "value_span"} cells.
    # Label and value are rendered as separate adjacent cells.
    header_row_offset = 0
    if header:
        total_cols = len(headers)
        DEFAULT_LABEL_BG = "D9D9D9"

        def _make_fill(hex_color, default=None):
            color = hex_color if hex_color is not None else default
            if not color:
                return None
            return PatternFill(start_color=color, end_color=color, fill_type="solid")

        def _write_header_cell(text, row, col_start, col_end, bold=False, fill=None, align="left", font_size=2):
            sz = {1: 8, 2: 10, 3: 12}.get(font_size, 10)
            c = ws.cell(row=row, column=col_start, value=text)
            c.font = Font(bold=bold, size=sz)
            c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
            c.border = THIN_BORDER
            if fill:
                c.fill = fill
            if col_end > col_start:
                ws.merge_cells(start_row=row, end_row=row, start_column=col_start, end_column=col_end)
                for c2 in range(col_start + 1, col_end + 1):
                    cell2 = ws.cell(row=row, column=c2)
                    cell2.border = THIN_BORDER
                    if fill:
                        cell2.fill = fill

        for grid_row in header:
            if isinstance(grid_row, dict):
                grid_row = [grid_row]
            total_span = sum(
                cell_def.get("label_span", 1) + cell_def.get("value_span", 1)
                for cell_def in grid_row
            )
            col_cursor = 1
            row_height_mult = max((cd.get("height", 1) for cd in grid_row), default=1)
            for cell_def in grid_row:
                label    = cell_def.get("label", "")
                value    = cell_def.get("value", "")
                ls       = cell_def.get("label_span", 1)
                vs       = cell_def.get("value_span", 1)
                bold     = cell_def.get("bold", True)
                align    = cell_def.get("align", "left")
                font_sz  = cell_def.get("font_size", 2)
                # Use DEFAULT_LABEL_BG only when label_bg key is absent, not when explicitly null.
                lbg_val  = cell_def.get("label_bg", DEFAULT_LABEL_BG)
                lbg      = _make_fill(lbg_val)
                vbg      = _make_fill(cell_def.get("value_bg"))

                if ls > 0:
                    l_cols = max(1, round(ls / total_span * total_cols))
                    l_end  = min(col_cursor + l_cols - 1, total_cols)
                    _write_header_cell(label, header_row_offset + 1, col_cursor, l_end,
                                       bold=bold, fill=lbg, align=align, font_size=font_sz)
                    col_cursor = l_end + 1

                if vs > 0:
                    v_cols = max(1, round(vs / total_span * total_cols))
                    v_end  = min(col_cursor + v_cols - 1, total_cols)
                    _write_header_cell(value, header_row_offset + 1, col_cursor, v_end,
                                       bold=False, fill=vbg, align="left", font_size=font_sz)
                    col_cursor = v_end + 1

            if row_height_mult > 1:
                ws.row_dimensions[header_row_offset + 1].height = row_height * row_height_mult
            header_row_offset += 1
        header_row_offset += 1  # blank separator row

    R = header_row_offset  # shorthand offset so all table rows shift down cleanly
    col = 1
    for top, group_headers in groups:
        start_col = col
        if top is None:
            ws.cell(row=R + 1, column=start_col, value=group_headers[0])
            ws.merge_cells(start_row=R + 1, end_row=R + 2, start_column=start_col, end_column=start_col)
            col += 1
        else:
            ws.cell(row=R + 1, column=start_col, value=top)
            for header in group_headers:
                ws.cell(row=R + 2, column=col, value=header[len(top) + 1 :])
                col += 1
            if len(group_headers) > 1:
                ws.merge_cells(start_row=R + 1, end_row=R + 1, start_column=start_col, end_column=col - 1)
            else:
                ws.merge_cells(start_row=R + 1, end_row=R + 1, start_column=start_col, end_column=start_col)

    last_row = R + 2 + len(flat_records) + blank_rows
    last_col = len(headers)
    bottom_row = last_row + 1 if footer is not None else last_row
    # Build a set of leaf column names so we can detect header-duplicate rows.
    leaf_name_set = set(leaf_names)

    for record_index, record in enumerate(flat_records, start=1):
        raw_record = records[record_index - 1]
        row_index = record_index + R + 2
        line_count = 1
        row_style = raw_record.get("_style", "data")

        # Skip subheader rows that simply repeat the column headers — XLSXgen
        # already renders the header row from column_widths, so this would duplicate it.
        if row_style == "subheader":
            row_texts = {_cell_text(v) for k, v in raw_record.items() if k not in INTERNAL_KEYS}
            if row_texts <= leaf_name_set:
                continue

        if row_style == "full_width":
            text = raw_record.get("_value", "")
            cell = ws.cell(row=row_index, column=1, value=text)
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = _table_border(row_index, 1, last_col, bottom_row, table_start=R + 1)
            if last_col > 1:
                ws.merge_cells(start_row=row_index, end_row=row_index, start_column=1, end_column=last_col)
                for c in range(2, last_col + 1):
                    ws.cell(row=row_index, column=c).border = _table_border(row_index, c, last_col, bottom_row, table_start=R + 1)
            continue

        row_bg = raw_record.get("_bg")
        row_height_mult = raw_record.get("_height", 1)
        row_fill_color = row_bg or row_fills.get(record_index)

        for col_index, header in enumerate(headers, start=1):
            leaf = leaf_names[col_index - 1]
            this_column_width = col_widths[col_index - 1]

            # Pull per-cell style from rich cell object if present.
            raw_cell = raw_record.get(header, raw_record.get(leaf, ""))
            cell_props = raw_cell if isinstance(raw_cell, dict) else {}
            cell_align  = cell_props.get("align") or column_alignments.get(leaf)
            _raw_valign = cell_props.get("valign") or column_vertical_alignments.get(leaf)
            cell_valign = "center" if _raw_valign == "middle" else _raw_valign
            cell_bold   = cell_props.get("bold", False)
            cell_bg     = cell_props.get("bg") or row_fill_color or column_fills.get(leaf)
            cell_color  = cell_props.get("text_color") or row_font_colors.get(record_index) or column_font_colors.get(leaf)
            cell_wrap   = cell_props.get("wrap", None)

            illegible = False
            if header in flag_keys:
                value = 1 if flat_records[record_index - 1].get(header, False) else 0
                cell = ws.cell(row=row_index, column=col_index, value=value)
                cell.number_format = CHECKBOX_FORMAT
                cell.alignment = DATA_ALIGNMENT
            else:
                value = flat_records[record_index - 1].get(header)
                illegible = value == ILLEGIBLE
                if illegible:
                    value = None
                elif isinstance(value, str):
                    value = _split_trailing_unit(value)
                cell = ws.cell(row=row_index, column=col_index, value=value)

                # Determine wrapping and alignment.
                rtl = isinstance(value, str) and _is_rtl(value)
                should_wrap = cell_wrap if cell_wrap is not None else (
                    isinstance(value, str) and ("\n" in value or _display_width(value) > this_column_width)
                )
                if isinstance(value, str) and _MULTI_SPACE_PATTERN.search(value):
                    cell.font = MONOSPACE_FONT

                h_align = cell_align or ("right" if rtl else None)
                v_align = cell_valign or ("top" if should_wrap else "center")
                cell.alignment = Alignment(
                    horizontal=h_align,
                    vertical=v_align,
                    wrap_text=bool(should_wrap),
                    readingOrder=2 if rtl else 1,
                )
                if should_wrap and isinstance(value, str):
                    line_count = max(line_count, _wrapped_line_count(value, this_column_width))

            number_format_override = row_number_formats.get(record_index) or column_number_formats.get(leaf)
            if number_format_override and header not in flag_keys:
                cell.number_format = number_format_override

            # Apply row-level style first, then per-cell overrides on top.
            font_bold = cell_bold
            if row_style == "total":
                cell.fill = TOTAL_FILL
                font_bold = True
            elif row_style == "subheader":
                cell.fill = SUBHEADER_FILL
                font_bold = True
            if cell_bg:
                cell.fill = PatternFill(start_color=cell_bg, end_color=cell_bg, fill_type="solid")
            if illegible:
                cell.fill = ILLEGIBLE_FILL
            cell.font = Font(
                name=cell.font.name,
                bold=font_bold,
                color=cell_color or "000000",
            )
            cell.border = _table_border(row_index, col_index, last_col, bottom_row, table_start=R + 1)

        effective_height = row_height * row_height_mult * line_count
        if effective_height > row_height:
            ws.row_dimensions[row_index].height = effective_height

    blank_start_row = R + 3 + len(flat_records)
    for row_index in range(blank_start_row, blank_start_row + blank_rows):
        for col_index, header in enumerate(headers, start=1):
            leaf = leaf_names[col_index - 1]
            alignment_override = column_alignments.get(leaf)
            vertical_override = column_vertical_alignments.get(leaf)
            cell = ws.cell(row=row_index, column=col_index)
            cell.alignment = (
                Alignment(horizontal=alignment_override, vertical=vertical_override or DATA_ALIGNMENT.vertical)
                if alignment_override or vertical_override
                else DATA_ALIGNMENT
            )
            cell.border = _table_border(row_index, col_index, last_col, bottom_row, table_start=R + 1)

    for col_index, header in enumerate(headers, start=1):
        if header in flag_keys:
            column_letter = get_column_letter(col_index)
            validation = DataValidation(type="list", formula1='"1,0"', allow_blank=True)
            validation.add(f"{column_letter}{R + 3}:{column_letter}{last_row}")
            ws.add_data_validation(validation)

    for row in ws.iter_rows(min_row=R + 1, max_row=R + 2, max_col=len(headers)):
        for cell in row:
            cell.font = HEADER_FONT
            cell.alignment = HEADER_ALIGNMENT
            cell.border = _table_border(cell.row, cell.column, last_col, bottom_row, table_start=R + 1)

    for col_index in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_index)].width = col_widths[col_index - 1]

    if footer is not None:
        footer_row = last_row + 1
        footer_cell = ws.cell(row=footer_row, column=1, value=footer)
        footer_cell.alignment = DATA_ALIGNMENT
        ws.merge_cells(start_row=footer_row, end_row=footer_row, start_column=1, end_column=len(headers))
        for col_index in range(1, len(headers) + 1):
            ws.cell(row=footer_row, column=col_index).border = _table_border(
                footer_row, col_index, last_col, bottom_row, table_start=R + 1
            )

    wb.save(xlsx_path)


def main():
    parser = argparse.ArgumentParser(description="Convert a JSON array of objects into an Excel spreadsheet.")
    parser.add_argument("json_path")
    parser.add_argument("xlsx_path", nargs="?")
    parser.add_argument("--column-width", type=float, default=DEFAULT_COLUMN_WIDTH)
    parser.add_argument("--row-height", type=float, default=DEFAULT_ROW_HEIGHT)
    parser.add_argument("--footer", default=None, help="Text for a merged full-width row at the bottom.")
    parser.add_argument(
        "--column-widths", default=None, help='JSON object mapping header name to width, e.g. \'{"Name": 30}\''
    )
    parser.add_argument(
        "--column-alignments",
        default=None,
        help='JSON object mapping header name to "left"/"center"/"right", e.g. \'{"Price": "right"}\'',
    )
    parser.add_argument(
        "--column-vertical-alignments",
        default=None,
        help='JSON object mapping header name to "top"/"center"/"bottom", e.g. \'{"Price": "center"}\'',
    )
    parser.add_argument(
        "--column-number-formats",
        default=None,
        help='JSON object mapping header name to an Excel number format, e.g. \'{"Price": "0.0000"}\'',
    )
    parser.add_argument(
        "--column-fills",
        default=None,
        help='JSON object mapping header name to a hex fill color, e.g. \'{"Total": "D9D9D9"}\'',
    )
    parser.add_argument(
        "--row-fills",
        default=None,
        help='JSON object mapping 1-indexed data row number to a hex fill color, e.g. \'{"3": "D9D9D9"}\'',
    )
    parser.add_argument(
        "--column-font-colors",
        default=None,
        help='JSON object mapping header name to a hex font color, e.g. \'{"Adjustment": "FF0000"}\'',
    )
    parser.add_argument(
        "--row-font-colors",
        default=None,
        help='JSON object mapping 1-indexed data row number to a hex font color, e.g. \'{"3": "FF0000"}\'',
    )
    parser.add_argument(
        "--row-number-formats",
        default=None,
        help='JSON object mapping 1-indexed data row number to an Excel number format, e.g. \'{"3": "0.0\\"%%\\""}\'',
    )
    parser.add_argument(
        "--blank-rows", type=int, default=0, help="Number of empty bordered rows to add after the data."
    )
    args = parser.parse_args()

    xlsx_path = args.xlsx_path or str(Path(args.json_path).with_suffix(".xlsx"))
    json_to_xlsx(
        args.json_path,
        xlsx_path,
        column_width=args.column_width,
        row_height=args.row_height,
        footer=args.footer,
        column_widths=json.loads(args.column_widths) if args.column_widths else None,
        column_number_formats=(
            json.loads(args.column_number_formats) if args.column_number_formats else None
        ),
        column_vertical_alignments=(
            json.loads(args.column_vertical_alignments) if args.column_vertical_alignments else None
        ),
        column_alignments=json.loads(args.column_alignments) if args.column_alignments else None,
        column_fills=json.loads(args.column_fills) if args.column_fills else None,
        row_fills=(
            {int(k): v for k, v in json.loads(args.row_fills).items()} if args.row_fills else None
        ),
        column_font_colors=json.loads(args.column_font_colors) if args.column_font_colors else None,
        row_font_colors=(
            {int(k): v for k, v in json.loads(args.row_font_colors).items()} if args.row_font_colors else None
        ),
        row_number_formats=(
            {int(k): v for k, v in json.loads(args.row_number_formats).items()}
            if args.row_number_formats
            else None
        ),
        blank_rows=args.blank_rows,
    )


if __name__ == "__main__":
    main()
