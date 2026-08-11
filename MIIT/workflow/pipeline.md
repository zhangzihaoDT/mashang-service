# MIIT Gov Proposed Vehicle Intelligence Pipeline

工信部拟公告新车情报管线：发现拟公告 → 找到关注车型 → 归档车型事实 → 结构化参数 → 补充监管附件 → 生成分析数据与报告。

```
MIIT.gov.cn
   ↓
P1 品牌/车型搜索（01_scan_batch + miit_gov_search）
   ↓  data/search_results/scan_batch_{batch}.md + reports/batch_{batch}/scan_report.html
P2 车型详情归档（02_archive_vehicle_details）
   ↓  data/vehicle_details/ + data/vehicle_photos/ + data/raw_html/ + data/fetch_status/
P3 车船税解析（03_parse_vehicle_tax）
   ↓  data/vehicle_tax/车型清单_第XX批车船税.json
P4 参数宽表（04_build_wide_table）
   ↓  data/wide_tables/wide_table_{batch}.csv
P5 报告（05_generate_brand_report / 06_generate_category_report）
   ↓  reports/batch_{batch}/
```

## 5 类资产（顶层认知入口）

| 目录 | 是什么 | 阅读目的 |
|------|--------|----------|
| `reports/` | ① 最终给人看的产出 | 想知道"已经得出了什么结果" |
| `data/` | ② 获取的数据 + 加工中间数据 | 想看原始/中间数据 |
| `scripts/` | ③ 所有可执行脚本（平铺，按管线顺序编号） | 想运行 |
| `runs/` | ④ 每轮运行记录 / 经验沉淀 | 想知道上一批踩了什么坑 |
| `workflow/` | ⑤ 规则、规划、配置、命令 | 想知道怎么用、为什么存在 |

```
MIIT/
├── README.md
├── Makefile
├── reports/           ① 最终报告（batch_409/ batch_410/）
├── data/              ② 事实数据（按内容命名：search_results / vehicle_details / vehicle_photos / raw_html / vehicle_tax / vehicle_parameters / wide_tables / fetch_status）
├── scripts/           ③ 执行脚本（01~06 按管线编号平铺 + miit_gov_search / miit_paths / report_common / tests）
├── runs/              ④ 运行记录（batch_409.md batch_410.md）
└── workflow/          ⑤ 规则与配置（pipeline.md commands.md batches.yaml brand_watchlist.yaml model_name_map.json schemas/ docs/）
```

## 脚本一览（scripts/ 平铺）

| 脚本 | 管线 | 说明 |
|------|------|------|
| `01_scan_batch.py` | P1 | 品牌搜索 + 简报（scan 快照 + scan_report.html） |
| `02_archive_vehicle_details.py` | P2 | 车型详情归档（可恢复：失败分类 + checkpoint + retry） |
| `03_parse_vehicle_tax.py` | P3 | 车船税 doc/txt → json/md |
| `04_build_wide_table.py` | P4 | 参数宽表 csv/md |
| `05_generate_brand_report.py` | P5 | 单品牌车型对比 HTML |
| `06_generate_category_report.py` | P5 | 按分类多品牌对比 HTML |
| `miit_gov_search.py` | sources | MIIT 搜索底层（HTTP/反爬/API），供 01 调用 |
| `miit_paths.py` | utils | 统一路径/批次配置入口（唯一 I/O 基座） |
| `report_common.py` | utils | P5 公共逻辑（参数提取/车型分组/对比渲染），05/06 共用 |

## 车型身份（canonical key）

**`vehicle_record_id = "{batch_no}:{model_code}"`** —— 不假设 `model_code` 全局唯一。
同一型号未来可能在不同批次再次申报（参数变更/扩展/重新申报），必须用批次号区分版本，
避免历史数据被覆盖。对应文件名：
`data/vehicle_details/{batch}_{model_code}-{产品名}.md`、`data/vehicle_photos/{batch}_{model_code}/`、`data/raw_html/{batch}_{model_code}.html`。

