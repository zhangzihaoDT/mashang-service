# MIIT 公告数据处理管线

## 总览

处理新批次（410、411...）的标准流程分 4 步：

```
Step 1: 搜索 —— 确定 watchlist 中哪些品牌有新车
         miit_report.py → scan_batch_XXX.md + report_batch_XXX.html

Step 2: 归档 —— 获取每款车型的 detail 信息（参数 + 照片）
         miit_archive_detail.py → 409-品牌/{model_id}-{产品名称}.md

Step 3: 补充 —— 结合车船税减免 doc 获取电池容量/续航/通用名称
         parse_车船税.py → 车型清单_第XXX批车船税.json

Step 4: 报告 —— 将信息加工为分类对比 HTML
         generate_category_report.py → miit_category_reports/{分类}.html
```

### 批次处理 checklist

| 步骤 | 命令 | 前置条件 | 产出 |
|------|------|----------|------|
| 1. 搜索 | `python3 MIIT/miit_report.py --batch 410` | `brand_watchlist.yaml` | `scan_batch_410.md` + `report_batch_410.html` |
| 2. 归档 | `python3 MIIT/miit_archive_detail.py --batch 410 --all-missing` | scan 中有 `detail_url` | `410-品牌/*.md` |
| 3. 补充 | `python3 MIIT/parse_车船税.py`（+ 前置 doc 下载/转换） | 批次页附件 `.doc` | `车型清单_第89批车船税.json` |
| 4. 报告 | `python3 MIIT/generate_category_report.py --batch 410 --all --output-dir miit_category_reports_410` | 归档目录 + 车船税 JSON | `miit_category_reports_410/` |
| 4b. 参数宽表 | `python3 MIIT/409-Parameter/wide_table.py --batch 410` | 归档目录 + 车船税 JSON | `MIIT/410-Parameter/` |

> 注：Step 1 和 Step 2 可跨越执行——搜索后先用 `--brand` 归档特定品牌，不需要等全量搜索完毕。Step 3 依赖批次附件发布（通常比公告晚 3-5 天），可以滞后执行；报告在 Step 3 之前可生成，但不含电池容量/续航/通用名称等车船税字段。

## 文件索引

### 核心脚本

| 脚本 | 用途 | 管线 |
|------|------|------|
| `miit_search.py` | MIIT API 搜索，按 watchlist 扫描品牌 | 一 |
| `miit_report.py` | 调用 miit_search.py，生成简报 HTML + scan MD | 一 |
| `miit_archive_detail.py` | 抓取详情页，提取参数，下载照片，归档 | 二 |
| `parse_车船税.py` | 解析车船税 doc → JSON/MD | 三 |
| `generate_miit_reports.py` | 单品牌车型对比 HTML（旧 Pipeline 4） | 四 |
| `generate_category_report.py` | 按分类生成多品牌车型对比 HTML | 四 |
| `409-Parameter/wide_table.py` | 参数宽表生成（支持 `--batch` 跨批次复用） | 4b |

### 配置与数据

| 文件 | 用途 |
|------|------|
| `brand_watchlist.yaml` | 关注品牌清单，按分类分组 |
| `公告批次.md` | 批次索引，记录每批的公告页/简报/归档 |
| `车型清单_第89批车船税.json` | 车船税结构化数据，含通用名称/电池容量/续航 |
| `model_name_map.json` | 车型通用名称映射（车船税缺失车型的命名补充） |
| `scan_batch_XXX.md` | 品牌扫描快照（管线一产物，可重放） |

---

## 管线一：品牌搜索 + 简报

从 watchlist 读取品牌，搜索 MIIT API，生成搜索快照和 HTML 简报。

```bash
python3 MIIT/miit_report.py                          # 搜索 + 生成简报 + 保存扫描
python3 MIIT/miit_report.py --batch 410               # 指定其他批次
python3 MIIT/miit_report.py --from-scan               # 从已有扫描 MD 生成简报（跳过搜索）
python3 MIIT/miit_report.py --open                    # 生成后自动打开浏览器
```

### 产出物

| 文件 | 格式 | 说明 |
|------|------|------|
| `scan_batch_410.md` | Markdown (含 JSON 块) | 搜索结果快照，可重放 |
| `report_batch_410.html` | HTML | 品牌搜索简报，按分类分组 |

