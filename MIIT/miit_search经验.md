# MIIT 新产品公示品牌搜索——经验记录

## 目标

从 watchlist (`priority_brand_watchlist.yaml`) 中读取品牌列表，自动在第 409 批 MIIT 新产品公示中搜索各品牌的新车申报信息，替代人工逐一手动查询。

## 成功路径

### 1. 理解页面结构

公告页 (`art_xxx.html`) 只是一个包装壳，真正的数据在一个 iframe 里：

```
https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/xcpgs409dwdwe233/index.html
```

iframe 内是一个带搜索条件的表格页，包含字段：企业名称、产品商标、产品名称、产品型号。

### 2. 发现 API

用 Playwright 打开页面后，通过 **network_requests** 定位到搜索请求。整个过程约 18 次 Playwright 调用：

| 操作 | 次数 | 用途 |
|------|------|------|
| navigate | 2 | 公告页 → iframe 数据页 |
| snapshot | 4 | 看页面结构、看搜索结果 |
| type / fill_form | 6 | 输入搜索词（含空字符串失败重试） |
| click | 2 | 触发查询 |
| network_requests / network_request | 4 | 定位并确认 API 地址 |

核心发现只依赖前 3 次调用（navigate → snapshot → network_requests），后续的 type/click 是为了验证 API 行为，实际走 API 方式后不再需要。

在 Network 面板观察到搜索操作实际调用的是：

```
POST-like GET 请求
/api-gateway/jpaas-publish-server/front/page/build/unit
```

参数通过 `paramJson` 传递，核心字段：

| 参数 | 含义 |
|------|------|
| PICI | 批次号 |
| QYMC | 企业名称 |
| CPSB | 产品商标 |
| CPMC | 产品名称 |
| CPXH | 产品型号 |

响应是一个 JSON，`data.html` 字段包含渲染后的表格 HTML。

### 3. 解析数据

API 返回的是 HTML 片段而非结构化 JSON，因此需要用正则从 `<tr>/<td>` 中提取字段。表格列顺序为：标题 → 批次 → 企业名称 → 产品商标 → 产品名称 → 产品型号。

## 卡点与克服

### 卡点 1：API 返回 403

**现象**：用 `requests.get()` 直接调用 API 时返回 403 Forbidden。

**原因**：MIIT API 要求携带特定的 HTTP 头，缺少会被拦截。

**解决**：添加三个关键头：

```python
headers = {
    "Referer": "https://www.miit.gov.cn/datainfo/.../index.html",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 ... Chrome/...",
}
```

### 卡点 2：搜索部分字段返回 403

**现象**：用 CPSB（产品商标）搜索某些品牌时出现 403，而 QYMC（企业名称）搜索同一品牌正常。

**原因**：API 对 `paramJson` 的 JSON 序列化格式敏感。浏览器的原始请求使用**不带空格**的紧凑格式：

```json
{"pageNo":1,"loadEnabled":true,"search":"...","pageSize":"20"}
```

而 `json.dumps()` 默认会插入空格：`{"pageNo": 1, "loadEnabled": true, ...}`。MIIT 网关对格式不一致的请求可能返回 403。

**解决**：使用 `separators=(",", ":")` 参数：

```python
json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
```

### 卡点 3：HTML 解析列数不对

**现象**：解析结果全部为空。

**原因**：表格实际有 6 列（标题、批次、企业名称、产品商标、产品名称、产品型号），最初按 4 列解析导致索引错位。

**解决**：确认列顺序后，用 `tds[2]` ~ `tds[5]` 提取正确的字段。

### 卡点 4：多次请求产生重复数据

**现象**：同一品牌通过不同搜索方式（CPSB + QYMC）搜出重复型号。

**解决**：按 `cpxh`（产品型号）做去重。

## 技术要点

- **直接调用 API 比模拟浏览器点击更可靠**——避免了 iframe 跨域、页面渲染延迟等问题
- **紧凑 JSON 序列化**是这类政府网站 API 的常见要求，需要留意
- **Referer 头**不能省略，许多政府 API 依赖它做来源校验
- **API 有频率限制**，连续请求时建议加 0.5s 以上的延迟

## 输出示例

```
品牌: 小米
共 4 条记录 (搜索方式: 产品商标=小米(4条))
  小米汽车科技有限公司 | 小米牌 | 插电式增程混合动力多用途乘用车 | XMA6500KREEVF3
  小米汽车科技有限公司 | 小米牌 | 插电式增程混合动力多用途乘用车 | XMA6500KREEVA1
  ...
```

