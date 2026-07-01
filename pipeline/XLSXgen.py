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
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import re as _re
import unicodedata as _ud


def _vwidth(s: str) -> int:
    """Approximate rendered width: full-width/wide chars count as 2, others 1."""
    return sum(2 if _ud.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _vljust(s: str, target: int, fillchar: str = " ") -> str:
    """Left-justify s with fillchar until its visual width reaches target."""
    pad = target - _vwidth(s)
    if pad <= 0:
        return s
    fw = _vwidth(fillchar) or 1
    out = s + fillchar * (pad // fw)
    if pad % fw:
        out += " " * (pad % fw)
    return out


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
                # Entire remainder IS the type token: "CODE TYPE_NUM TYPE_WORD"
                m = type_pat.match(remainder)
                if m and len(remainder) <= 12:
                    type_token = f"{m.group(1)}{type_internal}{m.group(2)}"
                else:
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
                # Type token may sit at the END of a name line (e.g. "<name> 999 購入")
                m2 = end_type_pat.search(stripped) if not type_token else None
                if m2 and len(f"{m2.group(1)} {m2.group(2)}") <= 12:
                    type_token = f"{m2.group(1)}{type_internal}{m2.group(2)}"
                    name_part = stripped[:m2.start()].strip()
                    if name_part:
                        name_lines.append(name_part)
                else:
                    name_lines.append(stripped)

    if not type_token:
        injected = (opts.get("injected_type") or "").strip()
        if injected:
            type_token = injected.replace(" ", type_internal, 1)
    first_line = f"{code_line}{code_to_type}{type_token}" if type_token else code_line
    rest = "\n".join(name_lines)
    return f"{first_line}\n{rest}" if rest else first_line


_SIDES = {
    "thin":   Side(style="thin"),
    "medium": Side(style="medium"),
    "thick":  Side(style="thick"),
    "dashed": Side(style="dashed"),
    None:     Side(style=None),
}


def _side(s):
    return _SIDES.get(s, Side(style=None))

def _side_colored(weight="medium", color="FFFFFF"):
    """Return a border side with the given weight and explicit color."""
    return Side(style=weight, color=color)

def _side_white(weight="medium"):
    return _side_colored(weight, "FFFFFF")


def _border(spec: dict) -> Border:
    def _s(side: str):
        style = spec.get(side)
        color = spec.get(f"{side}_color")
        if style is None:
            return Side(style=None)
        return Side(style=style, color=color) if color else _side(style)
    return Border(
        top=_s("top"),
        bottom=_s("bottom"),
        left=_s("left"),
        right=_s("right"),
    )


def _write_cell(ws, row: int, col: int, end_col: int, end_row: int,
                value: str, font_spec: dict | None, align_spec: dict | None, border_spec: dict | None,
                fill_spec: dict | None = None):
    font_spec = font_spec or {}
    align_spec = align_spec or {}
    border_spec = border_spec or {}
    font = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 10),
                underline="single" if font_spec.get("underline") else None)
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

    is_negative = isinstance(value, str) and value.strip().startswith("-")
    for r in range(row, end_row + 1):
        for c in range(col, end_col + 1):
            is_top    = r == row
            is_bottom = r == end_row
            is_left   = c == col
            is_right  = c == end_col
            cell = ws.cell(row=r, column=c)
            cell.font = Font(bold=font.bold, size=font.size, color="FF0000" if is_negative else "000000")
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
            if fill_spec:
                cell.fill = PatternFill("solid", fgColor=fill_spec.get("color", "FFFFFF"))


def _normalize_row(row, col_names: list) -> dict:
    """Convert a positional list-row (preferred — avoids JSON key-collision
    issues with duplicate/blank column headers) into the dict-row shape the
    rest of this module expects. Dict rows (e.g. {"_full_width": ...}) pass
    through unchanged."""
    if isinstance(row, dict):
        return row
    if isinstance(row, list):
        result: dict = {}
        seen: dict[str, int] = {}
        for i, cn in enumerate(col_names):
            cnt = seen.get(cn, 0)
            seen[cn] = cnt + 1
            key = cn if cnt == 0 else (f"{cn}_{cnt + 1}" if cn else f"_{cnt + 1}")
            result[key] = row[i] if i < len(row) else ""
        return result
    return {}


def _normalize_rows(rows: list, col_names: list) -> list:
    return [_normalize_row(rw, col_names) for rw in rows]


