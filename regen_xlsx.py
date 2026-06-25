import json
from XLSXgen import json_to_xlsx

with open("output/IMG_9691.json", encoding="utf-8") as f:
    data = json.load(f)

table = data.get("table", {})
base_row_height = {1: 15, 2: 30, 3: 45}.get(table.get("row_height", 1), 15)
json_to_xlsx(
    "output/IMG_9691.json",
    "output/IMG_9691.xlsx",
    column_widths=table.get("column_widths"),
    blank_rows=table.get("blank_rows", 0),
    header=data.get("header"),
    row_height=base_row_height,
)
print("Done: output/IMG_9691.xlsx")
