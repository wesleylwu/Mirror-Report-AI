"""Extract tables from an image using Claude and emit structured JSON.

Usage:
    python JSONgen.py <image_path> [output.json]

Requires the ANTHROPIC_API_KEY environment variable to be set.
If no output path is given, JSON is printed to stdout.
"""
import base64
import io
import json
import mimetypes
import sys
from pathlib import Path

import anthropic
from PIL import Image

from XLSXgen import json_to_xlsx

MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"
MODEL = MODEL_SONNET  # default

PROMPT = """You are a precise document digitizer. Your job is to reproduce every table and form in this image as faithfully as possible in JSON so it can be rendered in Excel at near-identical visual fidelity.

Return a single JSON object with this schema:

{
  "header": [
    [
      {
        "label": "<field name text>",
        "value": "<field value, or empty string if blank>",
        "label_span": <int — number of grid columns the label cell occupies>,
        "value_span": <int — number of grid columns the value cell occupies>,
        "font_size": <relative font size: 1=small, 2=normal, 3=large>,
        "bold": <true|false>,
        "height": <relative row height: 1=normal, 2=tall, 3=very tall>
      }
    ]
  ],
  "table": {
    "column_widths": { "<column header>": <width in characters, proportional to image> },
    "row_height": <default row height multiplier: 1=normal, 2=tall>,
    "blank_rows": <int — count of empty pre-printed template rows only>,
    "rows": [
      {
        "_style": "<data|total|subheader|full_width>",
        "_value": "<only for full_width rows — the text spanning all columns>",
        "_height": <optional row height multiplier for this specific row>,
        "<column header>": {
          "text": "<cell text content, empty string if blank>",
          "bold": <true|false>,
          "font_size": <1=small, 2=normal, 3=large>,
          "wrap": <true|false — whether text wraps in the cell>
        }
      }
    ]
  }
}

RULES:

HEADER SECTION:
- Capture every field in the metadata/form area above or beside the main data table.
- Each row is a list of field cells. Label and value are SEPARATE cells.
- All rows must have the same total span (sum of label_span + value_span across all cells per row must be equal for every row).
- Include empty value boxes — if a field has no value, still include it with value "".
- "label_span" and "value_span" must reflect the actual visual width of each cell relative to others. Measure the PIXEL POSITION of every column boundary from the left edge of the form. Use those pixel positions to compute consistent spans so that cells appearing in the same visual column across different rows have the same cumulative span from the left. For example, if the second major column boundary falls at 40% of the total width, every row should have cumulative spans summing to 40% of max_total_span at that boundary.
- "height" must reflect the actual visual row height: 1=normal single-line row, 2=row that is roughly twice the normal height, 3=very tall row.
- If no header section exists, return [].

TABLE SECTION:
- "column_widths": measure each column's pixel width carefully and express it as character counts. A column that is visually twice as wide as another must have exactly twice the number. Measure from the image — do not guess. Note that Japanese/CJK characters display at roughly DOUBLE the width of ASCII characters, so a column containing Japanese text needs a larger number to display the full content. Typical values range from 8 to 60; columns with long Japanese text should be 30–60.
- "row_height": measure the typical data row height. Use 1 for normal single-line rows, 2 for rows that are visually taller.
- "blank_rows": ONLY genuinely empty pre-printed rows (for hand-filling). Do NOT include total/summary rows here.
- CRITICAL: Do NOT emit a row whose cell texts are just the column header names. The column headers are already encoded in the column_widths keys and will be rendered automatically — do not repeat them as a row inside "rows".
- CRITICAL: Do NOT collapse multiple source rows into a single cell. If the original table has separate rows for 建売, 土地, 仲介, etc., each must appear as its own separate JSON row. Never comma-separate or newline-separate items that occupy distinct rows in the source; instead emit one JSON row object per source row.
- Every row in "rows" must use the full cell object format with "text", "bold", "font_size", "wrap".
- "_style" values:
    - "data": normal data row
    - "total": total/subtotal/summary row
    - "subheader": a section heading row within the table
    - "full_width": a row merged across ALL columns — put its text in "_value", omit column keys
- CRITICAL: Inspect the very last row(s) of the table carefully. Any row with text spanning multiple or all columns — even just 1–2 characters in a corner — must be captured as a "full_width" row. Never skip it or count it as blank_rows.
- For cells containing multiple lines or bullet points, use \\n between items and preserve bullet characters (•) at the start of each item.
- Blank cells must still appear as cell objects with text "".
- Abnormally tall or wide cells must be noted with the appropriate height/width fields.

- HANDWRITING: Ignore any handwritten annotations, pen marks, stamps, or ink overlaid on the printed form. Only capture pre-printed text.

- ITEM CODE ALIGNMENT: When a cell contains an item code (e.g. "GE0006280", "HA0002610", "H00001630") followed by a descriptor on the same line (e.g. "999 購入", "100 仕込"), use ASCII spaces (U+0020) only — never ideographic spaces (U+3000). Pad every code in that column with spaces so all descriptors start at the same character position across every row: find the longest code in the column, then pad shorter codes with trailing spaces to that length before the descriptor.

- TITLE ROW HEIGHT: Any header row that is a single cell spanning the full width and contains only a document title (e.g. 製造指図書, 調合票) must use "height": 3.

Return ONLY the raw JSON object. No explanation, no markdown fences."""


