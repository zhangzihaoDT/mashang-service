# 飞书云文档抓取经验（docx → Markdown + 原图）

本文档沉淀飞书云文档（wiki / docx / 可下载 docx）完整转存为 Markdown + 原图归档的两条路径与卡点。

## 两条路径

| 路径 | 适用 | 依赖 |
|------|------|------|
| **A. 在线抓取**（client_vars API + 图片端点） | 文档**不可下载**，只能在线浏览 | 浏览器登录态 Cookie |
| **B. docx 直接转换**（`utility_scripts/docx2md.py`） | 文档**可下载**为 .docx（文字+图片已打包） | 无，纯本地（lxml） |

优先判断：**能下载 docx 就先下载**（路径 B），文字与图片已打包，无需登录态与网络；只有不可下载时才走路径 A。

---

## 路径 B：docx 直接转换（推荐）

### 工具

```bash
python mashang_workspace/utility_scripts/docx2md.py \
    "~/Downloads/LS6 M2_T1产品简介Feature Book.docx" \
    -o "mashang_workspace/docs/archive/LS6_M2_T1_FeatureBook.md" \
    --title "LS6 M2/T1 产品简介 Feature Book"
```

- 图片自动抽取到 `<md同名单>_images/`，按出现顺序命名 `img_001.ext`，Markdown 引用同步生成。
- 支持 `--img-dir DIR`、`--prefix img`、`--title`。依赖仅 lxml。
- 已实例：`docs/archive/LS6_M2_T1_FeatureBook.md`（27 张图）。

### docx 导出体例（飞书/Word 导出）关键映射

| OOXML 结构 | 含义 | 转换结果 |
|-----------|------|---------|
| `w:pStyle` = `1` | H1（文档内通常仅 `Change Log` 一处） | `#`，但 `Change Log` 降级为 `##` |
| `w:pStyle` = `2 / 4 / 5` | H2 / H3 / H4 | `##` / `###` / `####` |
| `w:numPr`（段落属性） | 列表项（bullet） | `- ` |
| `<w:tbl>` 单列单行 | callout / 提示框（飞书"引用块"导出形态） | `> blockquote` |
| `<w:tbl>` 多列多行 | 数据表 | pipe table（`gridSpan` 跨列、多段 `<br>`、嵌套表递归） |
| 表格单元格内段落 | 单元格内容 | 多段合并 `<br>`，列表项前置 `- ` |
| `r:embed` → `a:blip` | 图片，`word/_rels/document.xml.rels` 映射 `media/imageN.ext` | `img_{seq:03d}.{ext}` |

### 为什么不用 pandoc

- pandoc 3.6.4 对导出 docx：`-t gfm` 把表格转成 HTML `<table>`（非 pipe table）；`-t markdown` 转成 ASCII 框线表；标题样式名是字面编码 `1/2/4/5`，pandoc 无法按 WCAG 规律正确映射为 `#`。
- 自写 OOXML 解析（`docx2md.py`）可控性高：样式→层级、单格表→blockquote、图片重命名全部按需定制，产物与路径 A 风格一致。

### 适用 / 不适用

- 适用：可下载为 docx 的飞书文档、Word 导出的结构化文档；需要与路径 A 产物风格一致的归档。
- 不适用：不可下载只能在线浏览的文档（走路径 A）；内容含流式嵌入对象（sheet 等只有 token，docx 中无文字内容，需另行处理，见下文卡点 5）。

---

## 路径 A：在线抓取（client_vars API + 图片）

适用于**不可下载**、只能在线浏览的文档。

### 数据源与端点

#### 文档正文（block 数据）

```text
https://{tenant}.feishu.cn/space/api/docx/pages/client_vars
  ?id={doc_id}
  &mode=7
  &limit=500
  &wiki_space_id={wiki_space_id}     # 仅 wiki 容器需要
  &container_type=wiki2.0 | docx2.0  # wiki vs 直链 docx 不同
  &container_id={wiki_token | doc_id}
```

- `{tenant}`：租户域名，即 wiki/docx URL 的主机名（如 `xfmkp6q7le.feishu.cn`）。
- wiki URL：`/wiki/{wiki_token}`，需 `wiki_space_id`，响应容器字段为 `blocks`。
- **docx 直链**：`/docx/{doc_id}`，无需 wiki_space_id，`container_type=docx2.0`，响应容器字段为 `block_map`（另含 `meta_map`）。
- `limit=500` 为单页 block 上限，需配合 `next_cursors` 传 `cursor=` 分页取全。

