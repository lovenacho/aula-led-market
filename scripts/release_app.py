#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AULA LED 一键发版：版本号 → 内核 → 打包 → Gitee → latest.json → 校验。

用法：
    python release_app.py --version v2.5.5 --notes "本次更新内容"
    python release_app.py --version v2.5.5 --notes "..." --dry-run
    python release_app.py --version v2.5.5 --notes "..." --app "D:\\测试\\AULA_LED_v2.5.4_Stable"

凭据（优先级：命令行 > 环境变量 > 配置文件）：
    环境变量 GITEE_TOKEN / GITHUB_TOKEN
    或 %USERPROFILE%\\.aula_release.json:
        {"gitee_token": "...", "github_token": "...", "app": "D:\\\\测试\\\\AULA_LED_v2.5.4_Stable"}

只做本地构建、不发布：加 --dry-run。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import date
from pathlib import Path

TOOLS = Path(r'D:\测试\AULA_LED v2.4.2源代码\_tools')
VERSION_SRC = TOOLS / 'patch_pkg' / 'aula' / 'version.py'
WORK_ROOT = Path(r'D:\测试')
GITEE_API = 'https://gitee.com/api/v5'
GH_API = 'https://api.github.com'
UA = {'User-Agent': 'aula-led-release'}


# ---------------------------------------------------------------- 基础工具
def log(msg):
    print(msg, flush=True)


def load_config():
    cfg_path = Path(os.path.expanduser('~')) / '.aula_release.json'
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def detect_app_dir(cfg):
    if cfg.get('app') and Path(cfg['app']).is_dir():
        return Path(cfg['app'])
    candidates = []
    for p in WORK_ROOT.glob('AULA_LED_v*_Stable'):
        if '.old-' in p.name:
            continue
        m = re.search(r'v(\d+)\.(\d+)\.(\d+)', p.name)
        if m:
            candidates.append((tuple(int(x) for x in m.groups()), p))
    if not candidates:
        raise SystemExit('找不到程序目录，请用 --app 指定')
    return max(candidates)[1]


def read_current_version():
    text = VERSION_SRC.read_text(encoding='utf-8')
    m = re.search(r"VERSION\s*=\s*'([^']+)'", text)
    if not m:
        raise SystemExit('读不到 version.py 里的 VERSION')
    return m.group(1)


def version_tuple(text):
    nums = re.findall(r'\d+', text)
    return tuple(int(x) for x in nums[:3]) or (0,)


def stop_app():
    try:
        import urllib.request as u
        req = u.Request('http://127.0.0.1:8720/api/quit', data=b'{}', method='POST',
                        headers={'Content-Type': 'application/json'})
        u.urlopen(req, timeout=5).read()
    except Exception:
        pass
    subprocess.run(['taskkill', '/F', '/IM', 'AULA_LED_Core.exe'], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'AULA_LED.exe'], capture_output=True)
    time.sleep(3)


def start_app(app_dir):
    exe = app_dir / 'AULA_LED.exe'
    if not exe.exists():
        return
    subprocess.Popen([str(exe)], cwd=str(app_dir), close_fds=True,
                     creationflags=0x00000008,
                     stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- 版本与内核
def version_source(version, note):
    return (
        "# -*- coding: utf-8 -*-\n"
        '"""版本号（单一来源）。界面、托盘、接口都从这里取，改版本只动这个文件。"""\n\n'
        "VERSION = %r\n"
        "VERSION_NOTE = %r\n"
    ) % (version, note)


def build_core(app_dir, version, note, out_path):
    sys.path.insert(0, str(TOOLS))
    from pyinstaller_pyz import CArchive, Pyz  # noqa: E402

    src = app_dir / 'AULA_LED_Core.exe'
    blob = src.read_bytes()
    arc = CArchive(blob)
    entry = next(e for e in arc.entries if e['typ'] == 'z')
    pyz = Pyz(arc.payload(entry))
    if 'aula.version' not in pyz.names:
        raise SystemExit('PYZ 缺少 aula.version')
    import marshal
    code = compile(version_source(version, note), r'aula\version.py', 'exec')
    new_pyz = pyz.rebuild({'aula.version': marshal.dumps(code)})
    new_exe = arc.rebuild({entry['name']: new_pyz}, blob[:arc.pkg_start])
    out_path.write_bytes(new_exe)
    return hashlib.sha256(new_exe).hexdigest().upper()


def update_index(app_dir, version):
    index = app_dir / '_internal' / 'web' / 'index.html'
    text = index.read_text(encoding='utf-8')
    text = re.sub(r'(id="verBadge">)v[0-9.]+', r'\g<1>' + version, text)
    text = re.sub(r'(id="verFoot">)v[0-9.]+', r'\g<1>' + version, text)
    index.write_text(text, encoding='utf-8')


def update_docs(app_dir, version, note, core_sha):
    today = date.today().isoformat()
    short = note.split('\n')[0][:60]
    for name in ('发布说明.txt', '使用说明.txt'):
        path = app_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'^(AULA 键盘灯光控制台 )v[0-9.]+', r'\g<1>' + version, text, count=1, flags=re.M)
        lines = text.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith('版本 v'):
                lines[i] = '版本 %s · %s（%s）' % (version, today, short)
                break
        text = '\n'.join(lines) + '\n'
        text = re.sub(r'(主程序 AULA_LED_Core\.exe SHA-256：)[0-9A-Fa-f]{64}', r'\g<1>' + core_sha, text)
        path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------- 打包
