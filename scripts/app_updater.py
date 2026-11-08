# -*- coding: utf-8 -*-
"""应用更新器（原型）：检查清单 → 下载校验 → 退出应用 → 替换 → 重启 → 失败回滚。

用法：
    python app_updater.py --manifest <latest.json 的 URL> --app <程序目录> [--apply]

不带 --apply 只做检查/下载/校验，不替换文件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

LOCAL_API = 'http://127.0.0.1:8720'
USER_FILES = ('settings.json',)
USER_DIRS = ('effects_custom', 'studio', 'model_data')


def parse_version(text):
    nums = re.findall(r'\d+', str(text or ''))
    return tuple(int(n) for n in nums[:4]) or (0,)


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def http_get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def http_post(url, timeout=10):
    req = urllib.request.Request(url, data=b'{}', method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def app_meta():
    try:
        return json.loads(http_get(LOCAL_API + '/api/meta', timeout=5))
    except Exception:
        return None


def ask_app_quit(timeout=25):
    try:
        http_post(LOCAL_API + '/api/quit')
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if app_meta() is None:
            return True
        time.sleep(0.5)
    return False


def download(url, dest, sha256=None, size=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, 'wb') as fh:
        length = int(resp.headers.get('Content-Length') or 0)
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            total += len(chunk)
            if length:
                pct = total * 100 // length
                sys.stdout.write('\r下载中 %d%% (%.1f/%.1f MB)' % (pct, total / 1048576, length / 1048576))
                sys.stdout.flush()
    print()
    actual = digest.hexdigest()
    if size and total != int(size):
        raise SystemExit('大小不符：期望 %s，实际 %s' % (size, total))
    if sha256 and actual.lower() != str(sha256).lower():
        raise SystemExit('SHA-256 不符：期望 %s，实际 %s' % (sha256, actual))
    return actual


def extract(zip_path, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    if not (dest / 'AULA_LED.exe').exists() or not (dest / 'AULA_LED_Core.exe').exists():
        raise SystemExit('更新包结构不对：缺少 AULA_LED.exe / AULA_LED_Core.exe')


def copy_user_data(old_root, new_root):
    for name in USER_FILES:
        src = old_root / name
        if src.exists():
            shutil.copy2(src, new_root / name)
    for name in USER_DIRS:
        src = old_root / name
        if src.is_dir():
            shutil.copytree(src, new_root / name, dirs_exist_ok=True)


def swap(old_root, new_root, backup_root):
    old_root.rename(backup_root)
    try:
        new_root.rename(old_root)
    except Exception:
        backup_root.rename(old_root)
        raise


def kill_app():
    for name in ('AULA_LED_Core.exe', 'AULA_LED.exe'):
        subprocess.run(['taskkill', '/F', '/IM', name], capture_output=True)


def start_app(app_root, core_only=False):
    exe = app_root / ('AULA_LED_Core.exe' if core_only else 'AULA_LED.exe')
    subprocess.Popen([str(exe)], cwd=str(app_root), close_fds=True,
                     creationflags=0x00000008)


def wait_version(expected, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        meta = app_meta()
        if meta and meta.get('version'):
            return meta
        time.sleep(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--app', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--start-core', action='store_true', help='只启动 AULA_LED_Core.exe（测试/无启动器场景）')
    ap.add_argument('--workdir', default='')
    args = ap.parse_args()

    app_root = Path(args.app).resolve()
    meta = app_meta()
    if not meta:
        raise SystemExit('应用没有在运行（需要先启动，才能读取当前版本并安全退出）')
    current = meta.get('version') or 'v0.0.0'
    print('当前版本:', current)

    info = fetch_json(args.manifest)
    latest = info.get('version') or ''
    print('清单版本:', latest)
    if parse_version(latest) <= parse_version(current):
        print('已是最新版本，无需更新。')
        return 0
    print('发现新版本:', latest)
    if info.get('notes'):
        print('更新说明:', info.get('notes'))

    work = Path(args.workdir) if args.workdir else app_root.parent / ('.aula_update_' + time.strftime('%Y%m%d_%H%M%S'))
    zip_path = work / ('update_%s.zip' % parse_version(latest)[-1])
    print('下载:', info['url'])
    download(info['url'], zip_path, info.get('sha256'), info.get('size'))
    print('校验通过:', zip_path)

    unpacked = work / 'new'
    if unpacked.exists():
        shutil.rmtree(unpacked)
    extract(zip_path, unpacked)
    print('解压完成:', unpacked)

    if not args.apply:
        print('（未加 --apply，只检查/下载/校验，不替换）')
        return 0

    print('通知应用退出…')
    if not ask_app_quit():
        raise SystemExit('应用没有按时退出，已中止（未改动任何文件）')

    copy_user_data(app_root, unpacked)
    backup = app_root.parent / (app_root.name + '.old-' + time.strftime('%Y%m%d_%H%M%S'))
    print('备份旧版本 ->', backup.name)
    swap(app_root, unpacked, backup)
    print('替换完成，启动新版本…')
    result = None
    try:
        start_app(app_root, args.start_core)
        result = wait_version(latest)
    except Exception as exc:
        print('启动失败:', exc)
    if not result:
        print('新版本没有起来，尝试回滚…')
        kill_app()
        time.sleep(1)
        for _ in range(10):
            try:
                shutil.rmtree(app_root)
                break
            except Exception:
                time.sleep(0.5)
        backup.rename(app_root)
        try:
            start_app(app_root, args.start_core)
        except Exception as exc:
            print('旧版本也没能自动启动，请手动运行 AULA_LED.exe：', exc)
        raise SystemExit('更新失败，已回滚到旧版本')
    print('更新成功：', result.get('version'), '| 机型:', result.get('model'))
    print('旧版本备份在:', backup)
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