## data/ 二级目录（按内容命名）

| 目录 | 内容 | 对应管线 |
|------|------|----------|
| `search_results/` | P1 品牌/车型搜索结果（scan 快照，可重放） | P1 |
| `vehicle_details/` | P2 车型完整参数归档（{batch}_{型号}-{产品名}.md） | P2 |
| `vehicle_photos/` | P2 公告照片（{batch}_{型号}/ 下） | P2 |
| `raw_html/` | 原始详情页缓存（{batch}_{型号}.html） | P2 |
| `vehicle_tax/` | 车船税 doc/txt/json/md | P3 |
| `vehicle_parameters/` | 结构化车型参数（canonical 目标层，暂未产出） | P2/P3→canonical |
| `wide_tables/` | P4 参数宽表 csv/md | P4 |
| `fetch_status/` | checkpoint / 抓取状态 | P2 |

## 批次处理流程

| 步骤 | 命令 | 前置条件 | 产出 |
|------|------|----------|------|
| 0. 登记批次 | 编辑 `workflow/batches.yaml` | 公告页发布 | page_id / index / 车船税批次 / 文件名 |
| 1. 搜索 | `python3 MIIT/scripts/01_scan_batch.py --batch 410` | `batches.yaml` + `brand_watchlist.yaml` | `data/search_results/scan_batch_410.md` + `reports/batch_410/scan_report.html` |
| 2. 归档 | `python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --all-missing` | scan 中有 `detail_url` | `data/vehicle_details/*.md` + `data/vehicle_photos/` |
| 3. 补充 | `python3 MIIT/scripts/03_parse_vehicle_tax.py`（+ 前置 doc 下载/转换） | 批次页附件 `.doc` | `data/vehicle_tax/车型清单_第89批车船税.json` |
| 4. 宽表 | `python3 MIIT/scripts/04_build_wide_table.py --batch 410` | 归档目录 + 车船税 JSON | `data/wide_tables/wide_table_410.csv` |
| 5. 报告 | `python3 MIIT/scripts/06_generate_category_report.py --batch 410 --all --output-dir batch_410/category_report` | 归档目录 + 车船税 JSON | `reports/batch_410/category_report/` |

> Step 1 和 Step 2 可跨越执行——搜索后先用 `--brand` 归档特定品牌，不需要等全量搜索完毕。Step 3 依赖批次附件发布（通常比公告晚 3-5 天），可以滞后执行；报告在 Step 3 之前可生成，但不含电池容量/续航/通用名称等车船税字段。

> **批次配置唯一来源是 `workflow/batches.yaml`**（页面 page_id / index、公示与归档日期、车船税批次、scan/tax 文件名），
> 脚本通过 `miit_paths.get_batch_config(batch)` 读取，不再各自写死。新批次只需在 `batches.yaml` 登记一行。

## 管线 P1：品牌搜索 + 简报

```bash
python3 MIIT/scripts/01_scan_batch.py --batch 410               # 搜索 + 生成简报 + 保存扫描
python3 MIIT/scripts/01_scan_batch.py --from-scan               # 从已有扫描 MD 生成简报（跳过搜索）
python3 MIIT/scripts/01_scan_batch.py --open                    # 生成后自动打开浏览器
```

### 产出物

| 文件 | 格式 | 说明 |
|------|------|------|
| `data/search_results/scan_batch_410.md` | Markdown (含 JSON 块) | 搜索结果快照，可重放 |
| `reports/batch_410/scan_report.html` | HTML | 品牌搜索简报，按分类分组 |

### 关键细节

- 搜索 API：`/api-gateway/jpaas-publish-server/front/page/build/unit`（miit_gov_search.py）
- 参数通过 `paramJson` 传递，需紧凑 JSON 序列化（`separators=(",", ":")`）
- 需设置 Referer / X-Requested-With / User-Agent 三头，否则 403
- 响应 `data.html` 为 HTML 片段，用正则从 `<td>` 提取字段
- `detail_url` 从第一栏 `<a href>` 中提取
- 批次 pageId / iframe index 登记在 `workflow/batches.yaml`