#### 图片原图下载

```text
https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/v2/cover/{token}/
  ?mount_node_token={block_id}
  &mount_point=docx_image
  &width={原图宽}
  &height={原图高}
  &policy=equal
  &fallback_source=1
```

- `{token}` 与 `{block_id}` 来自 `client_vars` 中 image block 的 `data.image.token` 与 block `id`。
- `width/height` 必须填**原图实际尺寸**（image block 元数据 `data.image.width/height`），否则返回缩略图。
- 全部请求需带登录态 Cookie（浏览器会话上下文提取）。
- 各 block 本身的扩展名与尺寸见 `data.image.mimeType / width / height`。

## 卡点与解决

### wiki / docx 在线抓取通用

| # | 卡点 | 现象 | 解法 |
|---|------|------|------|
| 1 | **虚拟滚动 + 懒加载** | 用 Playwright 滚屏抓 DOM，文本不全且乱序；图片在 DOM 中不存在（未进入视口不渲染） | 放弃 DOM，走 `client_vars` API 取结构化 block 数据 |
| 2 | **分页只取 `next_cursors[0]`** | 只拿到 1000 blocks，root children 553 个 MISSING | DFS 遍历全部 `next_cursors`（不是只取第一个）→ 6504 blocks，0 missing |
| 3 | **block 文本结构特殊** | 文本在 `data.text.initialAttributedTexts.text`，是 dict 而非字符串 | 按 `int(key)` 排序后拼接；bullet/ordered 文本在**自身** `text` 字段而非子节点 |
| 4 | **表格结构特殊** | 单元格走 `columns_id + rows_id + cell_set`，key 为 `{row_id}{col_id}` 拼接 | 解析 `cell_set[].block_id` 展开单元格内容；注意 `merge_info`（合并单元格） |
| 5 | **image block 无 URL** | 图片只有 `token` + 元数据（尺寸/mimeType/name），无 URL 无二进制 | 通过浏览器**网络面板观察前端懒加载实际请求**，得到图片下载端点模板 |
| 6 | **原图下载参数坑** | 省略尺寸或用错 `policy` 会返回 400 或 1280 缩略图 | `width/height` 传原图尺寸 + `policy=equal`，可拿到与元数据 `size` 精确一致的原图 |
| 7 | **内嵌图片漏抓** | 20 张图在 `table_cell` 单元格内、2 张在嵌套于 bullet 下的 `grid` 布局内，文本遍历未覆盖 | 表格图片走 `cell_set` 映射展开；grid 挂在 bullet 的 children 下，遍历需覆盖嵌套子结构 |
| 8 | **Playwright 沙箱禁写盘** | `run_code_unsafe` 中 `require('node:fs')` / `import('node:fs')` 均报错，无法在浏览器进程内落盘 | 改为在浏览器内提取登录态 Cookie header，导出后由外部 Python `requests` 批量下载 |

### docx 直链（docx2.0 容器）特有

| # | 卡点 | 现象 | 解法 |
|---|------|------|------|
| 1 | **容器字段不同** | wiki 用 `blocks`，docx 直链是 `block_map`（+`meta_map`），且无 `wiki_space_id` | `container_type=docx2.0` + `container_id={doc_id}`；读取 `block_map` |
| 2 | **`sheet` 类型块** | 嵌入电子表格 block 只有 `token`，无文字内容（内容存于另一对象） | 渲染为占位标记（如 `> 📊 [嵌入式电子表格]`） |
| 3 | **ordered 块可内嵌 children** | 5 个 ordered 下挂 bullet/sheet/nested ordered/text，文本遍历未递归导致内容缺失 | ordered 渲染后需递归 children（同 bullet/grid）；图片 register 加 block_id 去重防双计数 |
| 4 | **图片可挂在 `text` 块下** | `grid → text → image` 路径，text 渲染没递归就漏图（本实例 27 张中 2 张在此路径） | `text` 分支渲染后递归 children 子块 |

### 细节备注

