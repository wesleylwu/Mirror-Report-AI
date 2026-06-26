"""Derive Excel layout metrics from a document image using OpenCV.

Given a deskewed PIL image and a list of table column names (from the text
extraction pass), this module returns:
  - column_widths  : {col_name: char_width} proportional to pixel widths
  - row_height     : 1 | 2 | 3  (table data row height multiplier)
  - blank_rows     : int  (empty pre-printed rows at the bottom of the table)
  - header_layout  : per-row list of (label_span, value_span) for header cells
  - header_heights : per-row height multiplier for header rows
"""
import cv2
import numpy as np
from PIL import Image


# ── Image helpers ──────────────────────────────────────────────────────────

def _to_gray_thresh(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Return (gray, binary-inverted-thresh) for a PIL image."""
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return gray, thresh


def _morph_lines(thresh: np.ndarray, horizontal: bool, min_ratio: float = 0.15
                 ) -> np.ndarray:
    """Extract horizontal or vertical lines via morphological open."""
    h, w = thresh.shape
    length = int((w if horizontal else h) * min_ratio)
    length = max(length, 10)
    ksize = (length, 1) if horizontal else (1, length)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize)
    return cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)


def _cluster(positions: list[int], gap: int = 6) -> list[int]:
    """Merge positions within `gap` pixels into their mean."""
    if not positions:
        return []
    out, group = [], [positions[0]]
    for p in sorted(positions)[1:]:
        if p - group[-1] <= gap:
            group.append(p)
        else:
            out.append(int(np.mean(group)))
            group = [p]
    out.append(int(np.mean(group)))
    return out


def _line_positions(line_img: np.ndarray, axis: int,
                    min_coverage: float = 0.10) -> list[int]:
    """Return sorted pixel indices where a line image has significant ink."""
    proj = np.sum(line_img, axis=axis)
    dim  = line_img.shape[1 - axis]
    threshold = dim * min_coverage * 255
    raw = [int(i) for i, v in enumerate(proj) if v >= threshold]
    return _cluster(raw)


# ── Region segmentation ────────────────────────────────────────────────────

def _find_table_top(h_positions: list[int], img_height: int,
                    min_frac: float = 0.15) -> int:
    """Return the y-coordinate where the table grid begins.

    Heuristic: find the first horizontal line below min_frac of the image
    that is followed by regularly-spaced lines (= table rows).
    """
    lower_bound = int(img_height * min_frac)
    lower_lines = [y for y in h_positions if y > lower_bound]
    if len(lower_lines) < 2:
        return int(img_height * 0.4)

    gaps = [lower_lines[i + 1] - lower_lines[i]
            for i in range(len(lower_lines) - 1)]
    median_gap = float(np.median(gaps))

    # Walk forward until we find a run of at least 3 evenly-spaced lines
    for i in range(len(gaps) - 2):
        run = [gaps[i], gaps[i + 1], gaps[i + 2]]
        if all(abs(g - median_gap) < median_gap * 0.4 for g in run):
            return lower_lines[i]

    return lower_lines[0]


# ── Public API ─────────────────────────────────────────────────────────────

def analyze(
    img: Image.Image,
    col_names: list[str],
    n_header_rows: int,
) -> dict:
    """Analyze layout of a deskewed document image.

    Parameters
    ----------
    img          : deskewed PIL Image
    col_names    : table column names in order (from Claude text pass)
    n_header_rows: number of header rows (from Claude text pass, including title)

    Returns
    -------
    dict with keys:
        column_widths  : {name: int}
        row_height     : 1 | 2 | 3
        blank_rows     : int
        header_heights : [int, ...]  one per header row
        header_spans   : [[(label_span, value_span), ...], ...]  one list per row
        total_span     : int  grid column count
    """
    img_w, img_h = img.size
    _, thresh = _to_gray_thresh(img)

    h_lines = _morph_lines(thresh, horizontal=True, min_ratio=0.15)
    h_pos = _line_positions(h_lines, axis=1)  # y positions

    if not h_pos or h_pos[0] > 5:
        h_pos = [0] + h_pos
    if not h_pos or h_pos[-1] < img_h - 5:
        h_pos = h_pos + [img_h]

    table_top_y = _find_table_top(h_pos, img_h)

    # ── Table column widths ────────────────────────────────────────────────
    # Use a column-ink-projection approach in the table region: sum ink
    # density per x-column — separators show up as spikes of high ink.
    table_thresh = thresh[table_top_y:, :]
    col_proj = np.sum(table_thresh.astype(np.float32), axis=0) / 255.0
    table_h_px = table_thresh.shape[0]

    # A separator column has ink in most rows (≥30% of table height)
    sep_threshold = table_h_px * 0.30
    raw_seps = [x for x, v in enumerate(col_proj) if v >= sep_threshold]
    v_pos = _cluster(raw_seps, gap=4)

    # Drop separators that are just the document border (within 3% of each edge)
    edge_margin = int(img_w * 0.03)
    v_pos = [x for x in v_pos if edge_margin < x < img_w - edge_margin]

    # Add true image boundaries
    v_pos = [0] + v_pos + [img_w]

    col_px_widths = [v_pos[i + 1] - v_pos[i]
                     for i in range(len(v_pos) - 1)]

    # We need exactly len(col_names) column widths.
    # If OpenCV found more or fewer segments, fall back to equal widths.
    if len(col_px_widths) == len(col_names):
        import math
        # Sqrt-scale pixel widths to reduce dominance of wide columns.
        # This balances the grid so header labels (which fall on the same
        # grid columns) aren't forced to be as wide as the table's widest column.
        scaled = [math.sqrt(w) for w in col_px_widths]
        total_scaled = sum(scaled)
        BASE_CHARS = 140
        column_widths = {
            name: max(8, round(scaled[i] / total_scaled * BASE_CHARS))
            for i, name in enumerate(col_names)
        }
    else:
        # Fallback: equal widths
        column_widths = {name: 15 for name in col_names}

    # ── Table row heights ──────────────────────────────────────────────────
    table_h_pos = [y for y in h_pos if y >= table_top_y]
    if len(table_h_pos) >= 2:
        row_px_heights = [table_h_pos[i + 1] - table_h_pos[i]
                          for i in range(len(table_h_pos) - 1)]
        # Skip the first two (column header rows)
        data_heights = row_px_heights[2:] if len(row_px_heights) > 2 else row_px_heights
        if data_heights:
            median_h = float(np.median(data_heights))
            # Classify: ≤18px=1, ≤30px=2, else=3 (at 1568px wide image scale)
            # Normalise against image height for scale-independence
            norm = median_h / img_h
            if norm < 0.035:
                row_height = 1
            elif norm < 0.06:
                row_height = 2
            else:
                row_height = 3
        else:
            row_height = 2
    else:
        row_height = 2

    # ── Blank rows ─────────────────────────────────────────────────────────
    # Count rows below data where ink density is very low.
    blank_rows = 0
    if len(table_h_pos) >= 4:
        data_row_heights = [table_h_pos[i + 1] - table_h_pos[i]
                            for i in range(2, len(table_h_pos) - 1)]
        gray_arr, _ = _to_gray_thresh(img)
        # Invert so ink = high value
        ink = 255 - gray_arr
        for i, rh in enumerate(data_row_heights):
            y1 = table_h_pos[i + 2]
            y2 = table_h_pos[i + 3] if i + 3 < len(table_h_pos) else img_h
            x1, x2 = v_pos[0], v_pos[-1]
            region = ink[y1:y2, x1:x2]
            density = np.mean(region) / 255.0
            if density < 0.015:  # very little ink = blank row
                blank_rows += 1

    # ── Header row heights & cell spans ───────────────────────────────────
    header_h_pos = [y for y in h_pos if y <= table_top_y]
    if not header_h_pos or header_h_pos[0] > 5:
        header_h_pos = [0] + header_h_pos
    if header_h_pos[-1] < table_top_y:
        header_h_pos.append(table_top_y)

    header_row_px = [header_h_pos[i + 1] - header_h_pos[i]
                     for i in range(len(header_h_pos) - 1)]

    # Normalise header row heights to 1/2/3
    if header_row_px:
        median_hdr = float(np.median(header_row_px))
        def _classify_h(px: int) -> int:
            if px >= median_hdr * 2.2:
                return 3
            if px >= median_hdr * 1.4:
                return 2
            return 1
        header_heights = [_classify_h(px) for px in header_row_px]
    else:
        header_heights = [1] * n_header_rows

    # Pad / trim to match n_header_rows
    while len(header_heights) < n_header_rows:
        header_heights.append(1)
    header_heights = header_heights[:n_header_rows]

    # ── Header cell spans ──────────────────────────────────────────────────
    # Use the same vertical positions as the table columns to define a grid,
    # then express each header cell as a number of grid columns.
    # Since we don't know the cell boundaries independently, we use the
    # table's vertical grid as the underlying unit system and assume header
    # labels/values align to those same column boundaries.
    n_grid = len(col_px_widths) if col_px_widths else len(col_names)
    # Provide a flat fallback — caller can override with Claude-detected spans.
    header_spans = None  # signals "use Claude spans"

    return {
        "column_widths": column_widths,
        "row_height": row_height,
        "blank_rows": blank_rows,
        "header_heights": header_heights,
        "header_spans": header_spans,
        "total_span": n_grid,
        # Debug info
        "_h_pos": h_pos,
        "_v_pos": v_pos,
        "_table_top_y": table_top_y,
    }
