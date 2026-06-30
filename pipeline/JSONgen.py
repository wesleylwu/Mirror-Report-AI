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
from PIL import Image, ImageOps

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
      {
        "<column header>": "<cell text, or empty string if blank>",
        ...
      }
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

TABLE COLUMNS: Column header strings in left-to-right order.

TABLE ROWS: Each data row as an object keyed by column header.
- Do NOT emit a row whose values are just the column header names.
- Include subtotal and grand total rows — do not skip rows because they contain summary labels like 計 or 合計.
- Blank cells: "".
- If two or more columns share the same header text, append _2, _3, etc. to the duplicates (e.g. "達成%" and "達成%_2") so every key in a row object is unique. This applies even when the shared header text is "".
- The last row(s) of the table may be a full-width text row spanning all columns — output it as a special entry: {"_full_width": "<text>"}.
Return ONLY the raw JSON object. No explanation, no markdown fences."""

MAX_IMAGE_PX = 3000


def _auto_orient(img: Image.Image) -> Image.Image:
    """Pick the rotation (0/90/180/270) where text lines are horizontal and
    the document is top-heavy (title/headers at top have more ink than bottom).
    Variance of horizontal projection picks the correct axis; top-vs-bottom ink
    density breaks the 0° vs 180° tie."""
    img = ImageOps.exif_transpose(img)
    candidates = []
    for angle in (0, 90, 180, 270):
        rotated = img.rotate(angle, expand=True)
        gray = np.array(rotated.convert("L"))
        inv = (255 - gray).astype(float)
        h = inv.shape[0]
        row_sums = inv.sum(axis=1)
        var_score = float(np.var(row_sums))
        top_density = inv[:h // 4].mean()
        bot_density = inv[3 * h // 4:].mean()
        top_bias = float(top_density - bot_density)
        # Variance of row sums in top quarter: lower = better (correct top is
        # consistent header area; wrong orientation's top has background contrast)
        top_q_var = float(np.var(row_sums[:h // 4]))
        candidates.append((var_score, top_bias, top_q_var, rotated))

    max_var = max(c[0] for c in candidates) or 1.0
    max_tqv = max(c[2] for c in candidates) or 1.0
    best = max(candidates, key=lambda c: c[0] / max_var + c[1] / 255 - 0.05 * c[2] / max_tqv)
    return best[3]


def _deskew(img: Image.Image) -> Image.Image:
    img = _auto_orient(img)
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
        return img
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
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))


def extract_text_from_image(img: Image.Image, debug_name: str = "image") -> dict:
    img = _deskew(img)
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