def _split_title_3(title: str) -> tuple[str, str, str]:
    """Split a top-line title string into (left, center, right) parts.
    Left = leading period like '2026年2月'; right = trailing date/page marker
    like '2026/6/22 PAGE:1'; center = whatever document-name text remains."""
    title = (title or "").strip()
    left = right = ""
    center = title
    m = _re.match(r'^(\d{4}年\d{1,2}月)\s+(.*)$', center)
    if m:
        left, center = m.group(1), m.group(2)
    m = _re.search(r'^(.*?)\s+(\d{4}/\d{1,2}/\d{1,2}.*)$', center)
    if m:
        center, right = m.group(1), m.group(2)
    return left, center.strip(), right.strip()


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

    # 1. First attempt exact match on title and section
    for tmpl in templates:
        m = tmpl.get("match", {})
        t_title   = (m.get("title") or "").strip()
        t_section = (m.get("section_header") or "").strip()
        if t_title == title and t_section == section:
            return tmpl

    # Collect all text tokens present in the extracted data
    data_tokens: set[str] = set()
    data_tokens.add(title)
    data_tokens.add(section)
    data_tokens.update(data.get("header", {}).keys())
    table = data.get("table", {})
    col_names = table.get("columns", [])
    data_tokens.update(c for c in col_names if c)
    for row in _normalize_rows(table.get("rows", []), col_names):
        data_tokens.update(k for k in row.keys() if k and k != "_full_width")
    data_tokens.discard("")

    best_tmpl  = None
    best_score = -1.0

    for tmpl in templates:
        signals = tmpl.get("match_signals", [])
        if not signals:
            signal_score = 0.0
        else:
            hits         = sum(1 for s in signals if s in data_tokens)
            signal_score = hits / len(signals)

        # Title + section similarity as tiebreaker (weighted 0..0.5)
        m          = tmpl.get("match", {})
        t_title    = (m.get("title") or "").strip()
        t_section  = (m.get("section_header") or "").strip()
        title_sim  = difflib.SequenceMatcher(None, title,   t_title).ratio()
        section_sim= difflib.SequenceMatcher(None, section, t_section).ratio()
        score      = signal_score + 0.25 * title_sim + 0.25 * section_sim

        if score > best_score:
            best_score = score
            best_tmpl  = tmpl

    if best_tmpl is not None:
        return best_tmpl

    # Last resort fallback: default to the first template with a warning
    if templates:
        import sys
        print(
            f"Warning: No template matched for title={title!r} section={section!r}. "
            f"Falling back to: {templates[0].get('id')}",
            file=sys.stderr
        )
        return templates[0]

    raise ValueError(
        f"No template found for title={title!r} section={section!r}. "
        f"Available: {[t.get('id') for t in templates]}"
    )


# ── Sheet builder ─────────────────────────────────────────────────────────────

