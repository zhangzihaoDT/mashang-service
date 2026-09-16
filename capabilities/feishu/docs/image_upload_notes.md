# Feishu Docx 图片块写入 — 踩坑经验

> 背景：`presale_cumulative_order_compare.py --to-feishu` 需要把本地 PNG 图表嵌入飞书云文档。
> 从「正文可写、图片全失败」到「6/6 图片成功」，经历了多轮试错。以下是可复现的结论。

## 结论：图片写入必须走三步，不能一步建块

官方文档规定（`文档 FAQs / Create blocks / Update a block`）：

1. **创建空图片块**
   ```json
   POST /docx/v1/documents/{document_id}/blocks/{document_id}/children
   { "index": 0, "children": [ { "block_type": 27, "image": {} } ] }
   ```
   记录返回的 `children[0].block_id`（空块 `image.token=""`，宽高 100）。

2. **上传媒体，且绑定到图片块 **（不是文档）
   ```http
   POST /drive/v1/medias/upload_all
   Content-Type: multipart/form-data
   ```
   | 字段 | 值 |
   |------|-----|
   | `file_name` | 文件名 |
   | `parent_type` | `docx_image` |
   | `parent_node` | **第 1 步的空图片块 `block_id`** |
   | `size` | 字节数 |
   | `extra` | `{"drive_route_token": "<document_id>"}`（JSON 字符串） |
   | `file` | 文件字节，如 `image/png` |

   返回 `data.file_token`。

3. **用 replace_image 绑定 token**
   ```json
   PATCH /docx/v1/documents/{document_id}/blocks/{block_id}
   { "replace_image": { "token": "<file_token>" } }
   ```

之后：上传媒体结束；把第 2 步得到的 `file_token` 写入图片块。

## 试错路径（每个坑的具体表现）

| 尝试 | 现象 | 结论 |
|------|------|------|
| 一步建块 `{block_type:27, image:{token:<drive文件token>}}` | `1770001 invalid param` | 图片块不能随文件 token 直接创建 |
| 一步建块 `image.file_token` | API 成功，但块是**空占位**：`image.token=""`，宽高 100，前端「图片上传失败」 | `file_token` 字段被静默忽略，不是图片块契约字段 |
| 用 `im/v1/images` 的 `image_key` 填 `image.token` | `1770001 invalid param` | IM 图片与 Docx 图片是两套媒体体系，不能混用 |
| 媒体绑定到**文档 id**（`parent_node=document_id`） | 媒体上传成功，但建图块仍失败；需读文档回查才能发现 | 上传「成功」≠ 能用于 Docx，绑定目标必须是图片块 |
| 只授权 `im:resource:upload` / `drive:drive` | 媒体上传成功、图片块仍失败 | Docx 图片需要独立的 `docs:document.media:upload` scope |

## 权限清单（docx 图片链路）

- `docx:document` — 建文档 / 转 blocks / 插块
- `drive:drive` — `drive/v1/medias/upload_all`（meta 读取）
- `docs:document.media:upload` — 图片块媒体上传（**易漏，必须单独申请并发布**）
- `im:resource:upload` 与 Docx 图片无关（消息图片才用）

## 错误码对照（避免误判）

| 错误码 | 含义 / 排障提示 |
|--------|-----------------|
| `1770001 invalid param` | 参数不合法：最常见的根因是「图片 token 以错误方式写入图片块」或「parent_node 绑定错误」 |
| `1770040` / `1770032` | 无目标文件夹权限（应用只写自建文件夹） |
| `99991672` | 缺 scope，消息含申请链接 |

错误码较笼统，上传接口返回 `code:0` **不代表**图片可用。必须回读文档 blocks 验证。

## 验证：发布后回读 blocks

```python
GET /docx/v1/documents/{document_id}/blocks?page_size=500
```

成功标准：

- `block_type == 27` 的块数量 = 预期图片数；
- 每个块的 `image.token` 非空；
- 宽高为真实图片尺寸（PNG 如 `2400x552`），不是 `100x100`。

## 工程化建议（本次沉淀到 publish 流程）

1. **降级不阻断**：每张图片独立 try/except，失败打印 `⚠️ 图片插入被拒（已跳过）`，正文/表格照常写完。图片失败不是发布失败。
2. **dry-run**：`--to-feishu` 支持先打印计划（章节数、章节→图片映射），不触网。
3. **离线测试**：`capabilities/feishu/tests/test_docx_client.py` 用 fake HTTP 按请求顺序断言三步（空块创建 → `upload_all`（`parent_node`=块 id、`extra.drive_route_token`=文档 id）→ `PATCH replace_image`），再上真实环境。
4. **URL 路由 token**：`extra.drive_route_token` 是文档 id；`parent_node` 是图片块 id。两者别写反。
5. **清理策略**：每轮失败/调试文档按命名规则（`IMG-*` 等）集中删除，最终只留最新稿 + 历史官方稿。

## 成功样例

- `capabilities/feishu/docx/client.py::insert_image`（三步实现）
- 核验：最终发布文档 1043 blocks，其中 6 个 image 块全部 token 非空。