支持 `--format json` 输出结构化结果，便于下游集成。

## Step 2：车型详情获取

搜索出某个品牌有新车后，下一步是获取每款车型的完整参数和照片，归档为品牌文件夹（如 `409-小米/`、`409-理想/`）。

### 发现详情报文

在搜索结果页**点击车型型号**（如 `LXA6524BEVW02`），浏览器会打开新标签页，URL 格式为：

```
/datainfo/dljdclscqyjcpgg/xcpgs409dwdwe233/art/2026/art_{uuid}.html
```

这就是该车型的**企业申报车型公示详情页**，包含完整的尺寸、动力、选装参数和三张照片（左/右部照、后部照、选装照）。

### 获取详情数据

用 Playwright 打开车型详情页，通过 `page.evaluate('() => document.documentElement.outerHTML')` 获取完整 HTML。

**注意**：Playwright evaluate 返回的是 JSON 序列化后的字符串，所有 `"` 被转义为 `\"`。需要用以下方式还原：

```python
import json
raw = json.loads(f'"{saved_content}"')
# 或者手动替换
raw = saved_content.replace('\\"', '"').replace('\\n', '\n')
```

### 解析参数

详情页 HTML 包含 6 个 `<table>`，分别对应：基本信息、尺寸参数、动力系统等。用正则提取 `<th>/<td>` 配对即可。

### 下载照片

详情页底部有 `class="cppic"` 的容器，内含三组照片链接，每组结构为：

```html
<a href="/cms_files/filemanager/datainfo/cpgs/{hash}.jpg" target="_blank">查看原图</a>
```

照片文件名中的 `@` 后数字即字节长度，可直接拼为完整 URL 下载。注意照片间的顺序对应：左/右部照片、后部照片、选装照片1。

### 文件夹结构

每个车型一个独立文件夹，与 `409-小米/` 保持一致：

```
409-品牌/
├── {model}-{产品名称}.md          # 完整参数文档
├── {model}/
│   ├── 左_右部照片.jpg
│   ├── 后部照片.jpg
│   └── 选装照片1.jpg
```

详情页原始 HTML 是中间产物，提取完即删。

### 卡点 5：保存的 HTML 带 JSON 转义

**现象**：从 Playwright evaluate 保存的 HTML 文件里所有 `"` 都变成了 `\"`，导致正则匹配不到。

**原因**：`browser.evaluate` 的返回值经过 JSON 序列化，引号被转义。

**解决**：读取后用 `json.loads()` 或手动替换还原。判断依据：如果文件内容包含 `\\"`，说明经过了 JSON 转义。

### 卡点 6：照片 URL 在 HTML 中被转义

**现象**：正则 `<a href="..."` 匹配不到任何链接。

**原因**：同上，JSON 转义导致实际文件内容是 `href=\"...\"`。

**解决**：先还原 HTML（见卡点 5），再用标准正则提取。

## 自动化管线

### 管线一：品牌搜索 + 简报

```bash
python3 MIIT/miit_report.py               # 搜索全量品牌 → 生成 HTML 简报
python3 MIIT/miit_report.py --batch 410   # 指定其他批次
python3 MIIT/miit_report.py --open        # 生成后自动用浏览器打开
```

管线包含：

1. `miit_search.py` — 调用 MIIT API 搜索所有 watchlist 品牌，输出 JSON
2. `miit_report.py` — 读取 JSON，自动：
   - 按品牌分组，按能源类型（纯电/增程/插混）归类
   - 生成单文件 HTML 简报（`report_batch_XXX.html`）
   - 更新 `公告批次.md` 索引表（新增批次行）

简报格式：品牌卡片 → 能源类型分组 → 车型表格（企业名称、产品名称、产品型号），顶部统计看板展示总新车数和活跃品牌数。

### 管线二：车型详情归档

品牌搜索结果 → 人工选定目标品牌 → Playwright 打开详情页 → 提取参数 + 下载照片 → 归档为 `409-品牌/` 文件夹。

当前这一步尚未完全自动化（需手动点击车型型号获取详情页 URL），原因：每个车型详情的 UUID 无法从搜索 API 响应中直接推导，需要从页面点击触发。

## 后续可扩展

- 支持多批次对比（如 408 批 vs 409 批）
- 命中后自动标识新增车型 vs 改款车型
- 差异增量通知（飞书/webhook）
- 车型详情归档自动化：从搜索结果 HTML 中提取各车型的详情页 URL，替代人工点击
