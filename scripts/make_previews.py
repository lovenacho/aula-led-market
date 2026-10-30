# -*- coding: utf-8 -*-
"""为市场动画生成按真实键盘布局绘制的预览图。"""
import glob
import json
import os

from PIL import Image, ImageDraw, ImageFont

CANVAS_W, CANVAS_H = 640, 320
UNIT = 34
KEY_H = 40
GAP = 5
TOP = 38


def load_font(size):
    for path in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def short_label(label):
    return {
        'Backspace': 'Bksp', 'Caps': 'Caps', 'Enter': 'Enter',
        'Shift': 'Shift', 'Ctrl': 'Ctrl', 'Alt': 'Alt',
        'Menu': 'Menu', 'Space': 'Space',
    }.get(label, label)


def make_preview(frames_path, out_path, rows):
    data = json.load(open(frames_path, encoding="utf-8"))
    frames = data.get("frames") or []
    frame = frames[len(frames) // 2] if frames else {}

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), (8, 12, 24))
    draw = ImageDraw.Draw(img)
    total_h = len(rows) * (KEY_H + GAP) - GAP
    grid_top = TOP + max(0, (CANVAS_H - TOP * 2 - total_h) // 2)
    draw.rounded_rectangle([18, grid_top - 16, CANVAS_W - 18, grid_top + total_h + 16],
                           radius=16, fill=(13, 18, 34), outline=(38, 48, 74), width=1)

    small = load_font(9)
    normal = load_font(11)
    for r, row in enumerate(rows):
        row_w = sum(UNIT * key["w"] for key in row) + GAP * (len(row) - 1)
        x = (CANVAS_W - row_w) / 2
        y = grid_top + r * (KEY_H + GAP)
        for key in row:
            w = UNIT * key["w"] - GAP
            color = frame.get(str(key["id"])) or (26, 32, 48)
            draw.rounded_rectangle([x, y, x + w, y + KEY_H], radius=5,
                                   fill=tuple(color), outline=(58, 72, 102), width=1)
            text = short_label(str(key["label"]))
            font = normal if len(text) <= 4 else small
            tw = draw.textlength(text, font=font)
            lum = (0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]) / 255
            draw.text((x + w / 2, y + KEY_H / 2), text,
                      fill=(10, 14, 22) if lum > 0.55 else (170, 184, 205),
                      font=font, anchor="mm")
            x += UNIT * key["w"] + GAP

    img.save(out_path, "PNG")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    keyboards = json.load(open(os.path.join(root, "schema", "keyboards.json"),
                               encoding="utf-8"))
    for manifest_path in sorted(
            glob.glob(os.path.join(root, "animations", "*", "manifest.json"))):
        data = json.load(open(manifest_path, encoding="utf-8"))
        models = data.get("models") or []
        layout_name = "win68he" if any("68" in str(m) for m in models) else "win60he"
        rows = keyboards.get(layout_name) or keyboards["win60he"]
        src = os.path.join(root, data["frames"])
        dst = os.path.join(root, data["preview"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        make_preview(src, dst, rows)
        print("wrote", os.path.relpath(dst, root), "layout=", layout_name)


if __name__ == "__main__":
    main()
