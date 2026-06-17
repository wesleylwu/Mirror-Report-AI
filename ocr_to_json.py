"""Extract a table from an image via OCR and emit it as JSON rows.

Usage:
    python ocr_to_json.py <image_path> [output.json]

If no output path is given, JSON is printed to stdout.
"""
import json
import sys

import pytesseract
from PIL import Image


def extract_table(image_path: str) -> list[dict[str, str]]:
    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    words = [
        {"text": data["text"][i].strip(), "left": data["left"][i], "top": data["top"][i]}
        for i in range(len(data["text"]))
        if data["text"][i].strip()
    ]
    if not words:
        return []

    words.sort(key=lambda w: w["top"])
    row_height = sum(image.size) // 200 or 10  # rough tolerance for row grouping

    rows: list[list[dict]] = []
    for word in words:
        placed = False
        for row in rows:
            if abs(row[0]["top"] - word["top"]) <= row_height:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])

    for row in rows:
        row.sort(key=lambda w: w["left"])

    header = [w["text"] for w in rows[0]]
    records = []
    for row in rows[1:]:
        values = [w["text"] for w in row]
        record = {header[i] if i < len(header) else f"col_{i}": v for i, v in enumerate(values)}
        records.append(record)
    return records


def main():
    if len(sys.argv) < 2:
        print("Usage: python ocr_to_json.py <image_path> [output.json]", file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    records = extract_table(image_path)
    output = json.dumps(records, indent=2, ensure_ascii=False)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