def fill_grouped_template(tmpl: dict, data: dict, ws) -> None:
    """Render a month-grouped table (e.g. 売上実績表): col A is a merged month cell
    spanning group_size rows; remaining cols render each inner row independently."""
    import re as _re2

    for col_letter, width in tmpl.get("column_widths", {}).items():
        ws.column_dimensions[col_letter].width = width

    for row_spec in tmpl.get("header", []):
        r = row_spec["row"]
        ws.row_dimensions[r].height = row_spec.get("height", 14)
        for cell in row_spec["cells"]:
            if cell.get("fixed", True):
                value = cell.get("value", "")
            else:
                key = cell.get("key", "")
                if key in ("title", "section_header"):
                    value = data.get(key, "")
                else:
                    value = _fuzzy_get(data.get("header", {}), key)
            _write_cell(ws, r, cell["col"], cell["end_col"], r,
                        value, cell.get("font"), cell.get("align"), cell.get("border"))

    ch = tmpl.get("col_headers", {})
    if ch:
        r_hdr = ch.get("row", 2)
        ws.row_dimensions[r_hdr].height = ch.get("height", 14)
        for cell in ch.get("cells", []):
            _write_cell(ws, r_hdr, cell["col"], cell["end_col"], r_hdr,
                        cell.get("value", ""), cell.get("font"), cell.get("align"), cell.get("border"))

    table_rows = _normalize_rows(data.get("table", {}).get("rows", []),
                                  data.get("table", {}).get("columns", []))
    data_rows = [rw for rw in table_rows if "_full_width" not in rw]

    month_source = tmpl.get("month_source", "full_width")
    month_key    = tmpl.get("month_key", "月別")
    group_size   = tmpl.get("group_size", 4)

    n_groups    = tmpl.get("n_groups", 15)

    if month_source == "col":
        # Split into fixed-size chunks so summary rows (上半期合計 etc.) don't
        # corrupt group boundaries — the month label may appear on any row in the group
        groups: list[list[dict]] = [
            data_rows[i:i + group_size] for i in range(0, len(data_rows), group_size)
        ]

        def _fmt_month(name: str) -> str:
            if name.endswith("合計"):
                return name[:-2] + "\n合計"
            return name

        def _get_month(grp: list[dict]) -> str:
            for row in grp:
                val = row.get(month_key, "")
                if val:
                    return val
            return ""

        month_names = [_fmt_month(_get_month(g)) for g in groups]
    else:
        groups = []
        month_names = []
        for rw in table_rows:
            if "_full_width" in rw:
                parts = _re2.split(r'[\s　]+', rw["_full_width"].strip())
                month_names = [p for p in parts if p]
    start_row   = tmpl.get("data_start_row", 3)
    row_height  = tmpl.get("row_height", 14.0)
    gc          = tmpl.get("group_col", {})
    col_defs    = tmpl.get("columns", [])
    no_side     = Side(style=None)

    for g in range(n_groups):
        month          = month_names[g] if g < len(month_names) else ""
        grp_start      = start_row + g * group_size
        grp_end        = grp_start + group_size - 1
        gc_col         = gc.get("col", 1)
        gc_end_col     = gc.get("end_col", 1)
        gc_font        = gc.get("font", {})
        gc_align       = gc.get("align", {})
        gc_border      = gc.get("border", {})

        ws.merge_cells(start_row=grp_start, end_row=grp_end,
                       start_column=gc_col, end_column=gc_end_col)

        for r_idx in range(grp_start, grp_end + 1):
            is_first_r = r_idx == grp_start
            is_last_r  = r_idx == grp_end
            c_cell     = ws.cell(row=r_idx, column=gc_col)
            if is_first_r:
                c_cell.value     = month or None
                c_cell.font      = Font(bold=gc_font.get("bold", False),
                                        size=gc_font.get("size", 8))
                c_cell.alignment = Alignment(horizontal=gc_align.get("h", "center"),
                                             vertical=gc_align.get("v", "center"),
                                             wrap_text=True)
            c_cell.border = Border(
                top=_side(gc_border.get("top"))    if is_first_r else no_side,
                bottom=_side(gc_border.get("bottom", "medium")) if is_last_r else no_side,
                left=_side(gc_border.get("left")),
                right=_side(gc_border.get("right")),
            )

        for i in range(group_size):
            r          = grp_start + i
            ws.row_dimensions[r].height = row_height
            if groups:
                row_data = groups[g][i] if g < len(groups) and i < len(groups[g]) else {}
            else:
                data_idx = g * group_size + i
                row_data = data_rows[data_idx] if data_idx < len(data_rows) else {}
            is_first   = i == 0
            is_last    = i == group_size - 1

            col_names = data.get("table", {}).get("columns", [])
            # Build positional value list to handle duplicate column header keys
            pos_values = []
            seen: dict[str, int] = {}
            for col_name in col_names:
                count = seen.get(col_name, 0)
                seen[col_name] = count + 1
                if count == 0:
                    pos_values.append(row_data.get(col_name, "") if row_data else "")
                else:
                    dedup_key = f"{col_name}_{count + 1}" if col_name else f"_{count + 1}"
                    pos_values.append(row_data.get(dedup_key, "") if row_data else "")
            for col_def in col_defs:
                if "col_index" in col_def:
                    idx = col_def["col_index"]
                    value = pos_values[idx] if idx < len(pos_values) else ""
                else:
                    key = col_def.get("key", "")
                    if row_data:
                        value = row_data.get(key, "")
                        if not value:
                            for alias in col_def.get("key_aliases", []):
                                value = row_data.get(alias, "")
                                if value:
                                    break
                    else:
                        value = ""
                base_b     = col_def.get("border", {})
                border_spec = {
                    "top":    "medium" if is_first else base_b.get("top", "thin"),
                    "bottom": "medium" if is_last  else base_b.get("bottom", "thin"),
                    "left":   base_b.get("left"),
                    "right":  base_b.get("right"),
                }
                _write_cell(ws, r, col_def["col"], col_def["end_col"], r,
                            value, col_def.get("font", {}), col_def.get("align", {}),
                            border_spec)


