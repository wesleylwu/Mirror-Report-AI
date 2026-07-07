"""Extract text content from document images/PDFs using Claude.

Outputs a flat JSON with title, section_header, positional header rows,
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
import threading
import concurrent.futures
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

import anthropic
import fitz  # PyMuPDF
from PIL import Image, ImageOps

_STOP = threading.Event()
_STOP_FILE = Path(__file__).parent / "STOP"

MODEL_HAIKU  = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL = MODEL_SONNET  # default; overridden by --haiku flag at runtime

PROMPT = """Analyze this document image and output exactly three sections. Begin each section with its marker on its own line exactly as shown. No explanation before the first marker. No markdown fences.

---TEMPLATE---
JSON object describing the blank form structure. Pre-printed labels and structure only — no filled-in values.
Read every character exactly — ン vs ソ, サ vs セ, 両 vs 吋.
{"sheet_name":"<name>","orientation":"portrait|landscape","col_widths":[<float>,...],"data_rows":<count of repeating data rows in original>,"rows":[{"h":<height>,"cells":[{"c":<col>,"s":<colspan>,"rs":<rowspan>,"v":"<label>","b":<bold>,"a":"left|center|right","x":<border>,"f":"<RRGGBB>"}]}]}
Rules:
- Before writing anything, count the columns by tracing each vertical line from top to bottom. Write the count in col_widths — one entry per column, no more, no less.
- col_widths in Excel character units: narrow=4-6, standard=8-12, wide=15-25. Never use pixel values.
- Do NOT pad "v" values with spaces. Cell width is set by col_widths only.
- Include narrow spacer columns. Count only rows within the outer border.
- Count the exact number of repeating data rows visible in the image and set "data_rows" to that count.
- In "rows": include ALL rows — headers, labels, AND all blank data rows in their correct positions.
- Blank data rows MUST have "v":"" (empty string) on every cell — NEVER put handwritten, typed, or stamped values in the template. Those go in DATA only.
- For runs of identical blank data rows (same height, same column pattern, no labels), use the compact form: {"h":<height>,"repeat":<count>,"cells":[...one row's cells...]} instead of repeating each row individually. This saves tokens.
- "x": REQUIRED on every cell with any visible border. true/"tlbr" = all sides, "b" = bottom only, "tb" = top+bottom, "lr" = left+right. Omit only for cells with zero visible borders.
- Every cell inside a ruled table, grid, or bordered box must have "x" set — including full-width title/section rows that span all columns. If the section is enclosed by any outer border at all, set "x": true.
- "f": hex only for visibly shaded cells, omit for white.

---HTML---
<table> of the blank form structure. Inline styles only. No <html>/<body> wrapper.
colspan/rowspan for merges, border:1px solid #000 for borders, background:#RRGGBB for shading.
<col style="width:Npx"> for widths, <tr style="height:Npx"> for heights. Pre-printed labels only.

---DATA---
JSON array — filled-in values only (handwritten, typed, stamped — NOT pre-printed labels):
[{"r":<row>,"c":<col>,"v":"<value>"},...]
Omit empty cells. Output at most 30 rows — if document has more, output first 30 only."""

MAX_IMAGE_PX = 2800


def _try_json(s: str):
    s = s.strip()
    # Fix common model error: "key">value  →  "key":value
    s = re.sub(r'"(\w+)">', r'"\1":', s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for end_ch in ('}', ']'):
        pos = s.rfind(end_ch)
        while pos > 0:
            try:
                return json.loads(s[:pos + 1])
            except json.JSONDecodeError:
                pos = s.rfind(end_ch, 0, pos)
    return None


def _parse_sections(raw: str) -> dict:
    """Split ---TEMPLATE--- / ---HTML--- / ---DATA--- sections from a combined response."""
    # Use the LAST occurrence of each marker — model sometimes self-restarts mid-output
    def _last(pattern):
        matches = list(re.finditer(pattern, raw))
        return matches[-1] if matches else None

    m_tmpl = _last(r'---TEMPLATE---\s*')
    m_html = _last(r'---HTML---\s*')
    m_data = _last(r'---DATA---\s*')

    markers = sorted(
        [(m, name) for m, name in [(m_tmpl, 'template'), (m_html, 'html'), (m_data, 'data')] if m],
        key=lambda x: x[0].start(),
    )

    sections: dict[str, str] = {}
    for i, (m, name) in enumerate(markers):
        end = markers[i + 1][0].start() if i + 1 < len(markers) else len(raw)
        sections[name] = re.sub(r'```[a-z]*\n?|```', '', raw[m.end():end]).strip()

    template_text = sections.get('template', '')
    html = sections.get('html', '')
    data_text = sections.get('data', '')

    # Fallback: if no ---TEMPLATE--- marker but raw starts with '{', treat whole
    # pre-HTML block as the template (model forgot the marker)
    if not template_text and not sections:
        html_start = m_html.start() if m_html else len(raw)
        candidate = re.sub(r'```[a-z]*\n?|```', '', raw[:html_start]).strip()
        # strip any leading prose line (e.g. "JSON object describing...")
        first_brace = candidate.find('{')
        if first_brace != -1:
            template_text = candidate[first_brace:]

    template = _try_json(template_text) if template_text else None
    data = _try_json(data_text) if data_text else []
    if not isinstance(data, list):
        data = []

    return {"template": template, "html": html, "data": data}


MAX_CONTINUATIONS = 2  # max extra turns after the first; 3 total turns max

def _stream_response(client, messages: list, label: str, max_tokens: int = 16000) -> tuple:
    """Stream one logical response, handling max_tokens continuation automatically.

    Mutates messages in-place when continuation turns are needed.
    Returns (text, input_tokens, output_tokens, cache_read, cache_write).
    """
    accumulated = ""
    total_in = total_out = total_cr = total_cw = 0
    continuations = 0

    while True:
        turn_num = sum(1 for m in messages if m["role"] == "user")
        chars = 0
        with client.messages.stream(
            model=MODEL, max_tokens=max_tokens, temperature=0, messages=messages,
        ) as stream:
            for text in stream.text_stream:
                if _STOP.is_set() or _STOP_FILE.exists():
                    _STOP.set()
                    break
                chars += len(text)
                print(f"\r  [{label}] Turn {turn_num} — {chars:,} chars...", end="", flush=True)
            print()
            if _STOP.is_set():
                break
            message = stream.get_final_message()

        total_in  += message.usage.input_tokens
        total_out += message.usage.output_tokens
        total_cr  += getattr(message.usage, "cache_read_input_tokens", 0) or 0
        total_cw  += getattr(message.usage, "cache_creation_input_tokens", 0) or 0

        chunk = message.content[0].text if message.content else ""
        accumulated += chunk

        if message.stop_reason != "max_tokens":
            break

        continuations += 1
        if continuations > MAX_CONTINUATIONS:
            print(f"  [{label}] Hit continuation cap ({MAX_CONTINUATIONS}), stopping early.", file=sys.stderr)
            break

        # API rejects continuation if the assistant turn is whitespace-only
        clean_chunk = re.sub(r"[\x00-\x1f]", " ", chunk).strip()
        if not clean_chunk:
            print(f"  [{label}] Empty chunk, cannot continue.", file=sys.stderr)
            break

        messages.append({"role": "assistant", "content": clean_chunk})
        tail = accumulated[-120:].replace('"', '\\"')
        messages.append({"role": "user", "content":
            f'The output was cut off. Continue from exactly where it stopped. '
            f'The last characters output were: "...{tail}". '
            f'Do NOT restart. Do NOT repeat any output. Continue from that exact point.'})

    return accumulated.strip(), total_in, total_out, total_cr, total_cw


def extract_text_from_image(img: Image.Image, debug_name: str = "image") -> dict:
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_PX:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    print(f"[{debug_name}] Image size: {img.size[0]}×{img.size[1]}px  JPEG: {len(buf.getvalue())//1024}KB", file=sys.stderr)

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

    text, total_in, total_out, total_cr, total_cw = _stream_response(
        client, messages, label=debug_name, max_tokens=12000
    )

    print(
        f"[{debug_name}] Tokens — input: {total_in}, output: {total_out}, "
        f"total: {total_in + total_out} "
        f"(cache write: {total_cw}, read: {total_cr})",
        file=sys.stderr,
    )

    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    result = _parse_sections(text)
    if result.get("template"):
        return result

    raw_path = debug_name + ".raw_response.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Parse failed in {debug_name} — raw response saved to {raw_path}", file=sys.stderr)
    return {"template": None, "html": "", "data": []}


def extract_all(paths: list[str]) -> dict:
    tasks = []

    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            print(f"Error: path {path_str} does not exist", file=sys.stderr)
            continue

        # Extract the original filename from the temp filename if matching the pattern
        parts = p.name.split("_")
        if len(parts) >= 5 and parts[0] == "mirror":
            orig_name = "_".join(parts[4:])
        else:
            orig_name = p.name

        if p.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(p)
                for page_idx in range(len(doc)):
                    page = doc.load_page(page_idx)
                    pix = page.get_pixmap(dpi=150)
                    img_data = pix.tobytes("jpeg")
                    img = Image.open(io.BytesIO(img_data))
                    tasks.append((img, f"{orig_name} (page {page_idx + 1})"))
            except Exception as e:
                print(f"Error reading PDF {path_str}: {e}", file=sys.stderr)
                raise
        else:
            try:
                img = Image.open(p)
                tasks.append((img, orig_name))
            except Exception as e:
                print(f"Error reading image {path_str}: {e}", file=sys.stderr)
                raise

    if not tasks:
        raise ValueError("No valid images or PDF pages found to process.")

    pages_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(extract_text_from_image, task[0], task[1]) for task in tasks]
        try:
            for idx, f in enumerate(futures):
                res_dict = f.result()
                raw_title = tasks[idx][1]
                match = re.match(r"^(.*)\.([a-zA-Z0-9]+)\s*(\(page \d+\))?$", raw_title)
                if match:
                    title = f"{match.group(1)}{match.group(3) or ''}"
                else:
                    title = raw_title
                res_dict["filename"] = title
                if res_dict.get("html") and res_dict.get("data"):
                    try:
                        from HTMLgen import populate_html_with_data
                        res_dict["html"] = populate_html_with_data(res_dict["html"], res_dict["data"])
                    except Exception as pe:
                        print(f"Failed to populate HTML for {title}: {pe}", file=sys.stderr)
                pages_data.append(res_dict)
        except KeyboardInterrupt:
            _STOP.set()
            for fut in futures:
                fut.cancel()
            raise

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

    _STOP_FILE.unlink(missing_ok=True)  # clear any leftover stop file
    t0 = time.time()
    try:
        data = extract_all(input_paths)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    finally:
        _STOP_FILE.unlink(missing_ok=True)
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