### 数据流

```
brand_watchlist.yaml → miit_search.py → MIIT API
                     ↓
              scan_batch_XXX.md ← miit_report.py
                     ↓
              report_batch_XXX.html
```

### 关键细节

- 搜索 API：`/api-gateway/jpaas-publish-server/front/page/build/unit`
- 参数通过 `paramJson` 传递，需紧凑 JSON 序列化（`separators=(",", ":")`）
- 需设置 Referer / X-Requested-With / User-Agent 三头，否则 403
- 响应 `data.html` 为 HTML 片段，用正则从 `<td>` 提取字段
- `detail_url` 从第一栏 `<a href>` 中提取
- **批次配置**：每个公告批次有独立 `pageId` / iframe index，需在 `miit_search.py:BATCH_CONFIG` 登记（409/410 已登记）

---

## 管线二：车型详情归档

从搜索结果的 `detail_url` 自动抓取详情页，提取参数和照片，归档为 `{batch}-品牌/`。

```bash
# 归档单个品牌
python3 MIIT/miit_archive_detail.py --brand 小鹏 --batch 410

# 归档所有有搜索结果但未归档品牌（按车型 .md 是否存在判定）
python3 MIIT/miit_archive_detail.py --batch 410 --all-missing

# 预览
python3 MIIT/miit_archive_detail.py --batch 410 --all-missing --dry-run

# 只补抓之前失败/被拦截的车型（checkpoint resume）
python3 MIIT/miit_archive_detail.py --batch 410 --retry-failed
```

### 归档目录结构

```
410-品牌/
├── {model_id}-{产品名称}.md          # 完整参数文档
└── {model_id}/
    ├── 左-右部照片.jpg
    ├── 后部照片.jpg
    └── 选装照片1.jpg
```

### 数据流

```
miit_search.py 搜索结果含 detail_url
        ↓
miit_archive_detail.py —──→ {batch}-品牌/
  ├ requests 抓取详情页 HTML      ├ {model_id}-{产品名称}.md
  ├ 正则解析 <table>               ├ {model_id}/
  └ 下载 2~3 张照片                 │   ├ 左-右部照片.jpg
                                    │   ├ 后部照片.jpg
                                    │   └ 选装照片1.jpg
```

### 详情页表格结构

| 表格 | 内容 | 布局 | 解析方式 |
|------|------|------|----------|
| Table 0 | 基本信息（商标/型号/企业/地址） | 交错 th/td 对 | 成对提取 |
| Table 1 | 尺寸参数（外形/轴距/质量/轮胎/其它） | 交错 th/td 对 | 成对提取 |
| Table 2 | 底盘信息 | 表头 + 数据行 | th→td 映射 |
| Table 3 | 发动机参数（型号/企业/排量/功率） | 表头 + 数据行 | th→td 映射 |
| Table 4 | 意见反馈 | — | 跳过 |

注：纯电车型的 Table 3 实际描述驱动电机，`功率(kw)` 字段映射为 `驱动电机峰值功率`。

### 失败处理模型（410 批重构核心）

**原则：抓取任务不追求 single-run perfection，而追求 pipeline reliability。** 每次尽可能推进数据状态，失败可识别、可恢复、可补抓，最终数据逐渐达到完整。

#### 1. 失败分类（多状态，不再二元成功/失败）

| 状态 | 含义 | 处理 |
|------|------|------|
| `SUCCESS` | 成功拿到数据 | 写入归档 |
| `NOT_FOUND` | 明确确认页面/车型不存在（404） | 记录，不再重试 |
| `TRANSIENT_ERROR` | timeout / 502/503 / connection reset | 有限重试，耗尽后进 retry 队列 |
| `BLOCKED` | 403 / 429 / 验证码 / 风控 | 记录，需人工介入 |
| `PARSE_ERROR` | 页面拿到但结构解析失败 | 记录，保留 raw 供排查 |
| `SKIPPED` | 无 detail_url 等数据问题 | 跳过 |

> 关键：`Read timed out` 归入 `TRANSIENT_ERROR` 而非 `FAILED`，这是整个恢复系统能正确工作的前提。

#### 2. 瞬态失败有限重试（不拖死整批）

