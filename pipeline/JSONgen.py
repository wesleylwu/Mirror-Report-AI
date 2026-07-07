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

PROMPT = """Analyze this document image and output THREE sections. No explanation, no markdown fences.

---CODE---
Write a Python function build_template(ws) using openpyxl to recreate this form as a blank Excel template.
Include all imports (Font, Alignment, Border, Side, PatternFill, get_column_letter, etc.).
- Transcribe ONLY pre-printed labels. Read every character exactly — ン vs ソ, サ vs セ, 両 vs 吋.
- Count every column including narrow spacer columns. Count only rows within the outer border.
- Only assign fills to cells with a clearly visible background color. White/plain cells get NO fill.
- Order: (1) ws.title, column widths, row heights — (2) apply thin Border to every cell in one loop — (3) set values/fills/fonts/alignment — (4) ws.merge_cells() LAST.
- Set ws.page_setup.paperSize=9, fitToPage=True, fitToWidth=1, fitToHeight=1, orientation, ws.page_margins (0.5 all sides).

---HTML---
<table> representing the blank form template. Inline styles only. No <html>/<body> wrapper.
- colspan=N for merged cells, border:1px solid #000 on bordered cells, background:#RRGGBB for shaded cells.
- Approximate column widths with <col style="width:Npx">, row heights with <tr style="height:Npx">.
- Pre-printed labels only — no filled-in data.

---DATA---
JSON array of filled-in values (handwritten, typed, stamped — NOT pre-printed labels):
[{"r":<row>,"c":<col>,"v":"<value>"},...]
Omit empty cells."""

MAX_IMAGE_PX = 2800


def _try_json(s: str):
    s = s.strip()
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
    """Split ---CODE--- / ---HTML--- / ---DATA--- sections from a combined response."""
    m_code = re.search(r'---CODE---\s*', raw)
    m_html = re.search(r'---HTML---\s*', raw)
    m_data = re.search(r'---DATA---\s*', raw)

    markers = sorted(
        [(m, name) for m, name in [(m_code, 'code'), (m_html, 'html'), (m_data, 'data')] if m],
        key=lambda x: x[0].start(),
    )

    sections: dict[str, str] = {}
    for i, (m, name) in enumerate(markers):
        end = markers[i + 1][0].start() if i + 1 < len(markers) else len(raw)
        sections[name] = re.sub(r'```[a-z]*\n?|```', '', raw[m.end():end]).strip()

    code = sections.get('code', '')
    html = sections.get('html', '')
    data_text = sections.get('data', '')

    data = _try_json(data_text) if data_text else []
    if not isinstance(data, list):
        data = []

    return {"code": code, "html": html, "data": data}


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

        chunk = message.content[0].text
        accumulated += chunk

        if message.stop_reason != "max_tokens":
            break

        continuations += 1
        if continuations > MAX_CONTINUATIONS:
            print(f"  [{label}] Hit continuation cap ({MAX_CONTINUATIONS}), stopping early.", file=sys.stderr)
            break

        messages.append({"role": "assistant", "content": chunk})
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
        client, messages, label=debug_name, max_tokens=16000
    )

    print(
        f"[{debug_name}] Tokens — input: {total_in}, output: {total_out}, "
        f"total: {total_in + total_out} "
        f"(cache write: {total_cw}, read: {total_cr})",
        file=sys.stderr,
    )

    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    result = _parse_sections(text)
    if result.get("code"):
        return result

    raw_path = debug_name + ".raw_response.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Parse failed in {debug_name} — raw response saved to {raw_path}", file=sys.stderr)
    return {"code": "", "html": "", "data": []}


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