def _fill_sections(tmpl: dict, data: dict, ws, col_defs: list, start_row: int,
                   table_rows: list, row_h: float, dr: dict) -> None:
    """Render data rows described by a sections array.

    Each section entry:
      pairs          – number of 2-row pairs in this section
      block_pairs    – how many pairs = 1 "block" (B gets medium-top at block start)
      fill           – hex color or null for D3:O cols and B col
      col_A_border   – "medium" | "thick" | null
      col_A_span     – true → merge A for the whole section
      col_right      – right-border style for last col (default "medium")
      sub_sections   – optional list of {pairs, fill} for fill-variation within section

    pair_merge_col  (int, 1-based) in dr → merge that column every 2 rows.
    """
    no_side = Side(style=None)
    pair_col = dr.get("pair_merge_col")   # 1-based col index to merge per pair
    pair_col_labels = dr.get("pair_col_labels")  # fixed labels cycling per pair-in-block (overrides dynamic split)
    sections = dr.get("sections", [])

    # Build positional value list from each row
    col_names = data.get("table", {}).get("columns", [])
    if pair_col_labels:
        # The model sometimes emits its own redundant 当月/累計-style column even though
        # we already render that via pair_col_labels — drop it so positional indices
        # for the numeric columns don't shift.
        def _is_pair_label_col(cn: str) -> bool:
            if not cn:
                return False
            stripped = cn
            for lbl in pair_col_labels:
                stripped = stripped.replace(lbl, "")
            stripped = _re.sub(r'[/\s　,、]+', '', stripped)
            return stripped == ""
        col_names = [cn for cn in col_names if not _is_pair_label_col(cn)]

    def _pos_values(row_data: dict) -> list:
        seen: dict[str, int] = {}
        vals = []
        for cn in col_names:
            cnt = seen.get(cn, 0)
            seen[cn] = cnt + 1
            if cnt == 0:
                vals.append(row_data.get(cn, "") if row_data else "")
            else:
                dk = f"{cn}_{cnt+1}" if cn else f"_{cnt+1}"
                vals.append(row_data.get(dk, "") if row_data else "")
        return vals

    def _cell_value(col_def: dict, row_data: dict, pos_vals: list) -> str:
        if col_def.get("fixed"):
            return col_def.get("value", "")
        if "col_index" in col_def:
            idx = col_def["col_index"]
            val = pos_vals[idx] if idx < len(pos_vals) else ""
            concat_idx = col_def.get("concat_col_index")
            if concat_idx is not None:
                extra = pos_vals[concat_idx] if concat_idx < len(pos_vals) else ""
                if extra:
                    sep = col_def.get("concat_sep", " ")
                    val = (val + sep + extra).strip() if val else extra
            concat_all = col_def.get("concat_all_indices")
            if concat_all:
                sep = col_def.get("concat_sep", " ")
                skip = set(pair_col_labels) if pair_col_labels else set()
                pieces = [val] if val and val not in skip else []
                for ci in concat_all:
                    piece = pos_vals[ci] if ci < len(pos_vals) else ""
                    if piece and piece not in skip:
                        pieces.append(piece)
                val = sep.join(pieces)
            second_seg = col_def.get("second_segment_indices")
            if second_seg:
                skip = set(pair_col_labels) if pair_col_labels else set()
                lbl_idx, val_idx = second_seg
                lbl = pos_vals[lbl_idx] if lbl_idx < len(pos_vals) else ""
                v2  = pos_vals[val_idx] if val_idx < len(pos_vals) else ""
                if lbl in skip:
                    lbl = ""
                if v2 in skip:
                    v2 = ""
                inner_sep = col_def.get("second_segment_inner_sep", " ")
                seg_text = (lbl + inner_sep + v2).strip() if (lbl or v2) else ""
                if seg_text:
                    pad_to = col_def.get("second_segment_pad_to")
                    if pad_to:
                        val = _vljust(val, pad_to, "　")
                    sep = col_def.get("second_segment_sep", "   ")
                    val = (val + sep + seg_text) if val else seg_text
            second_pair = col_def.get("second_pair_indices")
            if second_pair and val:
                lbl_idx, val_idx = second_pair
                lbl = pos_vals[lbl_idx] if lbl_idx < len(pos_vals) else ""
                v2  = pos_vals[val_idx] if val_idx < len(pos_vals) else ""
                pair_text = (lbl + " " + v2).strip()
                if pair_text:
                    pad_to = col_def.get("second_pair_pad_to")
                    if pad_to and len(val) < pad_to:
                        val = val.ljust(pad_to, "　")
                    sep = col_def.get("second_pair_sep", "   ")
                    val = val + sep + pair_text
            if not val:
                guard_idx = col_def.get("fallback_guard_index")
                guard_blocks = (guard_idx is not None and guard_idx < len(pos_vals)
                                and pos_vals[guard_idx])
                if not guard_blocks:
                    for fb in col_def.get("fallback_col_indices", []):
                        val = pos_vals[fb] if fb < len(pos_vals) else ""
                        if val:
                            break
            return val
        key = col_def.get("key", "")
        return _fuzzy_get(row_data, key) if row_data else ""

    row_idx = 0   # index into table_rows
    excel_row = start_row

    for sec in sections:
        n_pairs     = sec.get("pairs", 0)
        block_pairs = sec.get("block_pairs", n_pairs)  # all pairs = one block if not specified
        col_a_border = sec.get("col_A_border", "medium")
        col_a_span  = sec.get("col_A_span", False)
        col_right   = sec.get("col_right", "medium")  # right border of last column

        # Build per-row fill lookup from sub_sections or flat fill
        sub_secs = sec.get("sub_sections")
        if sub_secs:
            row_fills = []
            for ss in sub_secs:
                row_fills.extend([ss.get("fill")] * (ss["pairs"] * 2))
        else:
            row_fills = [sec.get("fill")] * (n_pairs * 2)

        sec_start_row = excel_row
        sec_end_row   = excel_row + n_pairs * 2 - 1

        block_c_chunks: list = [''] * block_pairs  # pre-split C label per pair within block

        for pair_idx in range(n_pairs):
            is_first_pair_of_sec = pair_idx == 0
            is_last_pair_of_sec  = pair_idx == n_pairs - 1
            is_block_start       = (pair_idx % block_pairs) == 0

            pair_start = excel_row
            pair_end   = excel_row + 1
            _a_carry   = ""  # holds the 2nd token of a split col-A value for the pair's bottom row

            # Apply pair merge for col_C etc.
            if pair_col:
                ws.merge_cells(start_row=pair_start, end_row=pair_end,
                               start_column=pair_col, end_column=pair_col)

            # Pre-compute block C split: scan pair-tops from last to first; split evenly
            if is_block_start and pair_col and pair_col_labels:
                block_c_chunks = [pair_col_labels[_i % len(pair_col_labels)] for _i in range(block_pairs)]
            elif is_block_start and pair_col:
                _blk_label = ""
                for _bp in range(block_pairs - 1, -1, -1):
                    _td = row_idx + _bp * 2
                    _rd = table_rows[_td] if _td < len(table_rows) else {}
                    _pv = _pos_values(_rd)
                    for _cd in col_defs:
                        if _cd.get("col") == pair_col and "col_index" in _cd:
                            _v = _pv[_cd["col_index"]] if _cd["col_index"] < len(_pv) else ""
                            if _v:
                                _blk_label = _v
                                break
                    if _blk_label:
                        break
                _n = len(_blk_label)
                _chunk = (_n + block_pairs - 1) // block_pairs if block_pairs and _n else 0
                if _chunk:
                    block_c_chunks = [_blk_label[_i*_chunk:min((_i+1)*_chunk, _n)] for _i in range(block_pairs)]
                else:
                    block_c_chunks = [''] * block_pairs

            for sub_row in range(2):  # 0=odd(top), 1=even(bottom)
                r = excel_row + sub_row
                ws.row_dimensions[r].height = row_h
                row_data = table_rows[row_idx + sub_row] if (row_idx + sub_row) < len(table_rows) else {}
                pos_vals = _pos_values(row_data)
                fill_color = row_fills[pair_idx * 2 + sub_row]
                fill_spec  = {"color": fill_color} if fill_color else None

                is_pair_top    = sub_row == 0
                is_pair_bottom = sub_row == 1
                is_sec_top     = is_first_pair_of_sec and is_pair_top
                is_sec_bottom  = is_last_pair_of_sec  and is_pair_bottom

                for col_def in col_defs:
                    c     = col_def["col"]
                    ec    = col_def["end_col"]
                    value = _cell_value(col_def, row_data, pos_vals)
                    font_spec  = col_def.get("font", {"bold": False, "size": 8})
                    align_spec = col_def.get("align", {"h": "left", "v": "center", "wrap": False})

                    # Color for internal "hidden" borders — match fill so lines disappear into bg
                    hidden_color = fill_color if fill_color else "FFFFFF"

                    # ── Column A ──────────────────────────────────────────────
                    if c == 1:
                        if col_a_span:
                            # A is merged for the whole section; only write cell once
                            if is_sec_top:
                                ws.merge_cells(start_row=sec_start_row, end_row=sec_end_row,
                                               start_column=1, end_column=1)
                                span_val = sec.get("col_A_span_value", value)
                                a_cell = ws.cell(row=sec_start_row, column=1, value=span_val or None)
                                a_cell.font      = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 8))
                                a_cell.alignment = Alignment(horizontal=align_spec.get("h","center"),
                                                             vertical=align_spec.get("v","center"), wrap_text=True)
                                a_cell.border    = Border(
                                    top=_side(col_a_border), bottom=_side(col_a_border),
                                    left=_side(col_a_border), right=_side("medium"))
                                # Apply border to all cells in the merge (openpyxl requirement)
                                for ra in range(sec_start_row + 1, sec_end_row + 1):
                                    # pick fill color at this row for the hidden border color
                                    row_fill_at = row_fills[min((ra - sec_start_row), len(row_fills) - 1)]
                                    hc = row_fill_at if row_fill_at else "FFFFFF"
                                    c2 = ws.cell(row=ra, column=1)
                                    c2.border = Border(
                                        top=_side_colored(col_a_border, hc),
                                        bottom=_side(col_a_border) if ra == sec_end_row else _side_colored(col_a_border, hc),
                                        left=_side(col_a_border), right=_side("medium"))
                            continue  # all other rows handled by merge
                        else:
                            # A is per-row; block-boundary borders visible, internal hidden
                            is_block_bnd_top = is_pair_top and (pair_idx % block_pairs == 0) and not is_sec_top
                            is_block_bnd_bot = is_pair_bottom and ((pair_idx + 1) % block_pairs == 0) and not is_sec_bottom
                            if is_sec_top:
                                top_a = _side(col_a_border)
                            elif is_block_bnd_top:
                                top_a = _side("medium")
                            else:
                                top_a = _side_colored(col_a_border, hidden_color)
                            if is_sec_bottom:
                                bot_a = _side(sec.get("last_outer_bottom", col_a_border))
                            elif is_block_bnd_bot:
                                bot_a = _side("medium")
                            else:
                                bot_a = _side_colored(col_a_border, hidden_color)
                            if col_def.get("split_rows"):
                                if is_pair_top:
                                    tokens = _re.split(r'[ 　]+', value) if value else [""]
                                    if len(tokens) > 1:
                                        a_val = " ".join(tokens[:-1])
                                        _a_carry = tokens[-1]
                                    else:
                                        a_val = tokens[0]
                                        _a_carry = ""
                                else:
                                    # Fall back to this row's own value if the top row had
                                    # nothing to carry down (model may put it here directly)
                                    a_val = _a_carry or value
                            else:
                                a_val = value
                                if col_def.get("space_to_newline") and a_val:
                                    a_val = a_val.replace(" ", "\n")
                            a_cell = ws.cell(row=r, column=1, value=a_val or None)
                            a_cell.font      = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 8))
                            a_cell.alignment = Alignment(horizontal=align_spec.get("h","left"),
                                                         vertical=align_spec.get("v","center"),
                                                         wrap_text=bool(col_def.get("space_to_newline")))
                            a_cell.border = Border(top=top_a, bottom=bot_a,
                                                   left=_side(col_a_border), right=_side(col_a_border))
                            if fill_spec:
                                a_cell.fill = PatternFill("solid", fgColor=fill_spec["color"])
                        continue

                    # ── Free-text columns between A and the pair-merge column ──
                    if 1 < c < pair_col:
                        # Top: section outer at start; medium at block start (pair_top); else hidden
                        if is_sec_top:
                            top_b = _side(col_a_border)
                        elif is_block_start and is_pair_top:
                            top_b = _side("medium")
                        else:
                            top_b = _side_colored("thin", hidden_color)
                        # Bottom: thick/medium at section end; medium at block end; else hidden
                        sec_bot_weight = sec.get("last_outer_bottom", col_a_border)
                        if is_sec_bottom:
                            bot_b = _side(sec_bot_weight)
                        elif is_pair_bottom and (pair_idx % block_pairs) == (block_pairs - 1):
                            bot_b = _side("medium")
                        else:
                            bot_b = _side_colored("thin", hidden_color)
                        b_fill = fill_spec
                        b_cell = ws.cell(row=r, column=c, value=value or None)
                        b_cell.font      = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 8))
                        b_cell.alignment = Alignment(horizontal=align_spec.get("h","left"),
                                                     vertical=align_spec.get("v","center"), wrap_text=False)
                        left_side  = _side("medium") if c == 2 else _side_colored("thin", hidden_color)
                        right_side = _side("medium") if c == pair_col - 1 else _side_colored("thin", hidden_color)
                        b_cell.border    = Border(top=top_b, bottom=bot_b,
                                                  left=left_side, right=right_side)
                        if b_fill:
                            b_cell.fill = PatternFill("solid", fgColor=b_fill["color"])
                        continue

                    # ── Pair-merge column (e.g. 当月/累計) ──────────────────────
                    if c == pair_col:
                        if is_pair_top:
                            # Top row of merged pair; use pre-split block chunk for this pair
                            pair_pos_in_block = pair_idx % block_pairs
                            c_val = block_c_chunks[pair_pos_in_block] if pair_pos_in_block < len(block_c_chunks) else value
                            top_c = col_a_border if is_sec_top else ("medium" if is_block_start else None)
                            c_fill = fill_spec
                            _write_cell(ws, r, pair_col, pair_col, r, c_val, font_spec, align_spec,
                                        {"top": top_c, "bottom": "thin",
                                         "left": None, "right": "thin"},
                                        c_fill)
                        else:
                            # Bottom row of merged pair
                            bot_c = sec.get("last_outer_bottom", col_a_border) if is_sec_bottom else "thin"
                            _write_cell(ws, r, pair_col, pair_col, r, "", font_spec, align_spec,
                                        {"top": None, "bottom": bot_c,
                                         "left": None, "right": "thin"})
                        continue

                    # ── Columns D–O ───────────────────────────────────────────
                    # In filled rows, dashed dividers use gray so they're visible but harmonious
                    dash_color = "808080" if fill_color else "000000"
                    is_last_col = (ec == col_defs[-1]["end_col"])
                    left_b  = "medium" if c == pair_col + 1 else "thin"  # first numeric col = medium left
                    right_b = col_right if is_last_col else "thin"
                    if is_pair_top:
                        top_b  = col_a_border if is_sec_top else ("medium" if is_block_start else "dashed")
                        bot_b  = "dashed"
                    else:
                        top_b  = "dashed"
                        bot_b  = sec.get("last_outer_bottom", col_a_border) if is_sec_bottom else "medium"

                    # Write cell directly to apply colored dashed sides where needed
                    xc = ws.cell(row=r, column=c, value=value or None)
                    xc.font      = Font(bold=font_spec.get("bold", False), size=font_spec.get("size", 8))
                    xc.alignment = Alignment(horizontal=align_spec.get("h","right"),
                                             vertical=align_spec.get("v","center"), wrap_text=False)
                    def _s(name):
                        if name == "dashed":
                            return _side_colored("dashed", dash_color)
                        return _side(name)
                    xc.border = Border(top=_s(top_b), bottom=_s(bot_b),
                                       left=_side(left_b), right=_side(right_b))
                    if fill_spec:
                        xc.fill = PatternFill("solid", fgColor=fill_spec["color"])

            excel_row += 2
            row_idx   += 2


