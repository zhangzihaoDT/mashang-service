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
| 2. 归档 | `python3 MIIT/miit_archive_detail.py --all-missing` | scan 中有 `detail_url` | `409-品牌/*.md` |
| 3. 补充 | `python3 MIIT/parse_车船税.py`（+ 前置 doc 下载/转换） | 批次页附件 `.doc` | `车型清单_第XX批车船税.json` |
| 4. 报告 | `python3 MIIT/generate_category_report.py --all` | 归档目录 + 车船税 JSON | `miit_category_reports/` |

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

### 配置与数据

| 文件 | 用途 |
|------|------|
| `brand_watchlist.yaml` | 关注品牌清单，按分类分组 |
| `公告批次.md` | 批次索引，记录每批的公告页/简报/归档 |
| `车型清单_第88批车船税.json` | 车船税结构化数据，含通用名称/电池容量/续航 |
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
| `scan_batch_409.md` | Markdown (含 JSON 块) | 搜索结果快照，可重放 |
| `report_batch_409.html` | HTML | 品牌搜索简报，按分类分组 |

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

---

## 管线二：车型详情归档

从搜索结果的 `detail_url` 自动抓取详情页，提取参数和照片，归档为 `409-品牌/`。

```bash
# 归档单个品牌
python3 MIIT/miit_archive_detail.py --brand 小鹏

# 归档所有未归档品牌
python3 MIIT/miit_archive_detail.py --all-missing

# 预览
python3 MIIT/miit_archive_detail.py --all-missing --dry-run
```

### 归档目录结构

```
409-品牌/
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
miit_archive_detail.py —──→ 409-品牌/
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

### 卡点

**照片 URL 重复**：每张照片在 HTML 中出现两次（`<a href>` + 内部 `<img src>`），通过匹配 `查看原图` 锚文本去重。

**部分车型缺选装照片**：如特斯拉 Model Y 焕新版只有 2 张照片，归档中缺少 `选装照片1.jpg` 属正常。

**限流**：每款车型间 `time.sleep(1)`。

---

## 管线三：车船税目录解析

从批次页附件下载车船税减免目录 `.doc`，解析为结构化 JSON + Markdown。

```bash
# 下载附件
curl -L -o 车型清单.doc \
  -H "User-Agent: ..." \
  -H "Referer: https://www.miit.gov.cn/jgsj/zbys/qcgy/art/2026/art_xxx.html" \
  "https://www.miit.gov.cn/cms_files/filemanager/.../xxx.doc"

# 转纯文本
textutil -convert txt -output 车型清单.txt 车型清单.doc

# 解析
python3 MIIT/parse_车船税.py \
  --input 车型清单_第88批车船税.txt \
  --output 车型清单_第88批车船税 \
  --batch "第八十八批" \
  --date "2026-07-10"
```

### Doc 解析要点

- `.doc` 是 OLE2 二进制格式，用 macOS `textutil` 转纯文本
- Word 表格单元格用 `\x07` 分隔，每行是一个表格
- 空单元格从上一行继承值（Word 合并单元格行为）
- 不同分类的数据行索引不同（插混乘用车在第 13 行，纯电商用车在第 14 行等）

### 产出物

| 文件 | 用途 |
|------|------|
| `车型清单_第88批车船税.json` | 结构化数据，含按分类/schema/品牌索引 |
| `车型清单_第88批车船税.md` | 可阅读文档 |

### 关键字段映射

通用名称、电池容量（`动力蓄电池总能量_kWh`）、纯电续航（`纯电动续驶里程_km`）、整备质量（`整车整备质量_kg`）等字段供管线四使用。

---

## 管线四：分类车型对比报告

结合管线二的归档数据 + 管线三的车船税数据，按 `brand_watchlist.yaml` 的分类生成多品牌车型对比 HTML。

```bash
# 生成单个分类
python3 MIIT/generate_category_report.py --category 一线新能源

# 生成全部分类 + index
python3 MIIT/generate_category_report.py --all
```

### 报告结构

```
miit_category_reports/
├── index.html              ← 4 个分类导航
├── 一线新能源.html          ← 小米/理想/小鹏/特斯拉
├── 二线新能源.html          ← 岚图/腾势/魏牌
├── 华为五界三境.html        ← 问界/享界/智界/启境
└── 硬派方盒子.html          ← 爱咖/猛士/方程豹
```

### 每个分类页面包含

- 顶部品牌导航锚点
- 每个品牌一个区块，含车型组卡片
- 每个车型组：2 张内嵌照片 + 整车尺寸内联 + 动力对比表 + 电池续航对比表

### 车型合并规则

通过 `group_models()` 将同一车型的不同配置变体合并到一个卡片中：

1. 优先使用车船税 `通用名称`（如"小米澎程N70"）
2. 纯电/插混同 base ID 的共享通用名称（如岚图梦想家 BEV+PHEV 合并）
3. 逗号分隔的多名称取第一个（如 "V25,V25S" → "V25"）
4. 最终 fallback 到型号 base ID

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
| 详情页/照片抓取 | 1s（脚本内 `time.sleep(1)`） |
| 附件下载 | 建议 1s+ |

### 数据格式

- 搜索 API 返回 JSON，`data.html` 为 HTML 片段
- 详情页为静态 HTML，含 5 个有效 `<table>`
- 表格布局分两种：交错 th/td 对 / 表头+数据行
- 照片链接为 `/cms_files/filemanager/datainfo/cpgs/{hash}@{size}.jpg`

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

---

## 后续可扩展

- 多批次对比（408 vs 409）
- 新增车型 vs 改款车型自动标识
- 差异增量通知（飞书/webhook）
- 车船税 schema 自动推断
- 报告模板可配置（商用车 vs 乘用车）
