# AULA LED 市场投稿 Worker

作者在软件里直接投稿，Worker 用服务端 GitHub Token 创建 Pull Request。  
作者不需要 GitHub Token，也不需要 GitHub 账号。

## 1. 准备

- Cloudflare 账号（免费）
- Node.js
- 一个 GitHub Fine-grained PAT，只给 `lovenacho/aula-led-market`：
  - Contents: Read and write
  - Pull requests: Read and write

## 2. 安装 wrangler

```bash
npm install -g wrangler
wrangler login
```

## 3. 配置 Secret

在 `worker` 目录执行：

```bash
wrangler secret put GITHUB_TOKEN
```

粘贴 PAT，回车。

再设置邀请码：

```bash
wrangler secret put SUBMIT_CODE
```

输入一个作者投稿时要填的邀请码，例如：

```text
AULA-2026
```

## 4. 部署

```bash
cd worker
wrangler deploy
```

成功后会得到类似：

```text
https://aula-led-market-submit.<你的子域>.workers.dev
```

## 5. 测试

```bash
curl https://你的地址.workers.dev/health
```

应返回：

```json
{"ok":true,"service":"aula-led-market-submit"}
```

## 6. 软件里填

作者打开「上传到市场」：

- 投稿服务器填：
  ```text
  https://你的地址.workers.dev/submit
  ```
- 邀请码填你设置的 `SUBMIT_CODE`
- 点「作者直传」

Worker 会：

1. 校验投稿包；
2. 检查 ID/同名；
3. 创建分支；
4. 上传 manifest / frames / preview；
5. 更新 index.json；
6. 创建 PR；
7. 返回 PR 链接。

## 7. 你审核

打开 PR，检查预览、帧数、型号、许可证。  
没问题点 **Merge**，市场更新。

## 安全

- GitHub Token 只存在 Worker Secret；
- 作者只能投稿，不能直接写 main；
- PR 不自动合并；
- 建议给 `main` 开分支保护：必须 PR + `validate-market` 通过；
- 邀请码泄露就换一个：`wrangler secret put SUBMIT_CODE`；
- Token 过期就重新生成并更新 Secret。

## 成本

- Cloudflare Workers 免费额度足够小市场；
- GitHub 公开仓库免费；
- 不需要 R2、数据库、VPS。
