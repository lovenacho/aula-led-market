/**
 * AULA LED 动画市场投稿 Worker
 *
 * 作者软件 POST /submit，Worker 校验后直接在 GitHub 创建分支和 Pull Request。
 * GitHub Token 只保存在 Worker Secret 里，作者客户端永远拿不到。
 */
const MAX_BODY = 12 * 1024 * 1024;
const MAX_PREVIEW = 2 * 1024 * 1024;
const encoder = new TextEncoder();

function corsHeaders(env) {
  return {
    'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...corsHeaders(env),
    },
  });
}

function b64ToBytes(value) {
  const clean = String(value || '').replace(/^data:[^,]+,/, '').replace(/\s+/g, '');
  const binary = atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToB64(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function textToB64(text) {
  return bytesToB64(encoder.encode(text));
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function github(path, token, options) {
  const res = await fetch('https://api.github.com' + path, {
    ...(options || {}),
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + token,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'aula-led-market-worker',
      'Content-Type': 'application/json',
      ...((options && options.headers) || {}),
    },
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (err) { data = null; }
  if (!res.ok) {
    const message = (data && data.message) || ('GitHub HTTP ' + res.status);
    throw new Error(message);
  }
  return data;
}

function validateFrame(frame, index) {
  if (!frame || typeof frame !== 'object' || Array.isArray(frame)) {
    throw new Error('第 ' + (index + 1) + ' 帧格式不对');
  }
  for (const [key, rgb] of Object.entries(frame)) {
    if (!/^\d+$/.test(key)) throw new Error('第 ' + (index + 1) + ' 帧键位不对');
    if (!Array.isArray(rgb) || rgb.length !== 3
        || rgb.some((v) => !Number.isInteger(v) || v < 0 || v > 255)) {
      throw new Error('第 ' + (index + 1) + ' 帧颜色不对');
    }
  }
}

function normalizePackage(pack) {
  if (!pack || pack.format !== 'aula-led-market-submission') {
    throw new Error('不是有效的投稿包');
  }
  const m = pack.manifest;
  const f = pack.frames;
  if (!m || typeof m !== 'object' || !f || typeof f !== 'object') {
    throw new Error('投稿包缺少 manifest 或 frames');
  }
  const id = String(m.id || '');
  if (!/^[a-z0-9][a-z0-9-]{1,63}$/.test(id)) throw new Error('动画 ID 不合法');
  const name = String(m.name || '').trim();
  if (!name || name.length > 40) throw new Error('动画名长度不对');
  const author = String(m.author || '').trim() || '匿名';
  if (author.length > 40) throw new Error('作者名太长');
  const license = String(m.license || '').trim() || 'CC-BY-4.0';
  const models = Array.isArray(m.models) ? m.models.map(String).slice(0, 8) : [];
  const layouts = Array.isArray(m.layouts) ? m.layouts.map(String).slice(0, 12) : [];
  if (!models.length) throw new Error('至少选择一个适配型号');
  if (!layouts.length) throw new Error('缺少 layouts');
  const fps = Number(m.fps);
  if (!Number.isFinite(fps) || fps <= 0 || fps > 60) throw new Error('fps 不合法');
  const frames = f.frames;
  if (!Array.isArray(frames) || !frames.length) throw new Error('没有帧数据');
  if (frames.length > 600) throw new Error('帧数超过上限');
  frames.forEach(validateFrame);

  const previewBytes = b64ToBytes(pack.preview_png_base64);
  if (!previewBytes.length || previewBytes.length > MAX_PREVIEW) throw new Error('预览图太大');
  if (previewBytes[0] !== 0x89 || previewBytes[1] !== 0x50
      || previewBytes[2] !== 0x4e || previewBytes[3] !== 0x47) {
    throw new Error('预览图不是 PNG');
  }

  const manifest = {
    id,
    name,
    author,
    version: String(m.version || '1.0.0'),
    license,
    min_app: String(m.min_app || 'v2.4.4'),
    description: String(m.description || '').slice(0, 500),
    models,
    layouts,
    fps,
    smooth: !!m.smooth,
    tags: Array.isArray(m.tags) ? m.tags.map(String).slice(0, 10) : [],
    preview: 'previews/' + id + '.png',
    frames: 'animations/' + id + '/frames.json',
  };
  return { id, name, manifest, framesObj: f, previewBytes };
}

async function submit(payload, env) {
  if (!env.GITHUB_TOKEN) throw new Error('Worker 没有配置 GITHUB_TOKEN');
  if (!env.SUBMIT_CODE) throw new Error('Worker 没有配置 SUBMIT_CODE');
  if (String(payload.code || '') !== String(env.SUBMIT_CODE)) {
    return json({ ok: false, error: '邀请码不对' }, 401, env);
  }
  const { id, name, manifest, framesObj, previewBytes } = normalizePackage(payload.package);
  const repo = env.GITHUB_REPO || 'lovenacho/aula-led-market';
  const token = env.GITHUB_TOKEN;

  const ref = await github('/repos/' + repo + '/git/ref/heads/main', token);
  const indexRes = await github('/repos/' + repo + '/contents/index.json', token);
  const indexText = new TextDecoder().decode(b64ToBytes(indexRes.content));
  const index = JSON.parse(indexText);
  if (!Array.isArray(index.animations)) throw new Error('index.json 格式不对');
  if (index.animations.some((a) => a.id === id)) throw new Error('这个 ID 已存在');
  if (index.animations.some((a) => a.name === name)) {
    throw new Error('市场已有同名动画「' + name + '」，请改名后再投稿');
  }

  const framesText = JSON.stringify(framesObj, null, 2) + '\n';
  const framesBytes = encoder.encode(framesText);
  if (framesBytes.length > 5 * 1024 * 1024) throw new Error('帧数据太大');
  const framesSha = await sha256Hex(framesBytes);
  const manifestText = JSON.stringify(manifest, null, 2) + '\n';
  const branch = 'market-upload-' + id;

  await github('/repos/' + repo + '/git/refs', token, {
    method: 'POST',
    body: JSON.stringify({ ref: 'refs/heads/' + branch, sha: ref.object.sha }),
  });

  const putFile = async (path, base64, message, sha) => {
    const body = { message, content: base64, branch };
    if (sha) body.sha = sha;
    const encoded = path.split('/').map(encodeURIComponent).join('/');
    await github('/repos/' + repo + '/contents/' + encoded, token, {
      method: 'PUT', body: JSON.stringify(body),
    });
  };

  await putFile('animations/' + id + '/manifest.json', textToB64(manifestText), 'market: add ' + name);
  await putFile('animations/' + id + '/frames.json', bytesToB64(framesBytes), 'market: add ' + name);
  await putFile('previews/' + id + '.png', bytesToB64(previewBytes), 'market: add ' + name);

  index.animations.push({
    ...manifest,
    frames_url: 'animations/' + id + '/frames.json',
    frames_count: framesObj.frames.length,
    size: framesBytes.length,
    sha256: framesSha,
  });
  index.animations.sort((a, b) => String(a.id).localeCompare(String(b.id)));
  index.updated = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  await putFile('index.json', textToB64(JSON.stringify(index, null, 2) + '\n'),
    'market: index for ' + name, indexRes.sha);

  const pr = await github('/repos/' + repo + '/pulls', token, {
    method: 'POST',
    body: JSON.stringify({
      title: '[market] ' + name,
      head: branch,
      base: 'main',
      body: '投稿动画：' + name + '\n\n'
        + '- 作者：' + manifest.author + '\n'
        + '- 适配：' + models.join(' / ') + '\n'
        + '- 许可证：' + manifest.license + '\n'
        + '- 帧数：' + framesObj.frames.length + ' @ ' + manifest.fps + 'fps\n\n'
        + '由投稿 Worker 自动创建，请审核后合并。',
    }),
  });
  return json({ ok: true, id, branch, pr_url: pr.html_url }, 200, env);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }
    if (url.pathname === '/health' && request.method === 'GET') {
      return json({ ok: true, service: 'aula-led-market-submit' }, 200, env);
    }
    if (url.pathname !== '/submit') {
      return json({ ok: false, error: 'not found' }, 404, env);
    }
    if (request.method !== 'POST') {
      return json({ ok: false, error: 'method not allowed' }, 405, env);
    }
    const declared = Number(request.headers.get('Content-Length') || 0);
    if (declared > MAX_BODY) return json({ ok: false, error: '投稿包太大' }, 413, env);
    let text;
    try {
      text = await request.text();
    } catch (err) {
      return json({ ok: false, error: '读取请求失败' }, 400, env);
    }
    if (text.length > MAX_BODY) return json({ ok: false, error: '投稿包太大' }, 413, env);
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (err) {
      return json({ ok: false, error: '请求不是合法 JSON' }, 400, env);
    }
    try {
      return await submit(payload, env);
    } catch (err) {
      return json({ ok: false, error: String(err.message || err) }, 500, env);
    }
  },
};
