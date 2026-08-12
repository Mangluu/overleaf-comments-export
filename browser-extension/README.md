# Overleaf Comments Export 浏览器扩展

[中文](#中文说明) · [English](#english-guide)

## 中文说明

这个扩展从当前打开的 Overleaf 项目读取评论、回复、评论锚点和可选的
tracked changes，并在本机生成 Markdown、JSON、JSONL 或回复信模板。

它使用当前 Overleaf 标签页已有的登录会话：不需要复制 Cookie，不保存
登录信息，也不会把项目内容发送到第三方服务器。

## 在 Chrome 中加载

1. 在 Chrome 地址栏打开 `chrome://extensions/`。
2. 打开页面右上角的“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择仓库中的扩展目录（选择目录本身，不要选择其中某个文件）：

   ```text
   overleaf-comments-export/browser-extension
   ```

5. 在 Chrome 工具栏的扩展菜单中找到 **Overleaf Comments Export**，并可选地
   将它固定到工具栏。

修改扩展源代码后，回到 `chrome://extensions/`，点击扩展卡片上的“重新加载”，
然后刷新已经打开的 Overleaf 标签页。

## 使用方法

1. 在同一个 Chrome 中登录 Overleaf。
2. 打开项目编辑器页面，地址应类似：

   ```text
   https://www.overleaf.com/project/0123456789abcdef01234567
   ```

3. 点击工具栏中的 **Overleaf Comments Export**。
4. 选择是否包含已解决评论及 tracked changes。
5. 从弹窗的语言选择器中选择 `中文` 或 `English`。界面、运行提示、Markdown 和回复信
   模板会跟随该设置；JSON 字段名保持稳定的英文 schema。
6. 选择输出格式：
   - Markdown：便于直接阅读和提交版本控制。
   - JSON：完整结构化数据。
   - JSONL：每行一个评论记录，便于脚本处理。
   - 回复信模板：为每个未解决评论预留 Response 和 Change made 字段。
7. 点击“导出当前项目”，并保持弹窗打开直到显示“导出完成”。

文件会进入 Chrome 的默认下载目录，位于：

```text
overleaf-comments/<项目名称>/<导出 UTC 时间>/
```

例如：

```text
overleaf-comments/My Paper/2026-08-12T14-35-27Z/
```

其中 `Z` 表示 UTC。每次导出都会创建独立时间目录，避免混淆或覆盖上次结果。
Markdown 和回复信会明确显示每条评论及修订记录的时间；JSON/JSONL 中的评论包含
`created_at` 和 `last_activity_at`，修订记录包含 `timestamp` 和 `occurred_at`。

## 权限说明

- `activeTab`：仅在点击扩展时临时访问当前标签页。
- `scripting`：在当前 Overleaf 页面中执行只读导出逻辑。
- `downloads`：把生成的文件保存到本机。

扩展没有申请 `cookies` 权限，也没有申请访问所有网站的永久权限。

## 常见问题

- **提示当前标签页不是 Overleaf 项目**：先打开项目编辑器，而不是项目列表或
  PDF 分享页面。
- **Overleaf 拒绝请求**：确认当前浏览器已登录，并且当前账号能打开该项目。
- **没有文件名或行号**：Overleaf 的内部 `/ranges` 接口或页面文件树不可用；
  评论内容仍会放入“无法定位的讨论”部分。
- **加载新版本后没有变化**：在扩展管理页重新加载扩展，并刷新 Overleaf 标签页。

Overleaf 使用的是未公开内部接口，未来网站更新可能需要同步调整扩展。

## 开发验证

扩展核心没有第三方 JavaScript 运行时依赖。安装 Node.js 后可运行：

```powershell
npm test
```

原项目及本扩展继续使用仓库根目录的 MIT 许可证。

---

## English guide

This extension reads comments, replies, anchors, and optional tracked changes
from the Overleaf project open in the current tab. It can generate Markdown,
JSON, JSONL, and a response-letter template locally.

It uses the existing signed-in session in the current Overleaf tab. It does not
read or store browser cookies, and it does not send project content to a
third-party server.

### Load it in Chrome

1. Open `chrome://extensions/` in Chrome.
2. Enable **Developer mode** in the top-right corner.
3. Click **Load unpacked**.
4. Select the extension directory in the repository, not an individual file:

   ```text
   overleaf-comments-export/browser-extension
   ```

5. Optionally pin **Overleaf Comments Export** from Chrome's Extensions menu.

After editing the source, click **Reload** on the extension card and refresh
any Overleaf tabs that were already open.

### Use it

1. Sign in to Overleaf in Chrome.
2. Open a project editor URL such as:

   ```text
   https://www.overleaf.com/project/0123456789abcdef01234567
   ```

3. Click the extension icon.
4. Choose whether to include resolved comments and tracked changes.
5. Select `中文` or `English` in the language switcher. The UI,
   progress/error messages, Markdown report, and response-letter template use
   that language. JSON field names remain a stable English schema.
6. Select one or more output formats.
7. Click **Export current project** and keep the popup open until it reports
   completion.

Files are saved under the browser's normal download directory:

```text
overleaf-comments/<project name>/<export time in UTC>/
```

For example:

```text
overleaf-comments/My Paper/2026-08-12T14-35-27Z/
```

`Z` denotes UTC. Every run gets a separate timestamped directory. Markdown and
response letters show the time of each comment and tracked change explicitly.
In JSON/JSONL, comments contain `created_at` and `last_activity_at`; tracked
changes contain `timestamp` and the explicit alias `occurred_at`.

### Permissions

- `activeTab`: temporary access to the current tab after an explicit click.
- `scripting`: runs the read-only export code in the current Overleaf page.
- `downloads`: saves generated files locally.

The extension does not request the `cookies` permission or persistent access
to every website. Overleaf's internal endpoints are undocumented, so a future
site update may require an extension update.
