# -*- coding: utf-8 -*-
"""为市场动画生成简单的键盘网格预览图（原型用）。"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROWS = (
    list(range(14, 28)),
    list(range(28, 42)),
    list(range(42, 55)),
    list(range(55, 67)),
    list(range(67, 79)),
)


def make_preview(frames_path, out_path):
    data = json.load(open(frames_path, encoding="utf-8"))
    frames = data.get("frames") or []
    frame = frames[len(frames) // 2] if frames else {}
    cell_w, cell_h, gap = 27, 22, 3
    left, top = 12, 12
    width = left * 2 + 14 * cell_w + 13 * gap
    height = top * 2 + 5 * cell_h + 4 * gap
    img = Image.new("RGB", (width, height), (10, 14, 28))
    draw = ImageDraw.Draw(img)
    for r, row in enumerate(ROWS):
        for c, key in enumerate(row):
            x = left + c * (cell_w + gap)
            y = top + r * (cell_h + gap)
            color = frame.get(str(key)) or (26, 32, 48)
            draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=4,
                                   fill=tuple(color))
            draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=4,
                                   outline=(55, 70, 105), width=1)
    img.save(out_path, "PNG")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pairs = [
        ("animations/love-001/frames.json", "previews/love-001.png"),
        ("animations/heart-001/frames.json", "previews/heart-001.png"),
    ]
    for src, dst in pairs:
        make_preview(os.path.join(root, src), os.path.join(root, dst))
        print("wrote", dst)


if __name__ == "__main__":
    main()
