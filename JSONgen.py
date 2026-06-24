"""Extract tables from an image using Claude and emit structured JSON.

Usage:
    python JSONgen.py <image_path> [output.json]

Requires the ANTHROPIC_API_KEY environment variable to be set.
If no output path is given, JSON is printed to stdout.
"""
import base64
import json
import mimetypes
import sys
from pathlib import Path

import anthropic

from XLSXgen import json_to_xlsx

MODEL = "claude-sonnet-4-6"

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
        "label_bg": "<hex color of the label cell background, e.g. D9D9D9, or null>",
        "value_bg": "<hex color of the value cell background, or null>",
        "font_size": <relative font size: 1=small, 2=normal, 3=large>,
        "bold": <true|false>,
        "align": "<left|center|right>",
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
        "_bg": "<optional hex background color for this entire row>",
        "<column header>": {
          "text": "<cell text content, empty string if blank>",
          "align": "<left|center|right — horizontal text alignment>",
          "valign": "<top|middle|bottom — vertical alignment>",
          "bold": <true|false>,
          "font_size": <1=small, 2=normal, 3=large>,
          "bg": "<hex fill color or null>",
          "text_color": "<hex font color or null>",
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
- Capture background colors, font sizes, and alignment as they appear in the image.
- If no header section exists, return [].

TABLE SECTION:
- "column_widths": measure each column's width in characters proportional to how wide it appears visually. A column twice as wide as another should have roughly twice the number.
- "blank_rows": ONLY genuinely empty pre-printed rows (for hand-filling). Do NOT include total/summary rows here.
- Every row in "rows" must use the full cell object format with "text", "align", "valign", "bold", "font_size", "bg", "text_color", "wrap".
- "_style" values:
    - "data": normal data row
    - "total": total/subtotal/summary row
    - "subheader": a section heading row within the table
    - "full_width": a row merged across ALL columns — put its text in "_value", omit column keys
- CRITICAL: Inspect the very last row(s) of the table carefully. Any row with text spanning multiple or all columns — even just 1–2 characters in a corner — must be captured as a "full_width" row. Never skip it or count it as blank_rows.
- For cells containing multiple lines or bullet points, use \\n between items and preserve bullet characters (•) at the start of each item.
- Blank cells must still appear as cell objects with text "".
- Abnormally tall or wide cells must be noted with the appropriate height/width fields.

Return ONLY the raw JSON object. No explanation, no markdown fences."""


def extract_table(image_path: str) -> dict:
    media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_data},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )

    usage = message.usage
    print(f"Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}, total: {usage.input_tokens + usage.output_tokens}", file=sys.stderr)

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def main():
    if len(sys.argv) < 2:
        print("Usage: python JSONgen.py <image_path> [output.json]", file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    data = extract_table(image_path)
    output = json.dumps(data, indent=2, ensure_ascii=False)

    if len(sys.argv) >= 3:
        json_path = sys.argv[2]
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(output)

        table = data.get("table", {})
        xlsx_path = str(Path(json_path).with_suffix(".xlsx"))
        json_to_xlsx(
            json_path,
            xlsx_path,
            column_widths=table.get("column_widths"),
            blank_rows=table.get("blank_rows", 0),
            header=data.get("header"),
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
