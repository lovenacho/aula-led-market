# AULA LED 动画市场（原型）

一个只托管**数据动画**的静态市场，配合 AULA_LED 客户端的「动画市场」入口使用。
市场不包含 `.py`，客户端只下载帧数据，再用本地固定的 studio 保存流程安装。

## 目录

```text
animations/<id>/manifest.json   动画元数据
animations/<id>/frames.json     帧数据（studio JSON，含 frames 数组）
previews/<id>.png               市场预览图
scripts/validate.py             校验清单/帧数据
scripts/build_index.py          生成 index.json
scripts/make_previews.py        生成预览图（开发用）
.github/workflows/              PR 校验 + GitHub Pages 部署
index.json                      由 Actions 自动生成
```

## 发布到 GitHub

1. 新建 Public 仓库，把本目录内容提交上去；
2. Settings → Pages → Source 选 **GitHub Actions**；
3. push 到 `main`，等待 `deploy-market` 完成；
4. 市场索引地址是：
   - `https://<用户名>.github.io/<仓库>/index.json`
   - 或 jsDelivr：`https://cdn.jsdelivr.net/gh/<用户名>/<仓库>@main/index.json`

仓库变大后，把 `animations/` 里的帧数据改放 GitHub Releases 或对象存储，`index.json` 里的 `frames_url` 用绝对地址即可。

## 添加动画

1. 在 `animations/` 新建 `<id>/`；
2. 放 `manifest.json` 和 `frames.json`；
3. 在 `previews/` 放预览图；
4. 本地跑：
   ```bash
   python scripts/validate.py
   python scripts/build_index.py
   ```
5. 提交 PR；Actions 会自动校验。

`frames.json` 可以就是 AULA_LED 导出的 studio 工程 JSON；客户端读取其中的 `frames` 数组。

## 安全约定

- **不要**在市场里放 Python 插件或任何可执行文件；
- 不要接受指向仓库外的 `frames`/`preview` 路径；
- 服务端/客户端都应校验 `sha256`、帧数、fps、颜色范围；
- 公开市场需要人工审核许可证和内容。

## 客户端接入（原型）

客户端优先读取 GitHub/jsDelivr，失败时回落到程序目录里的 demo：

```text
_internal/web/market/index.json
```

正式上传后，把 `app.js` 里 `MARKET_INDEX_URLS` 的第一个地址改成：

```js
const MARKET_INDEX_URLS = [
  'https://cdn.jsdelivr.net/gh/<用户名>/<仓库>@main/index.json',
  'market/index.json',
];
```

保留第二项作为离线/网络不通时的本地示例。

客户端安装流程：

1. 读取 `index.json`；
2. 下载 `frames_url`；
3. 校验 `sha256` / 帧数 / fps；
4. 调用本地 `POST /api/studio/save` 保存为 studio 工程；
5. 已安装状态来自 `GET /api/studio` 的项目列表。
