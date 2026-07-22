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
import os
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
import pymssql
_STOP_FILE = Path(__file__).parent / "STOP"

MODEL_HAIKU   = os.environ.get("MODEL_HAIKU",   "claude-haiku-4-5-20251001")
MODEL_SONNET  = os.environ.get("MODEL_SONNET",  "claude-sonnet-4-6")
MODEL_SONNET5 = os.environ.get("MODEL_SONNET5", "claude-sonnet-5")
MODEL_OPUS    = os.environ.get("MODEL_OPUS",    "claude-opus-4-6")
MODEL_FABLE   = os.environ.get("MODEL_FABLE",   "claude-fable-5")
MODEL = MODEL_OPUS  # default; overridden by flags at runtime

def get_db_schemas():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "51399")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    database = os.environ.get("DB_NAME")

    if not all([host, user, password, database]):
        print("[Schema Discovery] Database config missing in env.", file=sys.stderr)
        return {}

    try:
        conn = pymssql.connect(
            server=host,
            port=int(port),
            user=user,
            password=password,
            database=database
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME IN (
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                AND TABLE_NAME NOT LIKE '%ログ'
                AND TABLE_NAME NOT LIKE '%ワーク'
                AND TABLE_NAME NOT LIKE '%履歴'
                AND TABLE_NAME NOT LIKE '%変換'
                AND TABLE_NAME NOT LIKE 'WK_%'
                AND TABLE_NAME NOT LIKE 'TAX%'
            )
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        schemas = {}
        for tname, cname in rows:
            if tname not in schemas:
                schemas[tname] = []
            schemas[tname].append(cname)
        print(f"[Schema Discovery] Successfully loaded {len(schemas)} table schemas from SQL Server.", file=sys.stderr)
        return schemas
    except Exception as e:
        print(f"[Schema Discovery] Failed to load schemas: {e}", file=sys.stderr)
        return {}

def format_schemas(schemas):
    lines = []
    for tname, cols in schemas.items():
        cols_str = ", ".join(cols)
        lines.append(f"- Table name: \"{tname}\"\n  Columns: {cols_str}")
    return "\n\n".join(lines)

BASE_PROMPT = """Analyze this document image and output exactly three sections. Begin each section with its marker on its own line exactly as shown. No explanation before the first marker. No markdown fences.

---TEMPLATE---
JSON object describing the blank form structure. Pre-printed labels and structure only — no filled-in values.
Read every character exactly — ン vs ソ, サ vs セ, 両 vs 吋.
{{"sheet_name":"<name>","orientation":"portrait|landscape","col_widths":[<float>,...],"data_rows":<count of repeating data rows in original>,"rows":[{{"h":<height>,"cells":[{{"c":<col>,"s":<colspan>,"rs":<rowspan>,"v":"<label>","b":<bold>,"a":"left|center|right","x":<border>,"f":"<RRGGBB>"}}]}}]}}
Rules:
- Before writing anything, count the columns by tracing each vertical line from top to bottom. Write the count in col_widths — one entry per column, no more, no less.
- col_widths in Excel character units: narrow=4-6, standard=8-12, wide=15-25. Never use pixel values.
- Do NOT pad "v" values with spaces. Cell width is set by col_widths only.
- Include narrow spacer columns. Count only rows within the outer border.
- Count the exact number of repeating data rows visible in the image and set "data_rows" to that count.
- In "rows": include ALL rows — headers, labels, AND all blank data rows in their correct positions.
- Blank data rows MUST have "v":"" (empty string) on every cell — NEVER put handwritten, typed, or stamped values in the template. Those go in DATA only.
- For runs of identical blank data rows (same height, same column pattern, no labels), use the compact form: {{"h":<height>,"repeat":<count>,"cells":[...one row's cells...]}} instead of repeating each row individually. This saves tokens.
- "x": REQUIRED on every cell with any visible border. true/"tlbr" = all sides, "b" = bottom only, "tb" = top+bottom, "lr" = left+right. Omit only for cells with zero visible borders.
- Every cell inside a ruled table, grid, or bordered box must have "x" set — including full-width title/section rows that span all columns. If the section is enclosed by any outer border at all, set "x": true.
- "f": hex only for visibly shaded cells, omit for white.

---HTML---
<table> of the blank form structure. Inline styles only. No <html>/<body> wrapper.
colspan/rowspan for merges, border:1px solid #000 for borders, background:#RRGGBB for shading.
<col style="width:Npx"> for widths, <tr style="height:Npx"> for heights. Pre-printed labels only.

---MAPPING---
Identify which database table matches this document type and map the document cells to the exact database column names of that matched table.
We dynamically scanned the database and found the following tables and columns:
{schemas_str}

Identify the best matching table and map ONLY the relevant columns to their 0-based coordinates in the TEMPLATE.
- IMPORTANT: You MUST ONLY map to the EXACT column names listed in the database schema for the matched table. Do NOT hallucinate or use column names from the document if they do not exist in the schema. For example, if the document says "売上金額" but the schema column is "金額" or "amount", you MUST use the schema's exact column name ("金額" or "amount").
- Functional Semantic Matching: Document field labels often use localized logistics terms, abbreviations, or packaging jargon that differ from database column names. Map document fields to database columns based on their functional business role rather than requiring exact string similarity:
  • Physical packaging or container style labels (e.g. 荷姿, 包装, 梱包) should be mapped to the closest functional unit/packaging category column available in the database schema (e.g. 単位, 単位名, 単位区分).
  • Prefix/suffix variations (e.g. 売上数量 vs. 数量, 伝票番号 vs. 伝票No) should map to the core functional attribute in the schema.
  • Event/transaction dates (e.g. 取引日, 納品日) should map to the corresponding posting/system date column (e.g. 計上日, 処理日).
- Do not output any columns that are not present in the matched table's schema.

If a column appears as a single field, map it to its cell coordinates: {{"r": <row>, "c": <col>}}.
If it appears as a table column, map it to its column index "c" AND a list of row indices "rows" where repeating data lines reside: {{"c": <col>, "rows": [<row1>, <row2>, ...]}}

Output format MUST be a single JSON object with two fields:
{{
  "matched_table": "<exact_database_table_name>",
  "fields": {{
    "<column_name_1>": {{"r": <row>, "c": <col>}},
    "<column_name_2>": {{"c": <col>, "rows": [<row1>, <row2>, ...]}}
  }}
}}
"""

MAX_IMAGE_PX = 2800


def _try_json(s: str):
    s = s.strip()
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
    def _last(pattern):
        matches = list(re.finditer(pattern, raw))
        return matches[-1] if matches else None

    m_tmpl = _last(r'---TEMPLATE---\s*')
    m_html = _last(r'---HTML---\s*')
    m_data = _last(r'---MAPPING---\s*')

    markers = sorted(
        [(m, name) for m, name in [(m_tmpl, 'template'), (m_html, 'html'), (m_data, 'mapping')] if m],
        key=lambda x: x[0].start(),
    )

    sections: dict[str, str] = {}
    for i, (m, name) in enumerate(markers):
        end = markers[i + 1][0].start() if i + 1 < len(markers) else len(raw)
        sections[name] = re.sub(r'```[a-z]*\n?|```', '', raw[m.end():end]).strip()

    template_text = sections.get('template', '')
    html = sections.get('html', '')
    data_text = sections.get('mapping', '')

    if not template_text and not sections:
        html_start = m_html.start() if m_html else len(raw)
        candidate = re.sub(r'```[a-z]*\n?|```', '', raw[:html_start]).strip()
        first_brace = candidate.find('{')
        if first_brace != -1:
            template_text = candidate[first_brace:]

    template = _try_json(template_text) if template_text else None
    data = _try_json(data_text) if data_text else {}

    return {"template": template, "html": html, "mapping": data}


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
        _thinking_models = {MODEL_SONNET5, MODEL_OPUS, MODEL_FABLE}
        _is_thinking = MODEL in _thinking_models
        _budget = max_tokens * 3 if _is_thinking else max_tokens
        _extra = {} if _is_thinking else {"temperature": 0}
        thinking_chars = 0
        with client.messages.stream(
            model=MODEL, max_tokens=_budget, messages=messages, **_extra,
        ) as stream:
            for event in stream:
                if _STOP.is_set() or _STOP_FILE.exists():
                    _STOP.set()
                    break
                event_type = type(event).__name__
                if event_type == "RawContentBlockDeltaEvent":
                    delta = getattr(event, "delta", None)
                    if delta is None:
                        pass
                    elif getattr(delta, "type", None) == "thinking_delta":
                        thinking_chars += len(getattr(delta, "thinking", "") or "")
                        print(f"\r  [{label}] Turn {turn_num} — thinking ({thinking_chars:,} chars)...", end="", flush=True)
                    elif getattr(delta, "type", None) == "text_delta":
                        chars += len(getattr(delta, "text", "") or "")
                        print(f"\r  [{label}] Turn {turn_num} — {chars:,} chars...", end="", flush=True)
            print()
            if _STOP.is_set():
                break
            message = stream.get_final_message()

        total_in  += message.usage.input_tokens
        total_out += message.usage.output_tokens
        total_cr  += getattr(message.usage, "cache_read_input_tokens", 0) or 0
        total_cw  += getattr(message.usage, "cache_creation_input_tokens", 0) or 0

        chunk = next((b.text for b in message.content if hasattr(b, "text")), "")
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

    schemas = get_db_schemas()
    schemas_str = format_schemas(schemas)
    prompt = BASE_PROMPT.format(schemas_str=schemas_str)

    client = anthropic.Anthropic()
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
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
        if result.get("html"):
            try:
                from HTMLgen import populate_html_with_data
                result["html"] = populate_html_with_data(result["html"], result.get("data") or [])
            except Exception as pe:
                print(f"Failed to populate HTML in OCR: {pe}", file=sys.stderr)
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
                    pix = page.get_pixmap(dpi=200)
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
                if res_dict.get("html"):
                    try:
                        from HTMLgen import populate_html_with_data
                        res_dict["html"] = populate_html_with_data(res_dict["html"], res_dict.get("data") or [])
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
    parser.add_argument("--sonnet5", action="store_true", help="Use claude-sonnet-5")
    parser.add_argument("--opus", action="store_true", help="Use claude-opus-4-6")
    parser.add_argument("--fable", action="store_true", help="Use claude-fable-5")
    args = parser.parse_args()

    global MODEL
    if args.haiku:
        MODEL = MODEL_HAIKU
    elif args.sonnet5:
        MODEL = MODEL_SONNET5
    elif args.opus:
        MODEL = MODEL_OPUS
    elif args.fable:
        MODEL = MODEL_FABLE
    else:
        MODEL = MODEL_SONNET
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