- `max_retries=3`（`--retries` 可调）
- `backoff = 2 ** attempt + random_jitter`（约 2s → 4s → 8s + 抖动）
- 重试耗尽即记录 `deferred_retry` 跳过，继续下一款——**快速失败、跳过、整批推进**

#### 3. 网络参数（政府站点保守设置）

- `timeout=(10, 60)`：connect timeout 10s / read timeout 60s（`Read timed out` 说明连接已建立，只是响应慢，需调大 read）
- 请求间隔随机 `0.8~1.5s`，串行抓取，**不做高并发**（政府站点不适合程序化高频访问）
- `--retries` 可覆盖；403/429 或页面含"安全验证/验证码"识别为 BLOCKED

#### 4. checkpoint / resume（一次性脚本 → 可恢复数据任务）

- 每款车型状态写入 `fetch_status_{batch}.json`：
  ```json
  {"FZ7000BEVB05L": {"status": "TRANSIENT_ERROR", "attempts": 3,
    "last_error": "Read timed out", "last_success": "2026-08-06",
    "data_status": "STALE", "action": "deferred_retry"}}
  ```
- `--retry-failed`：只补抓 `TRANSIENT_ERROR / BLOCKED` 车型
- Ctrl-C 中断也会落盘，可用 `--retry-failed` 继续
- `data_status`: `FRESH`（本次成功）/ `STALE`（历史成功+本次失败）/ `MISSING`

#### 5. 不污染正式数据（保鲜原则）

- `.md` 只在解析成功后写入；失败不删除旧数据
- 原始页面缓存到 `MIIT/raw/{batch}/{brand}/`，网络失败时可从缓存恢复解析（`--no-cache` 关闭）
- 失败时输出 `data_status=STALE + last_success`，标记 freshness

#### 6. 汇总日志

末尾输出：车型数 / 成功 / 暂时失败 / 明确不存在 / 被拦截 / 解析失败 / coverage / retry queue，并按品牌分组列出失败明细（`⚠ MIIT_TIMEOUT / attempts / last_success / action`），一眼判断是整体站点故障还是个别车型问题。

### 卡点

**照片 URL 重复**：每张照片在 HTML 中出现两次（`<a href>` + 内部 `<img src>`），通过匹配 `查看原图` 锚文本去重。

**部分车型缺选装照片**：如特斯拉 Model Y 焕新版只有 2 张照片，归档中缺少 `选装照片1.jpg` 属正常。

**`--all-missing` 判定**：按车型 `.md` 是否存在判定（而非品牌目录是否已建），避免目录已建但车型未归档时空转。

---

## 管线三：车船税目录解析

从批次页附件下载车船税减免目录 `.doc`，解析为结构化 JSON + Markdown。

```bash
# 下载附件（批次公示页第4个附件：车船税第XX批车型清单）
curl -L -o 车型清单.doc \
  -H "User-Agent: ..." \
  -H "Referer: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_xxx.html" \
  "https://www.miit.gov.cn/cms_files/filemanager/.../xxx.doc"

# 转纯文本
textutil -convert txt -output 车型清单.txt 车型清单.doc

# 解析
python3 MIIT/parse_车船税.py \
  --input 车型清单_第89批车船税.txt \
  --output 车型清单_第89批车船税 \
  --batch "第八十九批" \
  --date "2026-08-07"
```

### Doc 解析要点

- `.doc` 是 OLE2 二进制格式，用 macOS `textutil` 转纯文本
- Word 表格单元格用 `\x07` 分隔，每行是一个表格
- 空单元格从上一行继承值（Word 合并单元格行为）

### 分类识别（410 批重构核心）

**不要按位置映射分类，要按表头列签名识别。** 各批次 section 顺序可能不同、也可能缺段（410 批就没有「汽柴油重型货车」段），按位置映射会让后续所有分类错位。

`_detect_section()` 根据数据行表头列（如 `动力蓄电池组总质量` 带"组"=纯电商用车、`通用名称+产品型号+发动机排量(ml)`=插混乘用车、`燃料电池系统额定功率`=燃料电池等）识别所属分类，天然兼容缺段/顺序变化。

### 覆盖范围（重要口径）

车船税目录**只收录申请了减免的车型**，纯电乘用车、燃油车通常不在其中。每批命中率取决于该批申报结构：