def pack_zip(app_dir, out_zip):
    skip_root = {'AULA_LED.log', 'settings.json'}
    count = 0
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(app_dir):
            dirs[:] = [d for d in dirs if not d.startswith('_bak')]
            rel = os.path.relpath(root, app_dir)
            for name in sorted(files):
                if rel == '.' and name in skip_root:
                    continue
                if name.lower().endswith('.bak'):
                    continue
                if name.startswith('AULA_LED_Core.exe.bak'):
                    continue
                full = Path(root) / name
                z.write(full, full.relative_to(app_dir).as_posix())
                count += 1
    data = out_zip.read_bytes()
    return count, len(data), hashlib.sha256(data).hexdigest().upper()


# ---------------------------------------------------------------- Gitee
def gitee_api(token, path, method='GET', data=None, timeout=600):
    q = urllib.parse.urlencode({'access_token': token})
    url = GITEE_API + path + ('&' if '?' in path else '?') + q
    headers = dict(UA)
    body = None
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def gitee_ensure_repo(token, owner, repo):
    try:
        info = gitee_api(token, '/repos/%s/%s' % (owner, repo))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        info = gitee_api(token, '/user/repos', method='POST', data={
            'name': repo, 'private': False, 'auto_init': True,
            'description': 'AULA LED update packages'})
    if info.get('private'):
        info = gitee_api(token, '/repos/%s/%s' % (owner, repo), method='PATCH', data={
            'name': repo, 'private': False, 'has_issues': True,
            'has_wiki': True, 'can_comment': True})
    return info


def gitee_upload(token, owner, repo, version, zip_path):
    tag = version
    rel = None
    try:
        got = gitee_api(token, '/repos/%s/%s/releases/tags/%s' % (owner, repo, tag))
        if isinstance(got, dict) and got.get('id'):
            rel = got
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    if rel is None:
        rel = gitee_api(token, '/repos/%s/%s/releases' % (owner, repo), method='POST', data={
            'tag_name': tag, 'name': 'AULA LED %s' % version,
            'body': 'AULA LED %s' % version, 'target_commitish': 'master'})
    boundary = '----aula' + uuid.uuid4().hex
    blob = zip_path.read_bytes()
    body = b''.join([
        ('--' + boundary + '\r\n').encode(),
        ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % zip_path.name).encode(),
        b'Content-Type: application/zip\r\n\r\n', blob,
        ('\r\n--' + boundary + '--\r\n').encode(),
    ])
    q = urllib.parse.urlencode({'access_token': token})
    url = '%s/repos/%s/%s/releases/%d/attach_files?%s' % (
        GITEE_API, owner, repo, rel['id'], q)
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'User-Agent': 'aula-led-release',
        'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with urllib.request.urlopen(req, timeout=900) as resp:
        asset = json.loads(resp.read().decode('utf-8'))
    return asset['browser_download_url'], rel


# ---------------------------------------------------------------- GitHub 清单
def github_token():
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    try:
        out = subprocess.run(['git', 'credential', 'fill'], input=b'protocol=https\nhost=github.com\n\n',
                             capture_output=True, timeout=10).stdout.decode('utf-8', 'replace')
        for line in out.splitlines():
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''


def github_update_manifest(token, repo, manifest):
    path = '/repos/%s/contents/latest.json' % repo
    headers = {'Authorization': 'token ' + token, 'User-Agent': 'aula-led-release'}
    sha = None
    try:
        req = urllib.request.Request(GH_API + path + '?ref=main', headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            sha = json.loads(resp.read().decode('utf-8'))['sha']
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    payload = {
        'message': 'release: %s' % manifest['version'],
        'content': base64.b64encode(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')).decode('ascii'),
        'branch': 'main',
    }
    if sha:
        payload['sha'] = sha
    req = urllib.request.Request(GH_API + path, data=json.dumps(payload).encode('utf-8'),
                                 method='PUT', headers=dict(headers, **{'Content-Type': 'application/json'}))
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))['commit']['sha'][:8]


