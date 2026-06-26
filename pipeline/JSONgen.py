"""Extract text content from a document image using Claude.

Outputs a flat JSON with title, section_header, header key/value pairs,
and table rows. Layout is handled entirely by XLSXgen via templates.

Usage:
    python JSONgen.py <image_path> [output.json]

Requires the ANTHROPIC_API_KEY environment variable to be set.
"""
import base64
import io
import json
import sys
from pathlib import Path

import anthropic
import cv2
import numpy as np
from PIL import Image, ImageOps

MODEL = "claude-haiku-4-5-20251001"

PROMPT = """You are a precise document digitizer. Extract ONLY the text visible in the image. Do not infer, guess, or fill in values.

CRITICAL RULES:
- Transcribe ONLY pre-printed text. Ignore handwriting, stamps, and pen marks.
- If a field value is blank, output "".
- Read every character directly from the image.

Return a single JSON object with this exact schema:

{
  "title": "<full-width title text at the very top of the document, e.g. 製造指図書>",
  "section_header": "<full-width section title between the header fields and the data table, e.g. 調合票. Empty string if none.>",
  "header": {
    "<label text exactly as printed>": "<value text, or empty string if blank>",
    ...
  },
  "table": {
    "columns": ["<column header 1>", "<column header 2>", ...],
    "rows": [
      {
        "<column header>": "<cell text, or empty string if blank>",
        ...
      }
    ]
  }
}

RULES:

TITLE: The full-width text spanning the top of the document (e.g. 製造指図書). Do not include it in header.

HEADER FIELDS: Every label/value pair in the metadata section above the data table.
- Use the EXACT printed label text as the key (e.g. "手配No.", "発行日", "品目CD").
- If a field has no value printed, still include it with value "".
- Do NOT include the title or section header in this dict.

SECTION HEADER: A full-width label separating the header fields from the data table (e.g. 調合票). Empty string if none.

TABLE COLUMNS: Column header strings in left-to-right order.

TABLE ROWS: Each data row as an object keyed by column header.
- Do NOT emit a row whose values are just the column header names.
- Blank cells: "".
- The last row(s) of the table may be a full-width text row spanning all columns — output it as a special entry: {"_full_width": "<text>"}.
Return ONLY the raw JSON object. No explanation, no markdown fences."""

MAX_IMAGE_PX = 1568


def _deskew(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    gray = cv2.bitwise_not(gray)
    contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    quad = None
    h, w = cv.shape[:2]
    min_area = w * h * 0.10
    for cnt in contours[:5]:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(cnt) > min_area:
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        return img
    s = quad.sum(axis=1)
    diff = np.diff(quad, axis=1)
    ordered = np.array([
        quad[np.argmin(s)], quad[np.argmin(diff)],
        quad[np.argmax(s)], quad[np.argmax(diff)],
    ], dtype=np.float32)
    w_top  = np.linalg.norm(ordered[1] - ordered[0])
    w_bot  = np.linalg.norm(ordered[2] - ordered[3])
    h_left = np.linalg.norm(ordered[3] - ordered[0])
    h_right= np.linalg.norm(ordered[2] - ordered[1])
    out_w, out_h = int(max(w_top, w_bot)), int(max(h_left, h_right))
    dst = np.array([[0,0],[out_w,0],[out_w,out_h],[0,out_h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(cv, M, (out_w, out_h))
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    _, paper_mask = cv2.threshold(warped_gray, 200, 255, cv2.THRESH_BINARY)
    paper_coords = cv2.findNonZero(paper_mask)
    if paper_coords is not None:
        x, y, bw, bh = cv2.boundingRect(paper_coords)
        pad = 10
        warped = warped[max(0,y-pad):min(out_h,y+bh+pad),
                        max(0,x-pad):min(out_w,x+bw+pad)]
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))


def extract_text(image_path: str) -> dict:
    img = Image.open(image_path)
    img = _deskew(img)
    img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_PX:
        img.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

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

    accumulated = ""
    total_input = total_output = total_cache_read = total_cache_write = 0

    while True:
        turn = len([m for m in messages if m["role"] == "user"])
        chars = 0
        with client.messages.stream(
            model=MODEL, max_tokens=8192, temperature=0, messages=messages,
        ) as stream:
            for text in stream.text_stream:
                chars += len(text)
                print(f"\r  Turn {turn} — {chars:,} chars...", end="", flush=True)
            print()
            message = stream.get_final_message()

        total_input  += message.usage.input_tokens
        total_output += message.usage.output_tokens
        total_cache_read  += getattr(message.usage, "cache_read_input_tokens", 0) or 0
        total_cache_write += getattr(message.usage, "cache_creation_input_tokens", 0) or 0

        chunk = message.content[0].text
        accumulated += chunk
        if message.stop_reason != "max_tokens":
            break
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content": "Continue the JSON exactly from where you left off. Output only raw JSON continuation."})

    print(
        f"Tokens — input: {total_input}, output: {total_output}, "
        f"total: {total_input + total_output} "
        f"(cache write: {total_cache_write}, read: {total_cache_read})",
        file=sys.stderr,
    )

    text = accumulated.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

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
    args = parser.parse_args()

    data = extract_text(args.image_path)
    output = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output_json}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
