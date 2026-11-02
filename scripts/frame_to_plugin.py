# -*- coding: utf-8 -*-
"""把市场动画（frames.json / .aulaanim.json）转换成可直接放进 effects_custom 的插件。

用法：
    python frame_to_plugin.py <输入文件> --out <effects_custom 目录>
    python frame_to_plugin.py heart-001/frames.json --out "D:\\...\\effects_custom"
    python frame_to_plugin.py xxx.aulaanim.json --out "...\\effects_custom" --studio "...\\studio"

生成的 .py 与软件「动画市场 → 安装」产生的插件格式一致：
zlib + base64 压缩帧数据，render(t, ctx) 逐帧插值。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import zlib

TEMPLATE = '''# -*- coding: utf-8 -*-
"""{label}

由 frame_to_plugin 生成（{date}）。{credit}
想继续改：把同名 .json 放进 studio 目录，用控制台的「动画编辑器」加载。
想手改：直接改下面的 render()，改完在界面点「重新加载插件」。
"""

import base64
import zlib

ID = '{plugin_id}'
LABEL = {label!r}
FPS = {fps!r}          # 每秒播放几帧（编辑器里的「帧率」）
SMOOTH = {smooth!r}    # 相邻帧之间是否做渐变过渡

_DATA = (
{data}
)


def _decode():
    text = zlib.decompress(base64.b64decode(_DATA)).decode('ascii')
    frames = []
    for chunk in text.split(';'):
        frame = {{}}
        for item in chunk.split(' '):
            if not item:
                continue
            key, rgb = item.split(':')
            r, g, b = rgb.split(',')
            frame[int(key)] = (int(r), int(g), int(b))
        frames.append(frame)
    return frames


_FRAMES = _decode()


def render(t, ctx):
    frames = _FRAMES
    if not frames:
        return {{k: (0, 0, 0) for k in ctx.keys}}
    if len(frames) == 1:
        only = frames[0]
        return {{k: only.get(k, (0, 0, 0)) for k in ctx.keys}}

    pos = t * FPS
    index = int(pos) % len(frames)
    if not SMOOTH:
        current = frames[index]
        return {{k: current.get(k, (0, 0, 0)) for k in ctx.keys}}

    frac = pos - int(pos)
    a = frames[index]
    b = frames[(index + 1) % len(frames)]
    out = {{}}
    for key in ctx.keys:
        ca = a.get(key)
        cb = b.get(key)
        if ca is None and cb is None:
            out[key] = (0, 0, 0)
            continue
        ca = ca or (0, 0, 0)
        cb = cb or (0, 0, 0)
        out[key] = (int(ca[0] + (cb[0] - ca[0]) * frac),
                    int(ca[1] + (cb[1] - ca[1]) * frac),
                    int(ca[2] + (cb[2] - ca[2]) * frac))
    return out
'''


def slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '_', str(text or '').lower()).strip('_')
    return slug or 'anim'


def load_frames(path):
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError('不是合法的 JSON 对象')
    if data.get('format') == 'aula-led-market-submission':
        frames_obj = data.get('frames') or {}
        manifest = data.get('manifest') or {}
        source_id = str(manifest.get('id') or '')
        label = str(manifest.get('name') or '')
    else:
        frames_obj = data
        manifest = {}
        source_id = str(data.get('id') or '')
        label = str(data.get('name') or '')
    frames = frames_obj.get('frames')
    if not isinstance(frames, list) or not frames:
        raise ValueError('没有帧数据（frames 必须是非空数组）')
    if len(frames) > 600:
        raise ValueError('帧数超过上限 600')
    if not source_id:
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
        source_id = parent if stem.lower() in ('frames', 'manifest') else stem
    clean = []
    for frame in frames:
        item = {}
        for key, rgb in (frame or {}).items():
            r, g, b = (int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)
            item[int(key)] = (r, g, b)
        clean.append(item)
    if not manifest:
        sibling = os.path.join(os.path.dirname(os.path.abspath(path)), 'manifest.json')
        try:
            with open(sibling, 'r', encoding='utf-8') as fh:
                manifest = json.load(fh)
        except Exception:
            manifest = {}
    return clean, frames_obj, source_id, label, manifest


def encode_frames(frames):
    text = ';'.join(
        ' '.join('%d:%d,%d,%d' % (key, *rgb) for key, rgb in frame.items())
        for frame in frames
    )
    packed = base64.b64encode(zlib.compress(text.encode('ascii'), 9)).decode('ascii')
    lines = [packed[i:i + 66] for i in range(0, len(packed), 66)]
    return '\n'.join("    '%s'" % line for line in lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--out', required=True, help='effects_custom 目录')
    ap.add_argument('--studio', default='', help='可选：同时写 studio 工程 json 的目录')
    ap.add_argument('--id', default='', help='覆盖插件 ID 后缀（默认用动画 id）')
    ap.add_argument('--label', default='', help='覆盖显示名称')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    frames, frames_obj, source_id, label, manifest = load_frames(args.input)
    base = args.id or source_id or os.path.splitext(os.path.basename(args.input))[0]
    slug = slugify(base)
    plugin_id = 'studio_' + slug
    label = args.label or label or slug

    credit_lines = []
    for key, title in (('author', '作者'), ('license', '许可证'), ('description', '说明')):
        value = str(manifest.get(key) or '').strip()
        if value:
            credit_lines.append('%s：%s' % (title, value))
    credit = ('\n' + '\n'.join(credit_lines)) if credit_lines else ''

    os.makedirs(args.out, exist_ok=True)
    target = os.path.join(args.out, plugin_id + '.py')
    if os.path.exists(target) and not args.force:
        raise SystemExit('已存在：%s（确认覆盖加 --force）' % target)

    code = TEMPLATE.format(
        label=label,
        date=time.strftime('%Y-%m-%d %H:%M'),
        credit=credit,
        plugin_id=plugin_id,
        fps=float(frames_obj.get('fps') or 8.0),
        smooth=bool(frames_obj.get('smooth', True)),
        data=encode_frames(frames),
    )
    with open(target, 'w', encoding='utf-8') as fh:
        fh.write(code)
    print('已生成', target, '（%d 帧）' % len(frames))

    if args.studio:
        os.makedirs(args.studio, exist_ok=True)
        project = os.path.join(args.studio, slug + '.json')
        payload = {
            'name': label,
            'fps': float(frames_obj.get('fps') or 8.0),
            'smooth': bool(frames_obj.get('smooth', True)),
            'frames': frames_obj.get('frames'),
            'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            'layout': frames_obj.get('layout') or '',
        }
        with open(project, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('已生成', project)


if __name__ == '__main__':
    sys.exit(main())
