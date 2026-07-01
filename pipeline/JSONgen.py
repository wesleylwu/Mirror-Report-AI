"""Extract text content from document images/PDFs using Claude.

Outputs a flat JSON with title, section_header, header key/value pairs,
and table rows. Layout is handled entirely by XLSXgen via templates.
Outputs a unified JSON with a "pages" array containing extracted fields for each page.

Usage:
    python JSONgen.py <input_path1> [<input_path2> ...] [output.json]

Requires the ANTHROPIC_API_KEY environment variable to be set.
"""
import base64
import io
import json
import re
import sys
import time
import concurrent.futures
from pathlib import Path

import anthropic
import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageOps

MODEL_HAIKU  = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL = MODEL_SONNET  # default; overridden by --sonnet flag at runtime

PROMPT = """You are a precise document digitizer. Extract ONLY the text visible in the image. Do not infer, guess, or fill in values.

VALIDATION RULE:
- Inspect the image first. If the image is not a printed document or manufacturing report (e.g., if it is a photo of a person, animal, food, scenery, or any random physical object/scene), or if it is too blurry or dark to read, you MUST return a JSON with an "error" key:
  {"error": "invalid_document", "message": "The uploaded image does not appear to be a valid manufacturing document."}

CRITICAL RULES:
- Transcribe ONLY pre-printed text. Ignore handwriting, stamps, and pen marks.
- If a field value is blank or illegible, output "".
- Read every character directly from the image. Do NOT approximate, simplify, or substitute similar-looking characters — transcribe exactly what is printed, including every kanji, kana, alphanumeric character, symbol, and punctuation mark.
- Pay close attention to characters that look similar: e.g. ン vs ソ, サ vs セ, 両 vs 吋, ド vs ト. Zoom in mentally on each character before committing.
- Product names, codes, and field values must be transcribed in full — do not truncate or paraphrase.

Return a single JSON object with this exact schema:

{
  "title": "<full-width title text at the very top of the document, e.g. 製造指図書>",
  "section_header": "<full-width section title between the header fields and the data table, e.g. 調合票. Empty string if none.>",
  "header": {
    "<label text exactly as printed>": "<value text, or empty string if blank>",
    ...
  },
  "table": {
    "columns": ["<column header 1>", "<column header 2>", ...],
    "rows": [
      ["<cell text for column 1>", "<cell text for column 2>", ...],
      ...
    ]
  }
}

RULES:

TITLE: The full-width text spanning the top of the document (e.g. 製造指図書). Do not include it in header.

HEADER FIELDS: Every label/value pair in the metadata section above the data table.
- Use the EXACT printed label text as the key (e.g. "手配No.", "発行日", "品目CD").
- Capture the COMPLETE text within each value cell — a cell may contain multiple words or tokens separated by spaces (e.g. "30 噴霧", "20 仕込"). Transcribe ALL of them as one string.
- If a field has no value printed, still include it with value "".
- Do NOT include the title or section header in this dict.

SECTION HEADER: A full-width label separating the header fields from the data table (e.g. 調合票). Empty string if none.

TABLE COLUMNS: Column header strings in left-to-right order. Blank/unlabeled columns are still counted — include an empty string "" at their position.

TABLE ROWS: Each data row as an ARRAY of cell-text strings, in the exact same left-to-right order as TABLE COLUMNS. Every row array must have exactly as many entries as TABLE COLUMNS has — one entry per column position, including blank/unlabeled columns. This positional format means you never need to invent or repeat a key, so just transcribe what you see in each column, left to right.
- Do NOT emit a row whose values are just the column header names.
- Include subtotal and grand total rows — do not skip rows because they contain summary labels like 計 or 合計.
- Blank cells: "".
- The last row(s) of the table may be a full-width text row spanning all columns — output it as a special entry: {"_full_width": "<text>"} (an object, not an array) instead of a normal row.
Return ONLY the raw JSON object. No explanation, no markdown fences."""

MAX_IMAGE_PX = 3000


