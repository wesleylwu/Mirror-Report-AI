"""Convert a JSON array of objects into a new Excel spreadsheet.

Usage:
    python json_to_xlsx.py <input.json> [output.xlsx]

If no output path is given, the spreadsheet is written next to the
input file with the same name and a .xlsx extension.
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook


def json_to_xlsx(json_path: str, xlsx_path: str) -> None:
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    headers = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for record in records:
        ws.append([record.get(header, "") for header in headers])

    wb.save(xlsx_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python json_to_xlsx.py <input.json> [output.xlsx]", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    xlsx_path = sys.argv[2] if len(sys.argv) >= 3 else str(Path(json_path).with_suffix(".xlsx"))
    json_to_xlsx(json_path, xlsx_path)


if __name__ == "__main__":
    main()
