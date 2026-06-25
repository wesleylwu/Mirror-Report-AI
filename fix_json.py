import json

with open("IMG_9691.JPG.raw_response.txt", encoding="utf-8") as f:
    text = f.read()

# Fix the stray-quote bad key: 実績_売上"_売上比% -> 実績_売上比%
# The stray " sits between U+4E0A (上) and U+005F (_) before 売上比%
bad_key  = chr(0x5B9F)+chr(0x7E3E)+'_'+chr(0x58F2)+chr(0x4E0A)+chr(0x22)+'_'+chr(0x58F2)+chr(0x4E0A)+chr(0x6BD4)+'%":'
good_key = chr(0x5B9F)+chr(0x7E3E)+'_'+chr(0x58F2)+chr(0x4E0A)+chr(0x6BD4)+'%":'

fixed = text.replace(bad_key, good_key)
print(f"Bad-key fix made: {fixed != text}")

data = json.loads(fixed)

rows = data["table"]["rows"]
original_count = len(rows)

# Remove subheader rows whose cell texts duplicate the column header names
col_keys = set(data["table"]["column_widths"].keys())
# Build set of leaf names (part after last _)
leaf_names = {k.rsplit("_", 1)[-1] for k in col_keys} | col_keys

def is_dup_subheader(row):
    if row.get("_style") != "subheader":
        return False
    texts = set()
    for k, v in row.items():
        if k.startswith("_"):
            continue
        t = v.get("text", "") if isinstance(v, dict) else str(v)
        if t:
            texts.add(t)
    # If ALL non-empty texts are just column names or leaf names, it's a dup header
    return bool(texts) and all(
        t in col_keys or t in leaf_names or t.replace("\n", "_") in col_keys
        for t in texts
    )

data["table"]["rows"] = [r for r in rows if not is_dup_subheader(r)]
removed = original_count - len(data["table"]["rows"])
print(f"Removed {removed} duplicate subheader rows (was {original_count}, now {len(data['table']['rows'])})")

with open("output/IMG_9691.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Saved output/IMG_9691.json")