def _heuristic_rotation(img: Image.Image) -> int:
    """Pixel-statistics rotation guess: axis (portrait vs sideways) from
    row/col projection variance, then CW vs CCW and upside-down checks from
    ink density in top vs bottom strips. Independent signal from the model-
    based detector, used to cross-check it."""
    gray = np.array(img.convert("L"))
    inv = (255 - gray).astype(float)
    row_var = float(np.var(inv.sum(axis=1)))
    col_var = float(np.var(inv.sum(axis=0)))

    def _strip_ratio(candidate: Image.Image, pct: int) -> float:
        g = np.array(candidate.convert("L"))
        v = (255 - g).astype(float)
        rs = v.sum(axis=1)
        rh = len(rs)
        m = max(1, rh * pct // 100)
        bot = float(rs[rh - m:].mean()) or 1.0
        return float(rs[:m].mean()) / bot

    angle = 0
    base = img
    if col_var > row_var:
        cw  = img.rotate(270, expand=True)
        ccw = img.rotate(90,  expand=True)
        if _strip_ratio(cw, 25) >= _strip_ratio(ccw, 25):
            angle, base = 270, cw
        else:
            angle, base = 90, ccw

    if _strip_ratio(base, 5) > 1.5:
        angle = (angle + 180) % 360

    return angle


_LETTERS = "ABCD"


def _model_pick_rotation(img: Image.Image, candidates: list[int], model: str = MODEL_HAIKU) -> tuple[int, int, int]:
    """Ask the model to pick which of the given candidate rotations reads
    correctly, using a cropped high-res strip of just the top edge of each
    (where a title/header normally sits) rather than a shrunk full-page
    thumbnail — full-page thumbnails made dense tables illegible, causing
    the model to effectively guess.
    Returns (angle, input_tokens, output_tokens); first candidate on failure."""
    letters = _LETTERS[:len(candidates)]
    angle_by_letter = dict(zip(letters, candidates))
    strip_w = 900
    strips = []
    for letter, angle in angle_by_letter.items():
        cand = img.rotate(angle, expand=True).convert("RGB")
        # top ~22% of the page height, full width
        crop_h = max(1, int(cand.height * 0.22))
        crop = cand.crop((0, 0, cand.width, crop_h))
        scale = strip_w / crop.width
        crop = crop.resize((strip_w, max(1, int(crop.height * scale))), Image.LANCZOS)
        strips.append((letter, crop))

    label_w = 40
    total_h = sum(c.height for _, c in strips)
    grid = Image.new("RGB", (label_w + strip_w, total_h), "white")
    draw = ImageDraw.Draw(grid)
    y = 0
    for letter, crop in strips:
        draw.text((8, y + crop.height // 2 - 8), letter, fill="black")
        grid.paste(crop, (label_w, y))
        y += crop.height

    prompt = (
        f"This image stacks {len(candidates)} horizontal strips, each a crop of the "
        "very top edge of the same document page rotated differently, labeled at "
        f"the left: {', '.join(letters)} from top to bottom. Exactly one strip has "
        "text that reads upright, left-to-right (titles/headers, not sideways or "
        f"upside-down). Which one is it? Reply with ONLY the letter: {'/'.join(letters)}."
    )

    buf = io.BytesIO()
    grid.save(buf, format="JPEG", quality=90)
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=model, max_tokens=10, temperature=0,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        in_tok = message.usage.input_tokens
        out_tok = message.usage.output_tokens
        text = message.content[0].text.strip().upper()
        m = re.search(f"[{letters}]", text)
        if m:
            return angle_by_letter[m.group()], in_tok, out_tok
        return candidates[0], in_tok, out_tok
    except Exception as e:
        print(f"Rotation detection failed, defaulting to candidates[0]: {e}", file=sys.stderr)
    return candidates[0], 0, 0


def _auto_orient(img: Image.Image) -> tuple[Image.Image, int, int, int, int]:
    """Correct orientation by cross-checking a pixel-statistics heuristic
    against the model's own reading of the text. When they agree, that's a
    strong signal and costs nothing extra. When they disagree, a focused
    2-way comparison on Sonnet (stronger than Haiku, which has shown a
    specific blind spot on some images even with an unambiguous 2-way
    choice) breaks the tie — fully automatic, no manual review.
    Returns (img, base_input_tokens, base_output_tokens, tiebreak_input_tokens,
    tiebreak_output_tokens) — tiebreak counters are 0 when not triggered."""
    img = ImageOps.exif_transpose(img)
    heuristic_angle = _heuristic_rotation(img)
    model_angle, in_tok, out_tok = _model_pick_rotation(img, [0, 90, 180, 270])

    tie_in = tie_out = 0
    if heuristic_angle == model_angle:
        angle = model_angle
    else:
        angle, tie_in, tie_out = _model_pick_rotation(img, [heuristic_angle, model_angle], model=MODEL_SONNET)

    if angle:
        img = img.rotate(angle, expand=True)
    return img, in_tok, out_tok, tie_in, tie_out


def _deskew(img: Image.Image) -> tuple[Image.Image, int, int, int, int]:
    img, orient_in, orient_out, tie_in, tie_out = _auto_orient(img)
    cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    gray = cv2.bitwise_not(gray)
    contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    quad = None
    h, w = cv.shape[:2]
    min_area = w * h * 0.10
    for cnt in contours[:5]:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(cnt) > min_area:
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        return img, orient_in, orient_out, tie_in, tie_out
    s = quad.sum(axis=1)
    diff = np.diff(quad, axis=1)
    ordered = np.array([
        quad[np.argmin(s)], quad[np.argmin(diff)],
        quad[np.argmax(s)], quad[np.argmax(diff)],
    ], dtype=np.float32)
    w_top  = np.linalg.norm(ordered[1] - ordered[0])
    w_bot  = np.linalg.norm(ordered[2] - ordered[3])
    h_left = np.linalg.norm(ordered[3] - ordered[0])
    h_right= np.linalg.norm(ordered[2] - ordered[1])
    out_w, out_h = int(max(w_top, w_bot)), int(max(h_left, h_right))
    # Add output padding so edge content isn't clipped — extra vertical padding
    # since title/page-info text often sits just outside the table's own border
    pad_px_x = int(out_w * 0.03)
    pad_px_y = int(out_h * 0.15)
    canvas_w = out_w + 2 * pad_px_x
    canvas_h = out_h + 2 * pad_px_y
    dst = np.array([
        [pad_px_x,         pad_px_y        ],
        [pad_px_x + out_w, pad_px_y        ],
        [pad_px_x + out_w, pad_px_y + out_h],
        [pad_px_x,         pad_px_y + out_h],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(cv, M, (canvas_w, canvas_h))
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)), orient_in, orient_out, tie_in, tie_out


def extract_text_from_image(img: Image.Image, debug_name: str = "image") -> dict:
    img, orient_in, orient_out, tie_in, tie_out = _deskew(img)
    img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_PX:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    client = anthropic.Anthropic()
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": PROMPT, "cache_control": {"type": "ephemeral"}},
        ],
    }]

    accumulated = ""
    total_input = total_output = total_cache_read = total_cache_write = 0

    while True:
        turn = len([m for m in messages if m["role"] == "user"])
        chars = 0
        with client.messages.stream(
            model=MODEL, max_tokens=8192, temperature=0, messages=messages,
        ) as stream:
            for text in stream.text_stream:
                chars += len(text)
                print(f"\r  Turn {turn} — {chars:,} chars...", end="", flush=True)
            print()
            message = stream.get_final_message()

        total_input  += message.usage.input_tokens
        total_output += message.usage.output_tokens
        total_cache_read  += getattr(message.usage, "cache_read_input_tokens", 0) or 0
        total_cache_write += getattr(message.usage, "cache_creation_input_tokens", 0) or 0

        chunk = message.content[0].text
        accumulated += chunk
        if message.stop_reason != "max_tokens":
            break
        messages.append({"role": "assistant", "content": chunk})
        tail = accumulated[-120:].replace('"', '\\"')
        messages.append({"role": "user", "content": f'The JSON was cut off. Continue outputting raw JSON from exactly where it stopped. The last characters output were: "...{tail}". Do NOT restart. Do NOT repeat any output. Continue from that exact point.'})

    print(
        f"[{debug_name}] Orientation tokens — input: {orient_in}, output: {orient_out}, "
        f"total: {orient_in + orient_out}",
        file=sys.stderr,
    )
    print(
        f"[{debug_name}] Orientation tiebreak tokens (Sonnet, only when heuristic and "
        f"Haiku disagree) — input: {tie_in}, output: {tie_out}, total: {tie_in + tie_out}",
        file=sys.stderr,
    )
    print(
        f"[{debug_name}] Tokens — input: {total_input}, output: {total_output}, "
        f"total: {total_input + total_output} "
        f"(cache write: {total_cache_write}, read: {total_cache_read})",
        file=sys.stderr,
    )

    text = accumulated.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    # Strip stray code-fence markers and invalid control characters
    text = re.sub(r"```[a-z]*\n?", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    def _check_error(data: dict) -> dict:
        if "error" in data:
            raise ValueError(data.get("message") or f"Invalid document in {debug_name}.")
        return data

    try:
        return _check_error(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Model may have restarted mid-stream — find the last top-level { and try it
    last_start = text.rfind('\n{')
    if last_start > 0:
        try:
            return _check_error(json.loads(text[last_start + 1:]))
        except json.JSONDecodeError:
            pass

    # Truncate at the last complete row and close the JSON structure
    try:
        err_pos = None
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            err_pos = e.pos
        if err_pos:
            for pattern, closing in [
                ('\n      },', '\n    ]\n  }\n}'),
                ('\n      }',  '\n    ]\n  }\n}'),
                ('\n    },',   '\n  }\n}'),
                ('\n    }',    '\n  }\n}'),
            ]:
                pos = text.rfind(pattern, 0, err_pos)
                if pos > 0:
                    fixed = text[:pos + len(pattern.rstrip(','))] + closing
                    try:
                        data = json.loads(fixed)
                        print(f"Warning: JSON truncated at pos {err_pos}, recovered {len(data.get('table',{}).get('rows',[]))} rows", file=sys.stderr)
                        return data
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    # Save raw response and return empty shell so the program can continue
    raw_path = debug_name + ".raw_response.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON parse error in {debug_name}: {e} — raw response saved to {raw_path}", file=sys.stderr)
    return {"title": "", "section_header": "", "header": {}, "table": {"columns": [], "rows": []}}


def extract_all(paths: list[str]) -> dict:
    tasks = []

    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            print(f"Error: path {path_str} does not exist", file=sys.stderr)
            continue

        if p.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(p)
                for page_idx in range(len(doc)):
                    page = doc.load_page(page_idx)
                    pix = page.get_pixmap(dpi=150)
                    img_data = pix.tobytes("jpeg")
                    img = Image.open(io.BytesIO(img_data))
                    tasks.append((img, f"{p.name} (page {page_idx + 1})"))
            except Exception as e:
                print(f"Error reading PDF {path_str}: {e}", file=sys.stderr)
                raise
        else:
            try:
                img = Image.open(p)
                tasks.append((img, p.name))
            except Exception as e:
                print(f"Error reading image {path_str}: {e}", file=sys.stderr)
                raise

    if not tasks:
        raise ValueError("No valid images or PDF pages found to process.")

    pages_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(extract_text_from_image, task[0], task[1]) for task in tasks]
        for f in futures:
            pages_data.append(f.result())

    return {"pages": pages_data}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="input image/PDF paths; if last arg ends in .json it is the output path")
    parser.add_argument("--sonnet", action="store_true", help="Use claude-sonnet-4-6 (already the default)")
    parser.add_argument("--haiku", action="store_true", help="Use claude-haiku-4-5 instead of the default Sonnet")
    args = parser.parse_args()

    global MODEL
    MODEL = MODEL_HAIKU if args.haiku else MODEL_SONNET
    print(f"Using model: {MODEL}", file=sys.stderr)

    paths = args.paths
    output_json = None
    if paths and paths[-1].endswith(".json"):
        output_json = paths[-1]
        input_paths = paths[:-1]
    else:
        input_paths = paths

    t0 = time.time()
    try:
        data = extract_all(input_paths)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(f"Elapsed: {time.time() - t0:.1f}s", file=sys.stderr)

    output = json.dumps(data, indent=2, ensure_ascii=False)

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {output_json}", file=sys.stderr)

        xlsx_path = str(Path(output_json).with_suffix(".xlsx"))
        from XLSXgen import json_to_xlsx
        json_to_xlsx(output_json, xlsx_path)
    else:
        print(output)


if __name__ == "__main__":
    main()
