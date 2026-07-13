# MIIT 新产品公示品牌搜索——经验记录

## 目标

从 watchlist (`MIIT/brand_watchlist.yaml`) 中读取品牌列表，自动在第 409 批 MIIT 新产品公示中搜索各品牌的新车申报信息，替代人工逐一手动查询。

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

### 卡点 7：MIIT 详情页的「其它」字段——隐藏参数的风险区

**现象**：某些参数（如驱动电机峰值功率）在 MIIT 详情页没有独立表格行，仅出现在「其它」字段的长文本中。

**MIIT 详情页的表格结构**（Playwright `document.querySelectorAll('table')` 确认）：

| 表格索引 | 内容 | 行数 |
|----------|------|------|
| Table 0 | 基本信息（产品商标/型号/名称/企业+照片） | 4 行 |
| Table 1 | 尺寸参数（外形尺寸/轴距/整备质量/轮胎/**其它**等） | 18 行 |
| Table 2 | 底盘信息 | 2 行 |
| Table 3 | 发动机参数（型号/企业/排量/功率） | 2 行 |
| Table 4 | 意见反馈 | 1 行 |

关键发现：**没有独立的「电机参数」表格**。驱动电机峰值功率（210kW/100kW）仅出现在 Table 1 的「其它」行中，作为一段长文本的第六条：

```
"其它" 字段原文：
...5.驱动电机峰值功率:210kW/100kW,发动机最大净功率为:112kW...
```

**风险**：从「其它」字段正则提取参数时，容易引入非 MIIT 信息（如人为标注"双电机"）。提取/归档时需遵守以下规则：

1. **只提取数值，不添加解释性文字**。从「其它」中提取 `驱动电机峰值功率:210kW/100kW` → 归档为 `210 / 100`，不添加"双电机"等说明
2. **保持单元格式一致**。MIIT 原文为 `210kW/100kW`，归档格式与带独立行的字段对齐（值部分用空格包裹 `/`）
3. **定期验证**：所有从「其它」字段提取的参数，需用 Playwright 打开 MIIT 详情页重新核对，确保无熵增

**验证方法**：
```python
# 用 Playwright 定位所有表格中的电机信息
page.evaluate('''() => {
  const tables = document.querySelectorAll('table');
  for (const t of tables) {
    const rows = t.querySelectorAll('tr');
    for (const r of rows) {
      if (r.textContent.includes('驱动电机')) {
        return Array.from(r.querySelectorAll('th,td'))
          .map(c => c.textContent.trim()).join(' || ');
      }
    }
  }
  return 'NO DEDICATED ROW, check 其它 field';
}''')
```

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

### 管线二：车型详情归档（全自动化）

品牌搜索结果 → 脚本自动抓取详情页 → 提取参数 + 下载照片 → 归档为 `409-品牌/` 文件夹。

#### 2.1 数据流

```
miit_search.py 搜索结果含 detail_url
        ↓
miit_archive_detail.py —──→ 409-品牌/
  ├ requests 抓取详情页 HTML      ├ {model_id}-{产品名称}.md
  ├ 正则解析 6 个 <table>          ├ {model_id}/
  ├ 下载 2~3 张照片                 │   ├ 左-右部照片.jpg
  └ 生成 Markdown 存档              │   ├ 后部照片.jpg
                                    │   └ 选装照片1.jpg
```

#### 2.2 关键改进：detail_url 自动提取

之前 Pipeline 2 需要人工点击车型型号获取详情页 URL，因为搜索结果页的 API 响应返回的是 HTML，UUID 隐藏在 `<a href="...">` 中。现在的解法：在 `miit_search.py` 的 `_parse_table_html()` 中，从第一栏（标题）的 `<a href>` 中直接提取：

```python
url_m = re.search(r'href="([^"]+)"', tds[0])
detail_url = url_m.group(1) if url_m else ""
```

搜索结果行的 `detail_url` 随 JSON 一起存入 `scan_batch_XXX.md`，供 `miit_archive_detail.py` 使用。

#### 2.3 CLI 用法

```bash
# 归档单个品牌
python3 MIIT/miit_archive_detail.py --brand 小鹏

# 归档所有有搜索结果但未归档的品牌
python3 MIIT/miit_archive_detail.py --all-missing

# 预览（不实际执行）
python3 MIIT/miit_archive_detail.py --all-missing --dry-run
```

#### 2.4 归档文件结构

```
409-品牌/
├── {model_id}-{产品名称}.md          # 完整参数文档
└── {model_id}/
    ├── 左-右部照片.jpg
    ├── 后部照片.jpg
    └── 选装照片1.jpg
```

`.md` 文件包含：基本信息 → 尺寸参数 → 动力系统 → 底盘信息 → 车辆照片（含原始 URL 链接）。照片本身 gitignored（大文件），只提交 .md。

#### 2.5 详情页解析

详情页使用 `requests` 直接抓取（无需 Playwright），加 Referer 头绕过 MIIT 反爬。

**表格结构**（共 5 个有效 table）：

| 表格 | 内容 | 布局类型 | 解析方式 |
|------|------|----------|----------|
| Table 0 | 基本信息（商标/型号/企业/地址） | 交错 th/td 对 | 成对提取 |
| Table 1 | 尺寸参数（外形/轴距/质量/轮胎/其它） | 交错 th/td 对 | 成对提取 |
| Table 2 | 底盘信息 | 表头 + 数据行 | th→td 映射 |
| Table 3 | 发动机参数（型号/企业/排量/功率） | 表头 + 数据行 | th→td 映射 |
| Table 4 | 意见反馈 | 跳过 | — |

**布局检测**：脚本自动判断每张 table 的布局类型——如果某行同时包含 `<th>` 和 `<td>` 则为交错型，否则为表头+数据行型。

#### 2.6 卡点

**卡点：照片 URL 在详情页中重复**

详情页每张照片出现两次（`<a href>` 和内部的 `<img src>`）。用 `re.findall(r'查看原图\s*</a>')` 只匹配锚文本为"查看原图"的链接，天然去重。

**卡点：部分车型无选装照片**

特斯拉 Model Y 焕新版只有 2 张照片（无选装照片）。脚本不会报错，归档目录中该文件缺失属于正常情况。

### 管线三：批次附件下载 + 车船税目录解析（doc → JSON/MD）

独立子流程模块。从批次页附件中下载车船税减免目录 doc，解析为结构化 JSON + Markdown。

#### 3.1 批次页定位

`公告批次.md` 记录了每批的「批次页」链接（区别于「公告页」），批次页包含所有附件下载链接：

```
批次页: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_48f1d6ae25084378be76087d47bad09a.html
```

用 Playwright 打开批次页，snapshot 定位附件链接。第409批的附件4为：

```
4.《享受车船税减免优惠的节约能源 使用新能源汽车车型目录》（第八十八批）拟发布的车型清单.doc
↓
/cms_files/filemanager/1226211233/attach/20267/647e5546ee7143e39dbae6936447aef1.doc
```

#### 3.2 Doc 文件下载

**卡点：403 Forbidden**

MIIT 附件直接 `curl` 下载会返回 403。解法：加上 `Referer` 头（指向批次页 URL）：

```bash
curl -L -o 车型清单.doc \
  -H "User-Agent: Mozilla/5.0 ..." \
  -H "Referer: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_48f1d6ae25084378be76087d47bad09a.html" \
  "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/20267/647e5546ee7143e39dbae6936447aef1.doc"
```

#### 3.3 Doc 文本提取

`.doc` 是旧 Word 二进制格式（OLE2），用 macOS 自带的 `textutil` 转为纯文本：

```bash
textutil -convert txt -output 车型清单.txt 车型清单.doc
```

#### 3.4 数据结构分析

`textutil` 输出有以下特征：

| 特征 | 说明 |
|------|------|
| 分隔符 | Word 表格单元格用 `\x07` 分隔 |
| 单行表 | 每个 Word 表格 = 一行文本，header + 所有数据行连在一起 |
| 空单元格 | 连续两个 `\x07` 表示空单元格 |
| 尾部空列 | 每个表格右侧有一列空单元格（Word 导出残余），每行多 1 列 |

结构示意（以插混乘用车的第 13 行（0-indexed）为例）：

```
序号\x07企业名称\x07商标\x07产品型号\x07...\x07备注\x07\x07
1\x07小米汽车科技有限公司\x07小米牌\x07XMA6500KREEVA1\x07...\x07\x07
2\x07\x07\x07XMA6530KREEVA1\x07...\x07\x07
```

每行字段数 = header 字段数 + 1（尾部空列）。空单元格从上一行继承值（Word 的空白合并特性）。

#### 3.5 解析方案

核心逻辑（`parse_车船税.py`）：

1. **定位数据行**：找到所有以"序号"开头的行，按出现顺序匹配到预定 schema
2. **切分单元格**：`line.split('\x07')`，用 `len(schema) + 1` 作为行宽
3. **分组**：连续单元格按行宽分组，忽略尾部空列
4. **继承**：空单元格继承上一行同列的值（Word 表格的合并单元格行为）
5. **建记录**：截取 `row[:len(schema)]`，按 schema 命名映射

不同分类的数据行定位：

```
数据行索引（0-based）  对应分类            Schema 字段数   行宽（+1）
5                     节能乘用车          11              12
7                     天然气轻型商用车     7               8
9                     天然气重型商用车     7               8
11                    汽柴油重型货车      10              11
13                    插电式混合动力乘用车 12              13
14                    纯电动商用车        10              11
15                    插电式混合动力商用车 12              13
16                    燃料电池汽车        10              11
```

#### 3.6 CLI 用法

```bash
python3 MIIT/parse_车船税.py \
  --input 车型清单_第88批车船税.txt \
  --output 车型清单_第88批车船税 \
  --batch "第八十八批" \
  --date "2026-07-10"
```

`--output` 为输出前缀（不含扩展名），自动生成 `.json` + `.md`。

#### 3.7 产出物

| 文件 | 格式 | 用途 |
|------|------|------|
| `车型清单_第88批车船税.doc` | .doc | 原始附件 |
| `车型清单_第88批车船税.txt` | .txt | textutil 中间文本 |
| `车型清单_第88批车船税.json` | JSON | 结构化数据，含按分类/schema/品牌索引 |
| `车型清单_第88批车船税.md` | Markdown | 可阅读文档，概览+品牌索引+全量表格 |

JSON 结构：

```json
{
  "title": "...",
  "batch": "第八十八批",
  "section_order": ["节能乘用车", "插电式混合动力乘用车", ...],
  "sections": {
    "插电式混合动力乘用车": {
      "count": 45,
      "schema": ["序号", "企业名称", "商标", "产品型号", ...],
      "records": [
        { "企业名称": "小米汽车科技有限公司", "产品型号": "XMA6500KREEVA1", ... },
        ...
      ]
    }
  },
  "by_brand": {
    "小米汽车科技有限公司": {
      "插电式混合动力乘用车": [...]
    }
  },
  "stats": { "插电式混合动力乘用车": 45, "total_records": 607, ... },
  "brands": ["小米汽车科技有限公司", ...]
}
```

---

### 管线四：归档车型 HTML 报告生成（JSON + archive → HTML）

独立子流程模块。结合已归档的车型详情（.md + 照片）和管线三产出的车船税 JSON，为每个车型生成自包含 HTML 报告（图片 base64 内嵌）。

#### 4.1 处理流程

1. **加载数据**：遍历归档目录，逐一读取 .md 参数 + 车船税 JSON 补充电池/续航字段
2. **车型识别与分组**：按车船税的「通用名称」（如"小米澎程N70"）归组。同组内的不同产品型号视为同一车型的不同配置变体
3. **差异分析**：逐字段比较各变体，公共值合为单行，差异值分列展示
4. **渲染输出**：每组生成一个 HTML

```
归档目录/                   车船税 JSON
   4 个车型文件夹  ──→   车型识别与合并  ──→   2 个对比 HTML
                           ↓
                  按通用名称分组（澎程N70 / 澎程N90）
```

#### 4.2 前置条件

需要管线三产出的车船税 JSON + 管线二产出的车型归档目录：

```
409-小米/
├── XMA6500KREEVA1/
│   ├── 左-右部照片.jpg
│   ├── 后部照片.jpg
│   └── 选装照片1.jpg
├── XMA6500KREEVA1-多用途乘用车.md
├── ...
车型清单_第88批车船税.json
```

#### 4.3 数据来源映射

| 字段 | 来源 |
|------|------|
| 长/宽/高/轴距 | 归档 .md 的「外形尺寸(mm)」「轴距(mm)」 |
| 申报动力形式 | 归档 .md 的「新能源类型」 |
| 增程器（型号/排量/功率/企业） | 归档 .md 的发动机字段 |
| 驱动电机 | 归档 .md 的「驱动电机峰值功率」 |
| 电池类型 | 归档 .md 的「储能装置种类」 |
| 电芯及电池总成厂商 | 归档 .md 的「电池单体/总成企业」 |
| 电池容量 | 车船税 JSON 的 `动力蓄电池总能量_kWh` |
| 纯电续航（WLTC） | 车船税 JSON 的 `纯电动续驶里程_km` |
| 座位数 | 归档 .md 的「额定载客」 |
| 整备质量 | 车船税 JSON 或归档 .md 的「整备质量」 |
| 照片 | 归档目录下的 jpg（base64 嵌入 HTML） |

#### 4.4 CLI 用法

```bash
python3 MIIT/generate_miit_reports.py \
  --archive-dir 409-小米 \
  --tax-json 车型清单_第88批车船税.json \
  --brand "小米" \
  --output-dir xiaomi_reports \
  --batch "第409批"
```

`--brand` 用于 HTML 标题前缀；`--output-dir` 输出目录自动创建。

#### 4.5 HTML 输出布局

**配色**
- 页面背景：冷灰蓝 `#EFF2F5`（适配车辆银灰照片）
- 卡片标题/强调：品牌蓝 `#174A7C` / 金色 `#D79A36`
- 差异高亮底色：`#FFFCF0`

**图片容器**
```css
.photo { aspect-ratio: 16 / 10; background: #e9eef2; }
.photo img { width: 100%; height: 100%; object-fit: contain; }
```
- 统一宽高比，`contain` 保证车身完整
- 每组只展示 2 张（左-右部 + 后部），取自第一个变体

**参数分组**

| 分组 | 展示形式 | 公共字段 | 差异字段 |
|------|----------|----------|----------|
| **整车尺寸** | 一行内联 | `长: 4960 ｜ 宽: 1998 ｜ 轴距: 2950` | `高: 1765 / 1785`（/ 分隔） |
| **动力与底盘** | 侧边对比表格 | 增程器合并为单行 | 申报动力形式、驱动电机等分列对比 |
| **电池与续航** | 侧边对比表格 | 电池类型、总成合并为单行 | 容量、续航分列对比 |

公共值合为单列，差异值分列显示并标 `diff` 高亮底色。

#### 4.6 卡点

**正则捕获值带 markdown 标记**

.md 文件中的 `| **7, 5**（提供5座/7座两种布局） |` 提取后会带 `**`。解法：用 `re.sub(r'\*\*(.+?)\*\*', r'\1', val)` 清理。

**电机值含中文**

"210 / 100（双电机）" 不能简单拼接 "kW"。解法：纯数字/分数格式才加 "kW" 后缀。

#### 4.7 产出物

```
xiaomi_reports/
├── index.html                       # 索引页（2 个车型组）
├── 小米澎程N70.html                 # 澎程N70：2 款配置对比报告
└── 小米澎程N90.html                 # 澎程N90：2 款配置对比报告
```

## 后续可扩展

- 支持多批次对比（如 408 批 vs 409 批）
- 命中后自动标识新增车型 vs 改款车型
- 差异增量通知（飞书/webhook）
- 车船税解析的 schema 自动推断：从 header 行自动匹配字段，无需硬编码
- 报告生成模板可配置：支持不同的参数清单模板（如商用车 vs 乘用车）
