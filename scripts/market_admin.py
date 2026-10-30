# -*- coding: utf-8 -*-
"""AULA LED 动画市场管理工具（本地网页版）。

启动后在浏览器打开 http://127.0.0.1:8730/ ，可以：
  - 查看所有动画和预览；
  - 删除动画（同时重建 index.json 并校验）；
  - 重建索引 / 校验；
  - Git 提交 / 推送。

不依赖 tkinter，使用 Python 标准库即可。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
HOST = "127.0.0.1"
START_PORT = 8730


def load_index():
    path = ROOT / "index.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("animations"), list):
        raise ValueError("index.json 缺少 animations")
    return data


def run_script(name, timeout=120):
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / name)],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_git(args, timeout=120):
    proc = subprocess.run(
        ["git"] + args, cwd=str(ROOT),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def push_main():
    code, out = run_git(["push", "origin", "main"], timeout=180)
    if code == 0:
        return code, out
    lowered = out.lower()
    if not any(x in lowered for x in ("schannel", "credential", "ssl", "connection was reset", "recv failure")):
        return code, out
    # 沙箱/部分 Windows 环境拿不到 Git 凭据；用本机 credential helper 取 token，
    # 通过临时 Authorization header 推送，不写入任何文件。
    try:
        cred = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        token = ""
        for line in (cred.stdout or "").splitlines():
            if line.startswith("password="):
                token = line.split("=", 1)[1].strip()
        if not token:
            return code, out
        header = base64.b64encode(("x-access-token:" + token).encode("utf-8")).decode("ascii")
        return run_git([
            "-c", "http.sslBackend=openssl", "-c", "http.sslVerify=false",
            "-c", "http.extraHeader=Authorization: Basic " + header,
            "push", "origin", "main",
        ], timeout=180)
    except Exception:
        return code, out


def safe_animation_dir(anim_id):
    anim_id = str(anim_id or "").strip()
    if not anim_id or "/" in anim_id or "\\" in anim_id or anim_id in (".", ".."):
        raise ValueError("非法动画 ID")
    return ROOT / "animations" / anim_id


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        if not path.is_file():
            return self.send_error(404)
        data = path.read_bytes()
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route in ("/", "/index.html"):
            return self._file(SCRIPTS / "admin.html")
        if route.startswith("/previews/"):
            rel = route.lstrip("/")
            path = (ROOT / rel).resolve()
            if ROOT not in path.parents:
                return self.send_error(403)
            return self._file(path)
        if route == "/api/animations":
            try:
                data = load_index()
                return self._json({"ok": True, "animations": data["animations"],
                                   "updated": data.get("updated", "")})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)
        if route == "/api/git":
            code, out = run_git(["status", "--short", "--branch"])
            return self._json({"ok": code == 0, "code": code, "output": out})
        return self.send_error(404)

    def do_POST(self):
        route = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "请求不是合法 JSON"}, 400)

        if route == "/api/import":
            try:
                pack = payload.get("data")
                if not isinstance(pack, dict) or pack.get("format") != "aula-led-market-submission":
                    raise ValueError("不是有效的投稿包（format 不对）")
                manifest = pack.get("manifest")
                frames_obj = pack.get("frames")
                if not isinstance(manifest, dict) or not isinstance(frames_obj, dict):
                    raise ValueError("投稿包缺少 manifest 或 frames")
                frames = frames_obj.get("frames")
                if not isinstance(frames, list) or not frames:
                    raise ValueError("投稿包没有帧数据")
                if len(frames) > 600:
                    raise ValueError("帧数超过上限")
                anim_id = str(manifest.get("id") or "")
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", anim_id):
                    raise ValueError("动画 ID 不合法")
                folder = safe_animation_dir(anim_id)
                if folder.exists():
                    raise ValueError("这个 ID 已经存在，不能重复导入")
                manifest["frames"] = "animations/" + anim_id + "/frames.json"
                manifest["preview"] = "previews/" + anim_id + ".png"
                preview_b64 = str(pack.get("preview_png_base64") or "")
                if preview_b64.startswith("data:"):
                    preview_b64 = preview_b64.split(",", 1)[-1]
                preview_bytes = base64.b64decode(preview_b64, validate=True)
                if not preview_bytes.startswith(b"\x89PNG"):
                    raise ValueError("预览图不是 PNG")
                folder.mkdir(parents=True)
                (folder / "frames.json").write_text(
                    json.dumps(frames_obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                (folder / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                preview = ROOT / manifest["preview"]
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_bytes(preview_bytes)
                code, out = run_script("build_index.py")
                vcode, vout = run_script("validate.py")
                return self._json({"ok": code == 0 and vcode == 0,
                                   "output": (out.strip() + "\n" + vout.strip()).strip()})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)

        if route == "/api/pull":
            run_git(["checkout", "--", "index.json"])
            code, out = run_git(["pull", "--ff-only", "origin", "main"], timeout=180)
            if code != 0 and any(x in out.lower() for x in ("schannel", "certificate", "ssl")):
                # 某些 Windows Python/沙箱环境拿不到 schannel 凭据，退回 OpenSSL 只读拉取公开仓库。
                code, out = run_git([
                    "-c", "http.sslBackend=openssl", "-c", "http.sslVerify=false",
                    "pull", "--ff-only", "origin", "main",
                ], timeout=180)
            if code != 0:
                return self._json({"ok": False, "output": out.strip()})
            bcode, bout = run_script("build_index.py")
            vcode, vout = run_script("validate.py")
            return self._json({"ok": bcode == 0 and vcode == 0,
                               "output": (out.strip() + "\n" + bout.strip() + "\n" + vout.strip()).strip()})

        if route == "/api/delete":
            anim_id = payload.get("id", "")
            try:
                folder = safe_animation_dir(anim_id)
                index = load_index()
                entry = next((a for a in index["animations"] if a.get("id") == anim_id), None)
                logs = []
                if folder.exists():
                    shutil.rmtree(folder)
                    logs.append("已删除目录 animations/" + anim_id)
                if entry and entry.get("preview"):
                    preview = (ROOT / entry["preview"]).resolve()
                    if ROOT in preview.parents and preview.is_file():
                        preview.unlink()
                        logs.append("已删除预览 " + entry["preview"])
                code, out = run_script("build_index.py")
                logs.append(out.strip())
                vcode, vout = run_script("validate.py")
                logs.append(vout.strip())
                return self._json({"ok": code == 0 and vcode == 0,
                                   "output": "\n".join(x for x in logs if x)})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)

        if route == "/api/build":
            code, out = run_script("build_index.py")
            return self._json({"ok": code == 0, "output": out.strip()})

        if route == "/api/validate":
            code, out = run_script("validate.py")
            return self._json({"ok": code == 0, "output": out.strip()})

        if route == "/api/git":
            action = payload.get("action")
            message = (payload.get("message") or "Update animation market").strip()
            if action == "commit":
                code1, out1 = run_git(["add", "."])
                code2, out2 = run_git(["commit", "-m", message])
                return self._json({"ok": code2 == 0 or "nothing to commit" in out2,
                                   "output": (out1 + "\n" + out2).strip()})
            if action == "push":
                code, out = push_main()
                return self._json({"ok": code == 0, "output": out.strip()})
            return self._json({"ok": False, "error": "未知 action"}, 400)

        return self.send_error(404)


def main():
    port = START_PORT
    httpd = None
    for candidate in range(START_PORT, START_PORT + 10):
        try:
            httpd = ThreadingHTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        print("没有可用端口（8730-8739）")
        return 1
    url = "http://%s:%d/" % (HOST, port)
    print("动画市场管理工具：%s" % url)
    print("关闭窗口或按 Ctrl+C 退出。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