- 表格单元格内的图片数量不算在页面 document tree 的 children 链上，需走 `cell_set` 查找；grid 挂在 bullet 子节点时，`render_block` 需对 bullet 渲染后再展开其 children。
- 解析后 Markdown 以 `![label](S31L_M0_images/img_NNN.ext)` 引用图片，图片编号（`img_NNN`）与解析脚本中**同一次遍历顺序**一致，保证 引用 ↔ 文件 一一对应。
- 图片占位符 `[图片]` 与真实图片数量不一定相等（S31L 47 个占位 vs 69 张实际图片），以解析后实际登记的 image block 为准。
- 图片登记函数建议加 **block_id 去重**：`block_text()` 与 children 递归可能对同一张图重复登记，去重可保证 manifest/引用 数量稳定。

## 可复用流程

### 路径 B（docx 直转）

1. 下载 / 定位 `.docx` 文件。
2. `python utility_scripts/docx2md.py <input.docx> -o <out.md> [--title 标题]`。
3. 校验：`图片引用数 == 磁盘文件数`，magic bytes 正确（PNG `89504e47…`、JPEG `ffd8ffe0…`），无 `[图片]`/空引用。

### 路径 A（在线抓取）

1. 从 wiki/docx URL 解析租户域名、`{doc_id}` / `{wiki_token}` / `{wiki_space_id}`（按容器类型）。
2. 调用 `client_vars`，按 DFS 遍历 `next_cursors` 取全量 blocks（验证 root children 无 MISSING，递归验证全树 children 无缺失）。
3. 解析 block → Markdown：文本排序拼接、表格 `cell_set` 展开、bullet/ordered 自持文本、callout/grid 嵌套递归、sheet 占位；同时给每个 image block 登记 `token/block_id/宽高/mimeType` 并分配顺序编号。
4. 在浏览器网络面板（或 Playwright 网络请求）中确认图片下载端点模板。
5. 从浏览器会话提取 Cookie header（临时落 `/tmp`，chmod 600），用 Python `requests` 按编号批量下载原图到 `archive/*_images/`。
6. 校验：`参考引用数 == 磁盘文件数`，扩展名/magic bytes 正确（PNG `89504e47…`、JPEG `ffd8ffe0…`），删除临时 Cookie。

## 适用 / 不适用场景

**适用**：

1. 飞书 wiki（`/wiki/…`）或直链 docx（`/docx/…`）文档完整转存为 Markdown + 原图。
2. 需要把在线文档结构化后二次处理（表格、图片、层级）的场景。
3. 已登录飞书、可获取浏览器会话 Cookie 的机器/会话环境（仅路径 A 需要）。
4. **可下载 docx 的场景优先路径 B**——无登录态依赖，纯本地转换。

**不适用**：

1. 未登录飞书、无法获得会话 Cookie，且文档不可下载的环境（路径 A 的 `client_vars` 与图片端点需登录态；路径 B 无此限制）。
2. 需要在浏览器进程内直接落盘（Playwright `run_code_unsafe` 沙箱禁 `fs`）。
3. 文档为嵌入对象（非 docx block 模型）或复杂流程图式画布（白板/boards），需另外的接口；`sheet` 电子表格仅有 token 无文字内容，docx 导出也只含占位。

## 经验教训

- **优先看 API 层而非 DOM**：虚拟滚动页面（飞书、小红书、长列表）DOM 不等于数据源，先抓网络请求找后端接口。
- **分页要遍历全部游标**：异步接口的 `next_cursors` 是分叉列表（如同步网络中的多页并发），只取首元素会静默丢数据，务必 DFS。
- **素材下载看"浏览器实际请求"**：元数据里通常只有 token 没有 URL，跑到前端在真实场景发的请求，才能拿到正确的下载端点与参数。
- **Cookie 安全**：登录凭证只落 `/tmp`、chmod 600、用完即删，绝不进 Git、不提交仓库（仓库已有 `.gitignore` 边界：`dataset/incoming/feishu/` 与 `.local/playwright-mcp/feishu/`）。
- **图片编号与文档顺序解耦策略**：用解析脚本的同一次遍历给图片编号，Markdown 引用与磁盘文件天然对齐，避免"占位数 ≠ 实际图片数"造成的错位。
- **容器类型决定 API 参数**：wiki（`wiki2.0`/`blocks`/需要 `wiki_space_id`）与 docx 直链（`docx2.0`/`block_map`）结构不同，先确认 URL 形态再选参数。
- **register 去重是防御性必须**：`block_text()` 与 children 递归的双路径可能重复登记同一图片，去重后引用/文件数量才稳定。
- **优先验证 docx 是否可下载**：两条路径对比，路径 B 零外部依赖、可本地校验，是默认首选。