## 管线 P2：车型详情归档

```bash
python3 MIIT/scripts/02_archive_vehicle_details.py --brand 小鹏 --batch 410
python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --all-missing
python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --all-missing --dry-run
python3 MIIT/scripts/02_archive_vehicle_details.py --batch 410 --retry-failed
```

### 归档产出

```
data/vehicle_details/{batch}_{型号}-{产品名}.md   ← 完整参数文档（身份 = batch:型号）
data/vehicle_photos/{batch}_{型号}/              ← 左-右部照片 / 后部照片 / 选装照片1
data/raw_html/{batch}_{型号}.html                ← 原始详情页缓存（失败恢复解析用）
data/fetch_status/fetch_status_{batch}.json ← checkpoint
```

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

#### 4. checkpoint / resume

- 每款车型状态写入 `data/fetch_status/fetch_status_{batch}.json`：
  ```json
  {"FZ7000BEVB05L": {"status": "TRANSIENT_ERROR", "attempts": 3,
    "last_error": "Read timed out", "last_success": "2026-08-06",
    "data_status": "STALE", "action": "deferred_retry"}}
  ```
- `--retry-failed`：只补抓 `TRANSIENT_ERROR / BLOCKED` 车型
- Ctrl-C 中断也会落盘，可用 `--retry-failed` 继续
- `data_status`: `FRESH`（本次成功）/ `STALE`（历史成功+本次失败）/ `MISSING`

#### 5. 不污染正式数据（保鲜原则）

- `vehicle_details/*.md` 只在解析成功后写入；失败不删除旧数据
- 原始页面缓存到 `data/raw_html/`，网络失败时可从缓存恢复解析（`--no-cache` 关闭）
- 失败时输出 `data_status=STALE + last_success`，标记 freshness

#### 6. 汇总日志

末尾输出：车型数 / 成功 / 暂时失败 / 明确不存在 / 被拦截 / 解析失败 / coverage / retry queue，并按品牌分组列出失败明细（`⚠ MIIT_TIMEOUT / attempts / last_success / action`），一眼判断是整体站点故障还是个别车型问题。

### 详情页表格结构

| 表格 | 内容 | 布局 | 解析方式 |
|------|------|------|----------|
| Table 0 | 基本信息（商标/型号/企业/地址） | 交错 th/td 对 | 成对提取 |
| Table 1 | 尺寸参数（外形/轴距/质量/轮胎/其它） | 交错 th/td 对 | 成对提取 |
| Table 2 | 底盘信息 | 表头 + 数据行 | th→td 映射 |
| Table 3 | 发动机参数（型号/企业/排量/功率） | 表头 + 数据行 | th→td 映射 |
| Table 4 | 意见反馈 | — | 跳过 |

注：纯电车型的 Table 3 实际描述驱动电机，`功率(kw)` 字段映射为 `驱动电机峰值功率`。

### 卡点

**照片 URL 重复**：每张照片在 HTML 中出现两次（`<a href>` + 内部 `<img src>`），通过匹配 `查看原图` 锚文本去重。

**部分车型缺选装照片**：如特斯拉 Model Y 焕新版只有 2 张照片，归档中缺少 `选装照片1.jpg` 属正常。

**`--all-missing` 判定**：按车型 `.md` 是否存在判定（`data/vehicle_details/`）。

## 管线 P3：车船税目录解析