def fill_template(tmpl: dict, data: dict, ws) -> None:
    if tmpl.get("group_table"):
        fill_grouped_template(tmpl, data, ws)
        return

    header_vals = data.get("header", {})
    table       = data.get("table", {})
    table_rows  = _normalize_rows(table.get("rows", []), table.get("columns", []))

    # Column widths
    for col_letter, width in tmpl.get("column_widths", {}).items():
        ws.column_dimensions[col_letter].width = width

    # ── Header rows ───────────────────────────────────────────────────────────
    _used_header_keys: set = set()
    for row_spec in tmpl.get("header", []):
        r = row_spec["row"]
        ws.row_dimensions[r].height = row_spec.get("height", 15)
        for cell in row_spec["cells"]:
            key = cell.get("key", "")
            if cell.get("fixed"):
                value = cell.get("value", "")
            elif key in ("title", "section_header"):
                value = data.get(key, "")
            elif "title_part" in cell:
                left, center, right = _split_title_3(data.get("title", ""))
                value = {"left": left, "center": center, "right": right}[cell["title_part"]]
            elif "concat_keys" in cell:
                parts = [_fuzzy_get(header_vals, k, _used=_used_header_keys) for k in cell["concat_keys"]]
                value = " ".join(p for p in parts if p)
            elif "value_part" in cell:
                raw = _fuzzy_get(header_vals, key, _used=_used_header_keys)
                tokens = _re.split(r'[ 　]+', raw.strip()) if raw else [""]
                if cell["value_part"] == "tail" and len(tokens) > 1:
                    value = tokens[-1]
                elif cell["value_part"] == "tail":
                    value = ""
                else:
                    value = " ".join(tokens[:-1]) if len(tokens) > 1 else tokens[0]
            else:
                value = _fuzzy_get(header_vals, key, _used=_used_header_keys)
                if cell.get("label_prefix") and value:
                    value = f"{key} {value}"
            _write_cell(
                ws, r, cell["col"], cell["end_col"], r,
                value, cell["font"], cell["align"], cell["border"],
                cell.get("fill"),
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
    ch_fill = ch.get("fill")
    col_names = table.get("columns", [])
    for cell in ch.get("cells", []):
        if "col_index" in cell:
            idx = cell["col_index"]
            value = col_names[idx] if idx < len(col_names) else ""
        else:
            value = cell.get("value", "")
        merge_rows = cell.get("merge_rows", True)
        cell_r2 = r2 if merge_rows else r1
        _write_cell(
            ws, r1, cell["col"], cell["end_col"], cell_r2,
            value, cell["font"], cell["align"], cell["border"],
            cell.get("fill") or ch_fill,
        )
        # For non-merged header cells write the second row with its own border
        if not merge_rows and r2 != r1 and "row2_border" in cell:
            _write_cell(
                ws, r2, cell["col"], cell["end_col"], r2,
                cell.get("row2_value", ""), cell["font"], cell["align"], cell["row2_border"],
                cell.get("fill") or ch_fill,
            )

    # ── Data rows ─────────────────────────────────────────────────────────────
    dr = tmpl.get("data_rows", {})
    start    = dr.get("start_row", r2 + 1 if r2 else 1)
    count    = dr.get("count", 0)
    row_h    = dr.get("row_height", 30)
    col_defs = dr.get("columns", [])

    # Column header names — used to filter out misidentified full_width rows
    col_header_names = {c["value"] for c in ch.get("cells", []) if "value" in c}

    # Strip any _full_width rows whose text is just a column header name
    table_rows = [
        rw for rw in table_rows
        if not ("_full_width" in rw and rw["_full_width"].strip() in col_header_names)
    ]

    # Filter fully-blank data rows if requested
    if dr.get("filter_empty_rows"):
        def _row_is_empty(rw):
            if "_full_width" in rw:
                return False
            return all(v == "" or v is None for v in rw.values())
        table_rows = [rw for rw in table_rows if not _row_is_empty(rw)]

    # Inject any fixed rows that always appear before the JSON data
    prepend = dr.get("prepend_rows", [])
    table_rows = prepend + table_rows

    # Pop last row into footer if flagged
    footer_row_data = {}
    if dr.get("last_row_is_footer") and table_rows and "_full_width" not in table_rows[-1]:
        footer_row_data = table_rows.pop()

    # Sections-based rendering (for complex per-row styled documents)
    if dr.get("sections"):
        _fill_sections(tmpl, data, ws, col_defs, start, table_rows, row_h, dr)
        return

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
                {"h": "left", "v": "top", "wrap": True},
                border_spec,
            )
            continue

        col_names = table.get("columns", [])
        seen: dict[str, int] = {}
        pos_values = []
        for col_name in col_names:
            cnt = seen.get(col_name, 0)
            seen[col_name] = cnt + 1
            if cnt == 0:
                pos_values.append(row_data.get(col_name, "") if row_data else "")
            else:
                dedup_key = f"{col_name}_{cnt + 1}" if col_name else f"_{cnt + 1}"
                pos_values.append(row_data.get(dedup_key, "") if row_data else "")

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
            _write_cell(
                ws, r, col_def["col"], col_def["end_col"], r,
                value, col_def["font"], col_def["align"], border_spec,
            )

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = tmpl.get("footer")
    if footer:
        # If we added extra data rows, shift the footer down accordingly
        extra = max(0, n_rows - count)
        footer_fill = footer.get("fill")
        footer_col_names = table.get("columns", [])
        footer_seen: dict[str, int] = {}
        footer_pos: list[str] = []
        for cn in footer_col_names:
            cnt = footer_seen.get(cn, 0)
            footer_seen[cn] = cnt + 1
            if cnt == 0:
                footer_pos.append(footer_row_data.get(cn, "") if footer_row_data else "")
            else:
                dk = f"{cn}_{cnt+1}" if cn else f"_{cnt+1}"
                footer_pos.append(footer_row_data.get(dk, "") if footer_row_data else "")
        for cell in footer["cells"]:
            fr = footer["row"] + extra
            ws.row_dimensions[fr].height = footer.get("height", 30)
            if "col_index" in cell:
                idx = cell["col_index"]
                value = footer_pos[idx] if idx < len(footer_pos) else ""
            elif cell.get("fixed", False):
                value = cell.get("value", "")
            else:
                key = cell.get("key", "")
                if key == "_full_width":
                    rows = data.get("table", {}).get("rows", [])
                    fw = next((r["_full_width"] for r in rows if "_full_width" in r), "")
                    value = fw
                else:
                    value = footer_row_data.get(key, "") if footer_row_data else data.get(key, "")
            _write_cell(
                ws, fr, cell["col"], cell["end_col"], fr,
                value,
                cell["font"], cell["align"], cell["border"],
                cell.get("fill") or footer_fill,
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


def blank_xlsx(template_id: str, xlsx_path: str) -> None:
    templates = _load_templates()
    tmpl = next((t for t in templates if t["id"] == template_id), None)
    if tmpl is None:
        ids = [t["id"] for t in templates]
        raise ValueError(f"Template '{template_id}' not found. Available: {ids}")
    data = {"title": "", "section_header": "", "header": {}, "table": {"columns": [], "rows": []}}
    wb = Workbook()
    ws = wb.active
    fill_template(tmpl, data, ws)
    wb.save(xlsx_path)
    import sys
    print(f"Saved blank {xlsx_path} (template: {tmpl['id']})", file=sys.stderr)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("json_path", nargs="?")
    p.add_argument("xlsx_path", nargs="?")
    p.add_argument("--blank", metavar="TEMPLATE_ID", help="Generate a blank sheet for the given template ID")
    args = p.parse_args()

    if args.blank:
        out = args.json_path or args.xlsx_path or f"{args.blank}_blank.xlsx"
        blank_xlsx(args.blank, out)
    else:
        if not args.json_path:
            p.error("json_path is required unless --blank is used")
        xlsx_path = args.xlsx_path or str(Path(args.json_path).with_suffix(".xlsx"))
        json_to_xlsx(args.json_path, xlsx_path)


if __name__ == "__main__":
    main()