MAX_IMAGE_PX = 1024

def extract_table(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > MAX_IMAGE_PX:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    media_type = "image/jpeg"

    client = anthropic.Anthropic()
    # Mark the image and prompt with cache_control so that on continuation turns
    # the API reads them from cache instead of re-processing the full image each
    # time.  Without this, every max_tokens continuation re-sends the image and
    # multiplies the token cost by the number of turns needed.
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": PROMPT, "cache_control": {"type": "ephemeral"}},
            ],
        }
    ]

    accumulated = ""
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0

    while True:
        turn = len([m for m in messages if m["role"] == "user"])
        chars = 0
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                chars += len(text)
                print(f"\r  Turn {turn} — {chars:,} chars generated...", end="", flush=True)
            print()
            message = stream.get_final_message()

        total_input += message.usage.input_tokens
        total_output += message.usage.output_tokens
        total_cache_read  += getattr(message.usage, "cache_read_input_tokens", 0) or 0
        total_cache_write += getattr(message.usage, "cache_creation_input_tokens", 0) or 0

        chunk = message.content[0].text
        accumulated += chunk

        if message.stop_reason != "max_tokens":
            break

        # Response was cut off — ask Claude to continue exactly where it left off.
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": "Continue the JSON exactly from where you left off. Output only raw JSON continuation — no explanation, no markdown, no repeated content."})

    print(f"Tokens — input: {total_input}, output: {total_output}, total: {total_input + total_output} "
          f"(cache write: {total_cache_write}, cache read: {total_cache_read})", file=sys.stderr)

    text = accumulated.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Repair unescaped double-quotes inside JSON object keys.
    # Claude occasionally embeds a literal " in a key name (e.g. from OCR of a
    # symbol in the source document), which breaks JSON parsing.  We scan for
    # the pattern  "...": and remove any unescaped " that appears inside a key.
    import re as _re
    def _repair_keys(s: str) -> str:
        # Replace  "...<bare-quote>...":  with the quote removed from the key.
        # Strategy: find every  "text":  token where text contains a bare quote
        # by looking for quote-before-colon patterns that have extra quotes inside.
        return _re.sub(
            r'"([^"\\\n]*)"([^"\\\n:,\}\]{\[\n]*)"(\s*:)',
            lambda m: '"' + m.group(1) + m.group(2) + '"' + m.group(3),
            s,
        )
    # Apply repeatedly until no more stray quotes remain.
    for _ in range(5):
        fixed = _repair_keys(text)
        if fixed == text:
            break
        text = fixed

    # Repair missing opening quote on cell object keys: {text": → {"text":
    # Claude occasionally drops the leading " when starting a cell object,
    # producing  {text": "…", align": …}  instead of  {"text": "…", "align": …}.
    # Pass 1: fix the first key after {
    text = _re.sub(r'\{([A-Za-z_　-鿿][^":\{\}\[\]\n]*)"(\s*:)', r'{"' + r'\1"\2', text)
    # Pass 2: fix subsequent keys that are also missing their opening quote
    # Pattern: , followed by word chars (no leading ") then ":
    text = _re.sub(r',(\s*)([A-Za-z_　-鿿][^":\{\}\[\]\n,]*)"(\s*:)', r',\1"\2"\3', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raw_path = image_path + ".raw_response.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"JSON parse error: {e}", file=sys.stderr)
        print(f"Raw response saved to: {raw_path}", file=sys.stderr)
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    parser.add_argument("output_json", nargs="?")
    parser.add_argument("--haiku", action="store_true", help="Use Haiku instead of Sonnet (faster, less accurate)")
    args = parser.parse_args()

    global MODEL
    if args.haiku:
        MODEL = MODEL_HAIKU
        print(f"Using model: {MODEL}", file=sys.stderr)

    image_path = args.image_path
    data = extract_table(image_path)
    output = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output_json:
        json_path = args.output_json
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(output)

        table = data.get("table", {})
        xlsx_path = str(Path(json_path).with_suffix(".xlsx"))
        base_row_height = {1: 15, 2: 30, 3: 45}.get(table.get("row_height", 1), 15)
        json_to_xlsx(
            json_path,
            xlsx_path,
            column_widths=table.get("column_widths"),
            blank_rows=table.get("blank_rows", 0),
            header=data.get("header"),
            row_height=base_row_height,
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
