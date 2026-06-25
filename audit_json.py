import json
import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("output/IMG_9691.json", encoding="utf-8") as f:
    data = json.load(f)

rows = data["table"]["rows"]
col_widths_keys = set(data["table"]["column_widths"].keys())

print(f"Total rows: {len(rows)}")
print()

all_keys = set()
for r in rows:
    for k in r:
        if not k.startswith("_"):
            all_keys.add(k)

print("All data keys (EXTRA = not in column_widths):")
for k in sorted(all_keys):
    marker = "  <-- EXTRA" if k not in col_widths_keys else ""
    print(f"  {k}{marker}")

print()
from collections import Counter
c = Counter(r.get("_style", "data") for r in rows)
print("Row styles:", dict(c))

print()
print("Rows with _bg set:")
for i, r in enumerate(rows):
    if r.get("_bg"):
        mo = r.get("月", {})
        mo_text = mo.get("text", "") if isinstance(mo, dict) else mo
        print(f"  row {i}: _bg={r['_bg']} style={r.get('_style')} month={mo_text}")

print()
print("Rows where any cell has bg=D9D9D9:")
for i, r in enumerate(rows):
    for k, v in r.items():
        if isinstance(v, dict) and v.get("bg") == "D9D9D9":
            mo = r.get("月", {})
            mo_text = mo.get("text", "") if isinstance(mo, dict) else mo
            print(f"  row {i} col={k} month={mo_text}")
            break
