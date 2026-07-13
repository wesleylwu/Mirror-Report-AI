"""Render an HTML table from a cell-grid JSON produced by JSONgen.

Produces a pixel-accurate visual representation of the spreadsheet template
that mirrors what XLSXgen writes to Excel.

Usage:
    python SVGgen.py <json_path> [output.html]
"""
import json
import sys
import html as _html
from pathlib import Path
from html.parser import HTMLParser
import re


PX_PER_CHAR = 7.0   # approximate px width per character-unit column width
PX_PER_PT   = 1.33  # approximate px height per point row height
MIN_COL_PX  = 28.0
MIN_ROW_PX  = 16.0
FONT_PX     = 11
CELL_PAD_H  = 4     # horizontal padding (px) inside a cell
CELL_PAD_V  = 2     # vertical padding (px) inside a cell


def render_html(data: dict) -> str:
    col_widths = data.get("col_widths") or []
    rows_raw   = data.get("rows") or []
    num_cols   = int(data.get("num_cols") or len(col_widths) or 1)
    num_rows   = int(data.get("num_rows") or len(rows_raw))

    col_px = [max(MIN_COL_PX, float(w) * PX_PER_CHAR) for w in col_widths]
    while len(col_px) < num_cols:
        col_px.append(MIN_COL_PX)

    # Build lookup: explicit row number → row dict (supports sparse rows)
    row_by_r: dict[int, dict] = {}
    for idx, row in enumerate(rows_raw):
        r = row.get("r") or row.get("row") or (idx + 1)
        row_by_r[int(r)] = row

    # Reconstruct full sequence 1..num_rows; missing rows are empty
    rows = [row_by_r.get(r, {}) for r in range(1, num_rows + 1)]

    parts = [
        "<table style=\""
        "border-collapse: collapse; "
        f"font-family: Arial, sans-serif; font-size: {FONT_PX}px; "
        "background: white; "
        "table-layout: fixed;"
        "\">",
        "<colgroup>",
    ]
    for w in col_px:
        parts.append(f'<col style="width: {w:.0f}px"/>')
    parts.append("</colgroup>")

    for r_idx, row in enumerate(rows, start=1):
        try:
            rh = max(MIN_ROW_PX, float(row.get("h") or row.get("height") or 15) * PX_PER_PT)
        except (ValueError, TypeError):
            rh = MIN_ROW_PX

        parts.append(f'<tr style="height: {rh:.0f}px">')

        cells = row.get("cells") or []
        col_cursor = 1

        def _empty_td(n: int) -> None:
            if n <= 0:
                return
            colspan_attr = f' colspan="{n}"' if n > 1 else ""
            parts.append(f'<td{colspan_attr} style="padding:0;border:none"></td>')

        for cell in cells:
            try:
                col  = int(cell.get("c") or cell.get("col") or col_cursor)
                span = max(1, int(cell.get("s") or cell.get("span") or 1))
            except (ValueError, TypeError):
                col, span = col_cursor, 1

            _empty_td(col - col_cursor)

            value      = str(cell.get("v") or cell.get("value") or "")
            bold       = bool(cell.get("b") or cell.get("bold") or False)
            align      = cell.get("a") or cell.get("align") or "left"
            fill_hex   = cell.get("f") or cell.get("fill")
            border_val = "all" if cell.get("x") else (cell.get("border") or "none")

            styles = [
                f"padding: {CELL_PAD_V}px {CELL_PAD_H}px",
                f"text-align: {align}",
                "vertical-align: middle",
                "overflow: hidden",
                "white-space: nowrap",
            ]
            if bold:
                styles.append("font-weight: bold")
            if fill_hex:
                styles.append(f"background-color: {fill_hex}")
            if border_val == "all":
                styles.append("border: 1px solid #888888")
            else:
                styles.append("border: none")

            colspan_attr = f' colspan="{span}"' if span > 1 else ""
            parts.append(
                f'<td{colspan_attr} contenteditable="true" data-row="{r_idx}" data-col="{col}" style="{"; ".join(styles)}">{_html.escape(value)}</td>'
            )
            col_cursor = col + span

        # Fill any trailing gap at the end of the row
        _empty_td(num_cols - col_cursor + 1)

        parts.append("</tr>")

    parts.append("</table>")
    return "\n".join(parts)


