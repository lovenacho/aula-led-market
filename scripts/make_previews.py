# -*- coding: utf-8 -*-
"""为市场动画生成简单的键盘网格预览图（原型用）。"""
import glob
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
    # 固定 640×300 画布，键盘完整居中；卡片用 object-fit: contain，
    # 不再把两侧裁掉，所以所有键都能看到。
    cell_w, cell_h, gap = 30, 24, 4
    width, height = 640, 300
    grid_w = 14 * cell_w + 13 * gap
    grid_h = 5 * cell_h + 4 * gap
    left = (width - grid_w) // 2
    top = (height - grid_h) // 2
    img = Image.new("RGB", (width, height), (8, 12, 24))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([left - 18, top - 18, left + grid_w + 18, top + grid_h + 18],
                           radius=16, fill=(13, 18, 34), outline=(38, 48, 74), width=1)
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
    for manifest_path in sorted(
            glob.glob(os.path.join(root, "animations", "*", "manifest.json"))):
        data = json.load(open(manifest_path, encoding="utf-8"))
        src = os.path.join(root, data["frames"])
        dst = os.path.join(root, data["preview"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        make_preview(src, dst)
        print("wrote", os.path.relpath(dst, root))


if __name__ == "__main__":
    main()
