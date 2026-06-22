"""Extract a table from an image using Claude and emit it as JSON rows.

Usage:
    python ocr_to_json.py <image_path> [output.json]

Requires the ANTHROPIC_API_KEY environment variable to be set.
If no output path is given, JSON is printed to stdout.
"""
import base64
import json
import mimetypes
import sys
from pathlib import Path

import anthropic

from json_to_xlsx import json_to_xlsx

MODEL = "claude-sonnet-4-6"

PROMPT = (
    "Read the table in this image and return ONLY a JSON array of objects, "
    "one per data row, using the table's column headers as keys. "
    "Do not include any explanation or markdown formatting, just the raw JSON array."
)


def extract_table(image_path: str) -> list[dict[str, str]]:
    media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
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

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def main():
    if len(sys.argv) < 2:
        print("Usage: python ocr_to_json.py <image_path> [output.json]", file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    records = extract_table(image_path)
    output = json.dumps(records, indent=2, ensure_ascii=False)

    if len(sys.argv) >= 3:
        json_path = sys.argv[2]
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(output)
        xlsx_path = str(Path(json_path).with_suffix(".xlsx"))
        json_to_xlsx(json_path, xlsx_path)
    else:
        print(output)


if __name__ == "__main__":
    main()