- 409 批：17 款 watchlist 车型中插混/增程全命中
- 410 批：17 款中仅 4 款命中（问界M8 增程×2、猛士X700×2），其余 13 款纯电/燃油缺失属正常

缺失车型的电池容量/续航/通用名称可走**减免车辆购置税的新能源汽车车型目录**（另一公告）或 `model_name_map.json` 命名映射补。

### 产出物

| 文件 | 用途 |
|------|------|
| `车型清单_第89批车船税.json` | 结构化数据，含按分类/schema/品牌索引 |
| `车型清单_第89批车船税.md` | 可阅读文档 |

### 关键字段映射

通用名称、电池容量（`动力蓄电池总能量_kWh`）、纯电续航（`纯电动续驶里程_km`）、整备质量（`整车整备质量_kg`）等字段供管线四/4b 使用。

---

## 管线四：分类车型对比报告

结合管线二的归档数据 + 管线三的车船税数据 + `model_name_map.json` 命名映射，按 `brand_watchlist.yaml` 的分类生成多品牌车型对比 HTML。

```bash
# 生成单个分类
python3 MIIT/generate_category_report.py --batch 410 --category 一线新能源

# 生成全部分类 + index
python3 MIIT/generate_category_report.py --batch 410 --all --output-dir miit_category_reports_410
```

> 410 起需传 `--batch`（自动切换归档目录前缀 / 公示日期 / 车船税文件）；409 默认行为不变。输出建议用独立目录（如 `miit_category_reports_410/`）避免覆盖上一批报告。

### 报告结构

```
miit_category_reports_410/
├── index.html              ← 4 个分类导航
├── 一线新能源.html          ← 零跑
├── 二线新能源.html          ← 领克/魏牌
├── 华为五界三境.html        ← 问界/智界
└── 硬派方盒子.html          ← 爱咖/猛士
```

### 每个分类页面包含

- 顶部品牌导航锚点
- 每个品牌一个区块，含车型组卡片
- 每个车型组：2 张内嵌照片 + 整车尺寸内联 + 动力对比表 + 电池续航对比表

### 车型合并规则

通过 `group_models()` 将同一车型的不同配置变体合并到一个卡片中，**名称优先级**：

1. 车船税 `通用名称`（如"问界M8"、"猛士X700"）
2. `model_name_map.json` 本地映射（车船税缺失车型的命名补充）
3. 纯电/插混同 base ID 的共享通用名称
4. 逗号分隔的多名称取第一个（如 "V25,V25S" → "V25"）
5. 最终 fallback 到型号 base ID

### 车型名称映射（`model_name_map.json`）

车船税不含纯电/燃油车型，其市场名称通过公开报道检索沉淀到本地映射表：

```json
{"models": {
  "FZ7000BEVB05K": {"name": "零跑B01", "confidence": "medium", "note": "4490mm 与B01申报吻合"},
  "CC6530DC21HABEV": {"name": "魏牌V9X", "confidence": "high", "note": "5299/2025/3150 与V9X完全吻合"}
}}
```

- 每条含 `name / confidence / note`（尺寸依据、报道来源）
- `confidence`: high=尺寸完全吻合+媒体命名 / medium=尺寸吻合 / low=待确认（兜底写 `{品牌}新车型(今日刚公示,无公开名称)`）
- 命名来源：车家号 / 网易 / 新浪 / 汽车之家 / 腾讯等公开报道，按型号+品牌搜索验证，用尺寸交叉确认

### 参数提取

`extract_all_params()` 从归档 `.md` + 车船税 JSON 中提取参数：

**来源优先级**：`.md` 表格行 > 车船税 JSON > `.md` 的「其它」字段正则解析

| 参数 | 主要来源 | 回退来源 |
|------|----------|----------|
| 长/宽/高/轴距 | `外形尺寸(mm)` | `外形尺寸` |
| 申报动力形式 | `新能源类型` | `燃料种类` |
| 驱动电机 | `驱动电机峰值功率(kW)` | `功率(kw)` |
| 电池类型 | `储能装置种类` | 从「其它」正则提取 |
| 电芯及电池总成 | `电池单体/总成企业` | 从「其它」正则提取 |
| 电池容量/续航 | 车船税 JSON | — |
| 座位数 | `额定载客(人)` | `额定载客（含驾驶员）（座位数）` |
| 整备质量 | `整备质量(kg)` | `整备质量` / 车船税 |