```bash
# 下载附件（批次公示页第4个附件：车船税第XX批车型清单）
curl -L -o 车型清单.doc -H "User-Agent: ..." -H "Referer: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_xxx.html" "https://www.miit.gov.cn/cms_files/filemanager/.../xxx.doc"
# 转纯文本
textutil -convert txt -output 车型清单.txt 车型清单.doc
# 解析（相对 --output 落在 data/vehicle_tax/ 下）
python3 MIIT/scripts/03_parse_vehicle_tax.py \
  --input data/vehicle_tax/车型清单_第89批车船税.txt \
  --output 车型清单_第89批车船税 --batch "第八十九批" --date "2026-08-07"
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
| `data/vehicle_tax/车型清单_第89批车船税.json` | 结构化数据，含按分类/schema/品牌索引 |
| `data/vehicle_tax/车型清单_第89批车船税.md` | 可阅读文档 |

### 关键字段映射

通用名称、电池容量（`动力蓄电池总能量_kWh`）、纯电续航（`纯电动续驶里程_km`）、整备质量（`整车整备质量_kg`）等字段供 P4 / P5 使用。

## 管线 P4：参数宽表

```bash
python3 MIIT/scripts/04_build_wide_table.py --batch 410   # → data/wide_tables/wide_table_410.{csv,md}
python3 MIIT/scripts/04_build_wide_table.py --batch 410 --output-dir 自定义目录
```

- 输出：`data/wide_tables/wide_table_{batch}.csv` + `.md`（含衍生指标汇总、供应商覆盖结构、垂直整合分类）
- 新批次只需在 `workflow/batches.yaml` 登记 scan / 车船税文件名
- 字段口径与衍生指标说明见 `data/wide_tables/README.md`

## 管线 P5：报告

### 单品牌车型对比（05）

```bash
python3 MIIT/scripts/05_generate_brand_report.py \
  --batch 409 --brand 小米 \
  --output-dir batch_409/brand_report \
  --batch-label "第409批"
```

### 分类车型对比（06）

```bash
python3 MIIT/scripts/06_generate_category_report.py --batch 410 --category 一线新能源
python3 MIIT/scripts/06_generate_category_report.py --batch 410 --all --output-dir batch_410/category_report
```

> 相对路径的 `--tax-json` / `--output-dir` 自动落在 `data/vehicle_tax` / `reports` 下。

### 分类报告结构

```
reports/batch_410/category_report/
├── index.html              ← 4 个分类导航
├── 一线新能源.html          ← 零跑
├── 二线新能源.html          ← 领克/魏牌
├── 华为五界三境.html        ← 问界/智界
└── 硬派方盒子.html          ← 爱咖/猛士
```

### 车型合并规则

通过 `group_models()` 将同一车型的不同配置变体合并到一个卡片中，**名称优先级**：

1. 车船税 `通用名称`（如"问界M8"、"猛士X700"）
2. `model_name_map.json` 本地映射（车船税缺失车型的命名补充）
3. 纯电/插混同 base ID 的共享通用名称
4. 逗号分隔的多名称取第一个（如 "V25,V25S" → "V25"）
5. 最终 fallback 到型号 base ID

### 车型名称映射（workflow/model_name_map.json）

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

### 参数提取（report_common.extract_all_params）

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

## 统一配置（workflow/batches.yaml）

脚本只从 `batches.yaml` 读取批次信息，消灭"脚本 A 写一次 batch 信息 / 脚本 B 又写一次 / 文件名再隐含一次"：

```yaml
409:
  notice_date: 2026-07-07
  archive_date: 2026-07-13
  page_id: 49d24aca2b7f42e599691da4cc329220
  index: xcpgs409dwdwe233
  vehicle_tax_batch: 88
  scan_file: scan_batch_409.md
  tax_file: 车型清单_第88批车船税.json
```

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

## 后续可扩展

- 多批次对比（409 vs 410）
- 新增车型 vs 改款车型自动标识
- 差异增量通知（飞书/webhook）
- 车船税 schema 自动推断
- 报告模板可配置（商用车 vs 乘用车）
- 纯电车型容量/续航：接入减免车辆购置税的新能源汽车车型目录
- `model_name_map.json` 自动更新（公示后跟踪媒体报道自动补充命名）
- 统一 Dataset：product_master / vehicle_parameter → `data/vehicle_parameters/`
- 自动发现 pageId；接入 EIDC 双源（未来 `data/eidc/`）
