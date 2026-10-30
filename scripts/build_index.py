# -*- coding: utf-8 -*-
"""扫描 animations/*/manifest.json 生成市场 index.json。"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "index.json"
FIELDS = ("id", "name", "author", "version", "license", "min_app",
          "description", "models", "layouts", "fps", "smooth", "tags")


def main() -> int:
    animations = []
    for manifest_path in sorted((ROOT / "animations").glob("*/manifest.json")):
        data = json.load(open(manifest_path, encoding="utf-8"))
        frames_path = ROOT / data["frames"]
        frames_data = json.load(open(frames_path, encoding="utf-8"))
        entry = {key: data.get(key) for key in FIELDS if key in data}
        entry["preview"] = data["preview"]
        entry["frames_url"] = data["frames"]
        entry["frames_count"] = len(frames_data.get("frames") or [])
        entry["size"] = frames_path.stat().st_size
        entry["sha256"] = hashlib.sha256(frames_path.read_bytes()).hexdigest()
        animations.append(entry)

    index = {
        "schema": 1,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "animations": sorted(animations, key=lambda item: item["id"]),
    }
    text = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old != text:
            print("index.json 需要重新生成")
            return 1
        print("index.json 已是最新")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print("已生成 index.json：%d 个动画" % len(animations))
    return 0


if __name__ == "__main__":
    sys.exit(main())