def probe_url(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-1048575'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(1048576)
    return len(data), time.time() - t0


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--notes', default='')
    ap.add_argument('--app', default='')
    ap.add_argument('--gitee-token', default='')
    ap.add_argument('--github-token', default='')
    ap.add_argument('--gitee-owner', default='')
    ap.add_argument('--gitee-repo', default='aula-led-updates')
    ap.add_argument('--manifest-repo', default='lovenacho/aula-led-market')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-docs', action='store_true')
    ap.add_argument('--no-restart', action='store_true')
    args = ap.parse_args()

    version = args.version if args.version.startswith('v') else 'v' + args.version
    if not re.fullmatch(r'v\d+\.\d+\.\d+', version):
        raise SystemExit('版本号格式应为 v2.5.5')

    cfg = load_config()
    app_dir = Path(args.app) if args.app else detect_app_dir(cfg)
    if not (app_dir / 'AULA_LED_Core.exe').exists():
        raise SystemExit('程序目录不对：%s' % app_dir)

    old_version = read_current_version()
    if version_tuple(version) <= version_tuple(old_version):
        raise SystemExit('新版本 %s 必须大于当前 %s' % (version, old_version))

    gitee = args.gitee_token or os.environ.get('GITEE_TOKEN') or cfg.get('gitee_token', '')
    github = args.github_token or cfg.get('github_token', '') or github_token()
    owner = args.gitee_owner or (gitee_api(gitee, '/user')['login'] if gitee else '')

    log('程序目录 : %s' % app_dir)
    log('版本     : %s -> %s' % (old_version, version))
    if not args.dry_run:
        if not gitee:
            raise SystemExit('缺少 Gitee 令牌（GITEE_TOKEN 或 --gitee-token）')
        if not github:
            raise SystemExit('缺少 GitHub 令牌（GITHUB_TOKEN 或 --github-token）')

    stop_app()
    out_exe = app_dir / 'AULA_LED_Core.exe.new'
    core_sha = build_core(app_dir, version, args.notes, out_exe)
    backup = app_dir / ('AULA_LED_Core.exe.bak-' + old_version.replace('.', ''))
    if not backup.exists():
        shutil.copy2(app_dir / 'AULA_LED_Core.exe', backup)
    out_exe.replace(app_dir / 'AULA_LED_Core.exe')
    log('内核     : %s (sha %s…)' % ((app_dir / 'AULA_LED_Core.exe').stat().st_size, core_sha[:12]))

    update_index(app_dir, version)
    if not args.skip_docs:
        update_docs(app_dir, version, args.notes, core_sha)

    work = app_dir.parent / '_release' / version
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / ('AULA_LED_%s_Stable.zip' % version)
    count, size, zip_sha = pack_zip(app_dir, zip_path)
    log('打包     : %s（%d 个文件，%d 字节，sha %s…）' % (zip_path.name, count, size, zip_sha[:12]))

    if args.dry_run:
        log('（--dry-run，跳过上传与清单更新）')
        if not args.no_restart:
            start_app(app_dir)
        return 0

    if not args.skip_docs:
        VERSION_SRC.write_text(version_source(version, args.notes.split('\n')[0][:80]), encoding='utf-8')

    log('Gitee    : 上传中…')
    repo = gitee_ensure_repo(gitee, owner, args.gitee_repo)
    url, rel = gitee_upload(gitee, owner, args.gitee_repo, version, zip_path)
    log('Gitee    : %s' % url)

    manifest = {
        'version': version,
        'url': url,
        'sha256': zip_sha,
        'size': size,
        'min_app': 'v2.5.0',
        'notes': args.notes,
        'published': date.today().isoformat(),
        'mirrors': [],
    }
    commit = github_update_manifest(github, args.manifest_repo, manifest)
    log('清单     : 已更新（%s）' % commit)

    try:
        got, dt = probe_url(url)
        log('测速     : %.0f KB/s（前 1MB，%.1f 秒）' % (got / 1024 / max(dt, 0.001), dt))
    except Exception as exc:
        log('测速失败 : %r' % exc)

    if not args.no_restart:
        start_app(app_dir)
    log('完成     : %s' % version)
    return 0


if __name__ == '__main__':
    sys.exit(main())
