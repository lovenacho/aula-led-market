# -*- coding: utf-8 -*-
"""校验市场动画清单和帧数据（不执行动画代码）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("id", "name", "author", "version", "license",
            "layouts", "fps", "smooth", "preview", "frames")
MAX_FRAMES = 600
MAX_FRAMES_FILE = 8 * 1024 * 1024


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    errors = []
    seen = set()
    for manifest_path in sorted((ROOT / "animations").glob("*/manifest.json")):
        name = manifest_path.parent.name
        try:
            data = json.load(open(manifest_path, encoding="utf-8"))
        except Exception as exc:
            errors.append("%s: manifest 读取失败: %s" % (name, exc))
            continue
        for key in REQUIRED:
            if key not in data:
                errors.append("%s: 缺少字段 %s" % (name, key))
        if errors and any(e.startswith(name + ":") for e in errors):
            continue
        if data["id"] in seen:
            errors.append("%s: id 重复 %s" % (name, data["id"]))
        seen.add(data["id"])
        if not isinstance(data.get("layouts"), list) or not data["layouts"]:
            errors.append("%s: layouts 必须是非空数组" % name)
        fps = data.get("fps")
        if not isinstance(fps, (int, float)) or not (1 <= fps <= 60):
            errors.append("%s: fps 必须在 1..60" % name)
        if not isinstance(data.get("smooth"), bool):
            errors.append("%s: smooth 必须是布尔值" % name)

        for key in ("preview", "frames"):
            rel = data.get(key)
            if not isinstance(rel, str) or not rel:
                errors.append("%s: %s 路径为空" % (name, key))
                continue
            path = ROOT / rel
            if not is_under(path, ROOT):
                errors.append("%s: %s 越界" % (name, key))
            elif not path.is_file():
                errors.append("%s: 找不到 %s" % (name, path))
        if errors and any(e.startswith(name + ":") for e in errors):
            continue

        frames_path = ROOT / data["frames"]
        if frames_path.stat().st_size > MAX_FRAMES_FILE:
            errors.append("%s: frames 文件超过 %d MB" % (name, MAX_FRAMES_FILE // 1024 // 1024))
            continue
        try:
            frame_data = json.load(open(frames_path, encoding="utf-8"))
        except Exception as exc:
            errors.append("%s: frames 读取失败: %s" % (name, exc))
            continue
        frames = frame_data.get("frames")
        if not isinstance(frames, list) or not frames:
            errors.append("%s: frames 必须是非空数组" % name)
            continue
        if len(frames) > MAX_FRAMES:
            errors.append("%s: 帧数 %d 超过上限 %d" % (name, len(frames), MAX_FRAMES))
            continue
        for i, frame in enumerate(frames):
            if not isinstance(frame, dict):
                errors.append("%s: 第 %d 帧不是对象" % (name, i))
                break
            for key, rgb in frame.items():
                try:
                    int(key)
                except Exception:
                    errors.append("%s: 第 %d 帧键号 %r 非法" % (name, i, key))
                    break
                if (not isinstance(rgb, (list, tuple)) or len(rgb) != 3
                        or any(not isinstance(v, int) or not (0 <= v <= 255) for v in rgb)):
                    errors.append("%s: 第 %d 帧键 %s 颜色非法" % (name, i, key))
                    break

    if errors:
        print("校验失败：")
        for error in errors:
            print("  -", error)
        return 1
    print("校验通过：%d 个动画" % len(seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