class HTMLPopulator(HTMLParser):
    def __init__(self, data_list):
        super().__init__()
        self.data_map = {}
        for item in (data_list or []):
            r = item.get("r") or item.get("row")
            c = item.get("c") or item.get("col")
            v = item.get("v") or item.get("value")
            if r is not None and c is not None and v is not None:
                self.data_map[(int(r), int(c))] = str(v)
        
        self.output = []
        self.current_row = 0
        self.current_col = 1
        self.in_td = False
        self.td_attrs = []
        self.td_content = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current_row += 1
            self.current_col = 1
            self.output.append(f"<tr{self._render_attrs(attrs)}>")
        elif tag == "td":
            self.in_td = True
            self.td_attrs = attrs
            self.td_content = []
        else:
            attr_str = self._render_attrs(attrs)
            tag_str = f"<{tag}{attr_str}>"
            if self.in_td:
                self.td_content.append(tag_str)
            else:
                self.output.append(tag_str)

    def handle_endtag(self, tag):
        if tag == "tr":
            self.output.append("</tr>")
        elif tag == "td":
            self.in_td = False
            colspan = 1
            for name, val in self.td_attrs:
                if name == "colspan":
                    try:
                        colspan = int(val)
                    except ValueError:
                        pass
            
            val = self.data_map.get((self.current_row, self.current_col))
            if val is not None:
                content_str = _html.escape(val).replace("\n", "<br>")
            else:
                content_str = "".join(self.td_content)
                
            # Add contenteditable, data-row and data-col to attributes for frontend editing
            new_attrs = []
            has_editable = False
            for name, val in self.td_attrs:
                if name == "contenteditable":
                    has_editable = True
                new_attrs.append((name, val))
            
            if not has_editable:
                new_attrs.append(("contenteditable", "true"))
            new_attrs.append(("data-row", str(self.current_row)))
            new_attrs.append(("data-col", str(self.current_col)))
            
            attr_str = self._render_attrs(new_attrs)
            self.output.append(f"<td{attr_str}>{content_str}</td>")
            self.current_col += colspan
        else:
            tag_str = f"</{tag}>"
            if self.in_td:
                self.td_content.append(tag_str)
            else:
                self.output.append(tag_str)

    def handle_data(self, data):
        if self.in_td:
            self.td_content.append(data)
        else:
            self.output.append(data)

    def _render_attrs(self, attrs):
        if not attrs:
            return ""
        parts = []
        for name, val in attrs:
            if val is not None:
                parts.append(f'{name}="{val}"')
            else:
                parts.append(name)
        return " " + " ".join(parts)


def populate_html_with_data(html_str: str, data_list: list) -> str:
    populator = HTMLPopulator(data_list)
    populator.feed(html_str)
    return "".join(populator.output)


def _sheet_name_from_page(page_data: dict, idx: int) -> str:
    code = page_data.get("code", "")
    if code:
        m = re.search(r'ws\.title\s*=\s*["\']([^"\']+)["\']', code)
        if m:
            return re.sub(r'[:\\/?*\[\]]', '', m.group(1))[:30].strip()
    tmpl = page_data.get("template") or page_data
    name = str(tmpl.get("sheet_name") or f"Sheet {idx + 1}")
    return re.sub(r'[:\\/?*\[\]]', '', name)[:30].strip() or f"Page {idx + 1}"


def get_html_content(page_data: dict) -> str:
    raw_html = page_data.get("html")
    data_list = page_data.get("data")
    if raw_html:
        if data_list:
            return populate_html_with_data(raw_html, data_list)
        return raw_html
    tmpl = page_data.get("template") or page_data
    return render_html(tmpl)


def json_to_html(json_path: str, html_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    pages = data.get("pages")
    if pages is None:
        pages = [data]

    for idx, page_data in enumerate(pages):
        if "error" in page_data:
            continue

        if len(pages) == 1:
            out = html_path
        else:
            p = Path(html_path)
            out = str(p.parent / f"{p.stem}_{idx + 1}{p.suffix}")

        table_html = get_html_content(page_data)
        sheet_name = _html.escape(_sheet_name_from_page(page_data, idx))
        full_html = (
            "<!DOCTYPE html>\n<html>\n<head>"
            f'<meta charset="utf-8"><title>{sheet_name}</title>'
            "</head>\n<body style=\"margin:16px\">\n"
            f"<h2>{sheet_name}</h2>\n"
            f"{table_html}\n"
            "</body>\n</html>"
        )
        with open(out, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"Saved {out}", file=sys.stderr)


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("json_path")
    p.add_argument("html_path", nargs="?")
    args = p.parse_args()
    html_path = args.html_path or str(Path(args.json_path).with_suffix(".html"))
    json_to_html(args.json_path, html_path)


if __name__ == "__main__":
    main()