---

## 管线 4b：参数宽表（410 起新增）

从归档 `.md` + 车船税 JSON 生成结构化参数宽表（品牌/型号/电机/电池/供应商/衍生指标），`409-Parameter/wide_table.py` 通过 `--batch` 跨批次复用。

```bash
python3 MIIT/409-Parameter/wide_table.py --batch 410   # → MIIT/410-Parameter/
python3 MIIT/409-Parameter/wide_table.py --batch 410 --output-dir 自定义目录
```

- 输出：`{batch}-Parameter/wide_table.csv` + `wide_table.md`（含衍生指标汇总、供应商覆盖结构、垂直整合分类）
- 新批次只需在 `BATCH_PATHS` 登记 scan / 车船税文件名
- 字段口径与衍生指标说明见 `MIIT/409-Parameter/README.md`

---

## API 技术要点

### 反爬绕过

- 必须设置 `Referer`、`X-Requested-With`、`User-Agent` 三头
- 首次访问需先 GET index.html 做 cookie priming
- JSON 需紧凑序列化（`separators=(",", ":")`）
- 详情页可用 `requests` 直接抓取（加 Referer 即可）

### 频率限制

| 操作 | 间隔 |
|------|------|
| 品牌搜索（API） | 隐式（API 自带） |
| 详情页/照片抓取 | 0.8~1.5s 随机（脚本内） |
| 附件下载 | 建议 1s+ |

### 数据格式

- 搜索 API 返回 JSON，`data.html` 为 HTML 片段
- 详情页为静态 HTML，含 5 个有效 `<table>`
- 表格布局分两种：交错 th/td 对 / 表头+数据行
- 照片链接为 `/cms_files/filemanager/datainfo/cpgs/{hash}@{size}.jpg`
- 批次公示页在 `https://www.miit.gov.cn/jgsj/zbys/qcgy/` 栏目下，附件 4 为车船税 doc

---

## 历史勘探记录

> 以下记录了最初探索 MIIT 页面结构和 API 的过程，供参考。

### 页面结构发现

公告页 (`art_xxx.html`) 只是一个包装壳，真正的数据在一个 iframe 中：
`https://www.miit.gov.cn/datainfo/dljdclscqyjcpgg/xcpgs409dwdwe233/index.html`

### API 发现

通过 Playwright network_requests 定位到搜索请求，核心 API：
`/api-gateway/jpaas-publish-server/front/page/build/unit`

### 已解决的卡点

| 卡点 | 现象 | 解法 |
|------|------|------|
| API 403 | `requests.get()` 返回 403 | 加 Referer/X-Requested-With/UA 头 |
| 紧凑 JSON | 部分搜索字段 403 | `separators=(",", ":")` |
| 列数不对 | 解析结果为空 | 确认 6 列顺序 |
| 重复数据 | 同一品牌通过 CPSB+QYMC 搜出重复 | 按 `cpxh` 去重 |
| JSON 转义 | HTML 中 `\"` | `json.loads()` 还原 |
| 照片 URL 转义 | href 匹配不到 | 先还原 HTML |
| 其它字段 | 电池/电机信息隐藏在长文本中 | 正则提取 |
| Read timed out | 抓详情页超时且脚本卡死 | 失败分类 TRANSIENT_ERROR + 有限重试 + checkpoint，不再拖死整批 |
| 车船税解析错位 | 批次缺某分类段导致后续全错位 | 按表头列签名识别分类，不按位置映射 |
| 纯电/燃油车型无名称 | 车船税目录不含，报告显示空基名 | `model_name_map.json` 命名映射补 |

---

## 后续可扩展

- 多批次对比（409 vs 410）
- 新增车型 vs 改款车型自动标识
- 差异增量通知（飞书/webhook）
- 车船税 schema 自动推断
- 报告模板可配置（商用车 vs 乘用车）
- 纯电车型容量/续航：接入减免车辆购置税的新能源汽车车型目录
- `model_name_map.json` 自动更新（公示后跟踪媒体报道自动补充命名）
