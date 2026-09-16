# capabilities/feishu — Feishu Base Capability

## 能力定位

**领域无关的飞书原语集合**。当前包含：

- **docx 云文档写入**（`capabilities.feishu.docx`）：内容（Markdown/HTML）→ 飞书云文档。

不负责业务内容组装（报告版式/章节由调用方生成），也不包含 Bitable / 消息推送（分别属其他原语）。

## namespace 与入口

```python
from capabilities.feishu.docx import FeishuDocxClient

client = FeishuDocxClient(folder_token="BNAnf...")   # 默认读 FEISHU_DOCX_FOLDER_TOKEN
res = client.create_document_from_markdown("标题", "# H1\n正文")
# -> {"document_id": "dox...", "url": "https://<host>/docx/dox...", "blocks": N, "revision_id": R}
```

公开方法：

| 方法 | 说明 |
|------|------|
| `create_document(title, folder_token=None)` | 建空文档，返回 `document_id` |
| `convert_to_blocks(content, content_type="markdown")` | 服务端内容→blocks（支持 markdown/html） |
| `insert_descendants(document_id, blocks, first_level_block_ids)` | 批量插入 blocks |
| `create_children(document_id, children, block_id=None, index=-1)` | 在指定父块下创建子块（默认根节点） |
| `upload_media(file_path, parent_node, parent_type="docx_image", drive_route_token=None)` | 上传媒体（云空间不可见），返回 `file_token` |
| `insert_image(document_id, file_path, block_id=None, index=-1)` | 三步插入 image 块（block_type 27）：建空块→上传媒体→`replace_image` |
| `create_document_from_markdown(title, md)` / `create_document_from_content(...)` | 一键三步（建文档→转换→插入） |
| `create_document_from_html(title, html)` | 本地 HTML→Markdown（markdownify）后走同链路 |
| `document_url(document_id)` | 拼文档 URL |

`dry_run=True` 只返回计划（不触网）。

### 图片块（易踩坑）

图片写入**必须三步走**，不能一步创建带 token 的图片块（会 `1770001 invalid param`）：

1. 创建空图片块：`POST .../blocks/{doc}/children`，`[{"block_type": 27, "image": {}}]`，记录返回的 `block_id`
2. 上传媒体：`POST /drive/v1/medias/upload_all`，`parent_type=docx_image`，`parent_node=<空图片块 block_id>`，`extra={"drive_route_token": "<document_id>"}`
3. 绑定 token：`PATCH .../blocks/{block_id}`，`{"replace_image": {"token": "<file_token>"}}`

scope：图片上传需 `docs:document.media:upload`（易漏）；块写入用 `docx:document`。`im:resource:upload` 与 Docx 图片无关。

上传接口返回 `code:0` 不代表图片可用；必须回读 blocks，确认 `block_type==27`、`image.token` 非空、宽高为真实尺寸（不是 `100x100`）。

**完整踩坑过程见 `docs/image_upload_notes.md`。**

## 实现路线

**Markdown/HTML → Block Convert**（服务端转换，不手写 block/table renderer）：

1. `POST /open-apis/docx/v1/documents` — 建文档（`folder_token` + `title`）
2. `POST /open-apis/docx/v1/documents/blocks/convert` — `{content_type, content}` → `blocks` + `first_level_block_ids`
3. `POST /open-apis/docx/v1/documents/{id}/blocks/{id}/descendant` — 批量插入

HTML 输入先在本地用 `markdownify` 归一为 Markdown（`converter.to_markdown`），复用同一服务端转换。

## 认证与 env

- 认证：`tenant_access_token`（应用身份；`capabilities.feishu.auth.tenant_access_token`，带缓存）。

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 应用凭据（必需） |
| `FEISHU_DOCX_FOLDER_TOKEN` | 默认目标文件夹 token |
| `FEISHU_TENANT_HOST` | 文档 URL host（默认 `r4i0myjr3j.feishu.cn`） |
| `FEISHU_API_BASE` | Open API base（默认 `https://open.feishu.cn/open-apis`） |

## 权限前提（应用身份）

- scope：`docx:document`（或 `docx:document:create`）；建议加 `drive:drive`。
- 落点：**tenant 身份只能写「应用自建文件夹」，或已把应用加为协作者的文件夹**，否则报 `1770040 no folder permission` / `1770032 forbidden`。
- 缺 scope 报 `99991672`（错误信息含申请链接）。

`FeishuAPIError` 对上述错误码附带中文排障提示。

## 边界（not for）

- Bitable / Sheets 写入、群消息推送、收消息 bot、文件下载采集 —— 均属其他原语。
- 业务报告版式与内容组装 —— 留在调用方（如 `presale_cumulative_order_compare.py --to-feishu`）。

## tests

```bash
python -m pytest capabilities/feishu/tests -q      # 离线，注入 fake HTTP
```

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| `mashang_workspace/research_scripts/presale_cumulative_order_compare.py --to-feishu` | 预售报告 → 飞书云文档 | ✅ |
