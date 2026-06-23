# MIIT 目标品牌端到端 Dry Run Runbook

## 1. 目的

本 Runbook 记录 MIIT 项目从信息获取到业务情报输出的完整链路，供后续批次重复执行参考。

完整链路：

```
信息获取
→ 附件文本抽取
→ 产品清单结构化
→ evidence 输出
→ Promptbuilder 方法论读取
→ 目标品牌信息提取
→ 业务解释
→ 输出沉淀
```

目标：对任意指定 MIIT 批次和目标品牌（如比亚迪、智己），可一键式执行 Dry Run，验证数据质量和链路完整性，并输出可供业务解读的情报简报。

## 2. 当前链路状态

第 407 批 official 已验证完整链路成功。以下为各层级当前状态：

| 层级 | 路径 / 命令 | 状态 | 说明 |
|------|-------------|------|------|
| 脚本层 | `research_scripts/miit_new_car/monitor.py` | ✅ 可用 | 串联抓取、抽取、解析、diff、evidence 全流程 |
| 脚本层 | `research_scripts/miit_new_car/extract_attachment_text.py` | ✅ 可用 | 单步附件文本抽取（textutil 引擎） |
| 脚本层 | `research_scripts/miit_new_car/parse_product_list.py` | ✅ 可用 | 产品清单主表结构化解析 |
| 脚本层 | `research_scripts/miit_new_car/discover_batches.py` | ✅ 可用 | 多页批次发现 |
| Makefile | `make miit-fetch-batch BATCH=N` | ✅ 可用 | 集成 monitor.py 抓取单批次 |
| Makefile | `make miit-extract-text BATCH=N` | ✅ 可用 | 集成 extract_attachment_text.py |
| Makefile | `make miit-parse-product-list BATCH=N` | ✅ 可用 | 集成 parse_product_list.py |
| 原始文件 | `outputs/miit_new_car/raw/batch_{N}/` | ✅ 已验证 | 附件 DOC 文件缓存，第 407 批 3 个附件 |
| 文本抽取 | `outputs/miit_new_car/extracted/batch_{N}_attachment_text.json` | ✅ 已验证 | 第 407 批 3/3 成功，主附件 170KB |
| 文本原文 | `outputs/miit_new_car/extracted/text/batch_{N}/*.txt` | ✅ 已验证 | textutil 抽取纯文本，含 `\x07` 分隔表格 |
| 产品清单 | `outputs/miit_new_car/product_list/batch_{N}_product_list.json` | ✅ 已验证 | 1111 条/469 企/939 型号，quality=usable |
| 产品清单 CSV | `outputs/miit_new_car/product_list/batch_{N}_product_list.csv` | ✅ 已验证 | 与 JSON 同内容，适合表格浏览 |
| Evidence | `outputs/miit_new_car/evidence/batch_{N}_official_source_evidence.json` | ✅ 已验证 | 3 层 evidence（batch/attachment/product_list） |
| 诊断 | `outputs/miit_new_car/diagnostics/batch_{N}_attachment_diagnostics.json` | ✅ 已验证 | 附件可用性诊断 |
| Watchlist Diff | `outputs/miit_new_car/diff/batch_{N}_watchlist_diff.json` | ✅ 已验证 | 基于 legacy parsed 层的增量 diff |
| 方法论文档 | `docs/miit_promptbuilder_draft.md` | ✅ 已验证 | v0.2 draft，8 个 Prompt 模块 + 字段清洗 |
| 信号简报 | `outputs/miit_new_car/promptbuilder_runs/batch_{N}_official_miit_signal_brief.md` | ✅ 已验证 | 第 407 批信号简报含比亚迪/智己分析 |

### 已知限制

- **字段偏移**：部分品牌（小鹏/问界/零跑）在 product_list 中存在 enterprise_name / brand / product_name / product_model 列错位问题。字段对齐良好的品牌（比亚迪、智己）不受影响。
- **diff 覆盖范围**：`diff_watchlist.py` 基于 legacy `parsed/` 层输出，不反映 `product_list/` 最新数据。建议通过 product_list 全字段检索替代。
- **深度参数缺失**：续航、电池、电机、尺寸等参数当前无法从 product_list 获取，需通过税收目录/能耗目录补充。
- **缺少历史批次快照**：仅单批数据无法做严格两批对比。

## 3. 标准执行流程

以下为端到端执行步骤（以第 407 批为例）。

### 3.1 信息获取

```bash
# 发现最新批次
make miit-discover-latest-batch

# 发现多页批次
make miit-discover-batches PAGES=3

# 抓取指定批次（含附件下载、文本抽取、产品清单解析、diff、evidence 输出）
make miit-fetch-batch BATCH=407

# 或分步执行：
make miit-fetch-batch BATCH=407             # 抓取详情页 + 附件下载（monitor.py 会自动后续步骤）
```

### 3.2 附件文本抽取（单独执行时）

```bash
make miit-extract-text BATCH=407
```

输出：
- `outputs/miit_new_car/extracted/batch_407_attachment_text.json`
- `outputs/miit_new_car/extracted/text/batch_407/{hash}.txt`

### 3.3 产品清单结构化（单独执行时）

```bash
make miit-parse-product-list BATCH=407
```

输出：
- `outputs/miit_new_car/product_list/batch_407_product_list.json`
- `outputs/miit_new_car/product_list/batch_407_product_list.csv`

### 3.4 Evidence 检查

`make miit-fetch-batch` 已自动生成 evidence。检查路径：

```bash
# 查看 evidence JSON
cat mashang_workspace/outputs/miit_new_car/evidence/batch_407_official_source_evidence.json

# 检查 evidence_layers 三层可用性
```

关键字段：
- `evidence_layers.official_batch_evidence.available`
- `evidence_layers.official_attachment_evidence.available`
- `evidence_layers.official_product_list_evidence.available`
- `product_list_count`、`enterprise_count`、`quality`

### 3.5 读取 Promptbuilder 方法论

```bash
# 查看 Promptbuilder 文档
cat mashang_workspace/docs/miit_promptbuilder_draft.md
```

核心内容：
- §3 输入清洗与字段可信度校验
- §4 总流程（8 个 Prompt 模块）
- §5–12 各模块 Prompt 模板
- §13 人工校验规则
- §15 第 407 批 Dry Run 经验

### 3.6 目标品牌信息提取

从 product_list 中检索目标品牌：

```bash
# 检索品牌在产品清单中的记录
.venv/bin/python -c "
import json
with open('mashang_workspace/outputs/miit_new_car/product_list/batch_407_product_list.json') as f:
    data = json.load(f)
records = data.get('records', [])
for row in records:
    en = str(row.get('enterprise_name', '') or '')
    br = str(row.get('brand', '') or '')
    pn = str(row.get('product_name', '') or '')
    pm = str(row.get('product_model', '') or '')
    if '比亚迪' in en + br or '智己' in en + br:
        print(json.dumps({k: row[k] for k in ['enterprise_name','brand','product_name','product_model','product_model_granularity']}, ensure_ascii=False))
"
```

从附件原文文本中检索上下文：

```bash
.venv/bin/python -c "
with open('mashang_workspace/outputs/miit_new_car/extracted/text/batch_407/b43b6a0d1ffb47eba041adefa8541476.txt') as f:
    text = f.read()
for kw in ['比亚迪', '智己']:
    idx = text.find(kw)
    if idx >= 0:
        start = max(0, idx - 300)
        end = min(len(text), idx + 800)
        print(text[start:end])
"
```

> `b43b6a0...txt` 是附件 1（道路机动车辆完整附件）的文本。其他附件为税收目录，已排除。

### 3.7 业务解释

基于提取的目标品牌信息，按 Promptbuilder 方法论进行分析：

1. **批次扫描**：确认批次号、状态、资产完整性
2. **重点车型筛选**：S/A/B/C 分级
3. **车型信息抽取**：企业/品牌/型号/能源形式
4. **新旧版本差异**：强对比（需历史快照）或弱对比（型号首次出现判断）
5. **产品意图解读**：全新/改款/版本扩展/补齐短板
6. **竞品映射**：关联到我方核心车型（LS6/LS8 等）
7. **威胁等级判断**：评分式威胁评估
8. **信号简报**：汇总输出

详细 Prompt 模板见 `docs/miit_promptbuilder_draft.md` §5–12。

### 3.8 输出沉淀

简报输出到 `outputs/miit_new_car/promptbuilder_runs/`：

```bash
# 查看已有信号简报
cat mashang_workspace/outputs/miit_new_car/promptbuilder_runs/batch_407_official_miit_signal_brief.md
```

输出结构：
- 输入资产检查
- 批次扫描结果
- Watchlist 命中概览
- 重点车型 S/A/B/C 分级
- 车型信息抽取样例
- 产品意图解读
- 竞品映射
- 威胁等级判断
- 一句话结论（管理层/产品规划/情报跟踪版）
- 后续 7/30/90 天追踪清单
- 问题与改进建议

## 4. 目标品牌检索速查

### 4.1 品牌关键词

| 品牌 | product_list 关键词 | extracted text 关键词 | 预期字段对齐质量 |
|------|-------------------|----------------------|-----------------|
| 比亚迪 | `enterprise_name: 比亚迪汽车工业有限公司` | `比亚迪` | 高（企业名标准化） |
| 智己 | `brand: 智己` | `智己牌` | 高（brand 字段对齐好） |
| 小鹏 | `brand/enterprise 含 小鹏` | `小鹏` | 低（字段偏移严重） |
| 问界 | `enterprise 含 赛力斯` | `问界/赛力斯` | 中（字段偏移部分） |
| 理想 | `enterprise 含 理想` | `理想` | 中（字段偏移部分） |

### 4.2 字段对齐质量判断规则

| 条件 | 结论 |
|------|------|
| `enterprise_name` 以 `公司/厂/集团/有限` 结尾 | 企业名字段大概率正确 |
| `brand` 为已知品牌名（长度 <=10） | 品牌字段大概率正确 |
| `product_name` 包含 `车/轿车/客车/乘用车/货车` | 产品名字段大概率正确 |
| `product_model` 匹配 `大写字母+数字` 模式 | 型号字段大概率正确 |
| 上述任一项不符合 | 可能存在字段偏移，需回看 extracted text |

## 5. 输出文件一览

```
outputs/miit_new_car/
├── raw/batch_{N}/metadata.json                 # 批次元信息
├── raw/batch_{N}/attachments/{hash}.doc        # 附件 DOC 原始文件（不提交 git）
├── extracted/batch_{N}_attachment_text.json    # 附件文本抽取结果
├── extracted/text/batch_{N}/{hash}.txt         # 附件纯文本原文
├── product_list/batch_{N}_product_list.json    # 结构化产品清单
├── product_list/batch_{N}_product_list.csv     # 结构化产品清单（CSV）
├── parsed/batch_{N}_products.json              # 附件级结构化记录
├── diff/batch_{N}_watchlist_diff.json          # Watchlist 增量 diff
├── diagnostics/batch_{N}_attachment_diagnostics.json  # 附件诊断
├── evidence/batch_{N}_official_source_evidence.json   # Evidence 分层输出
└── promptbuilder_runs/batch_{N}_official_miit_signal_brief.md  # 业务信号简报
```

## 6. 快速验证命令

```bash
# 完整 Dry Run（以第 408 批为例）
make miit-fetch-batch BATCH=408

# 品牌检索
.venv/bin/python -c "
import json
with open('mashang_workspace/outputs/miit_new_car/product_list/batch_408_product_list.json') as f:
    data = json.load(f)
records = data.get('records', [])
targets = ['比亚迪', '智己', '小鹏', '问界', '理想']
for row in records:
    fields = ' '.join(str(row.get(k, '')) for k in ['enterprise_name','brand','product_name','product_model'])
    for t in targets:
        if t in fields:
            print(json.dumps({k: row.get(k, '') for k in ['enterprise_name','brand','product_name','product_model']}, ensure_ascii=False))
            break
"

# Promptbuilder 方法论
cat mashang_workspace/docs/miit_promptbuilder_draft.md

# 生成信号简报（人工编写，参考已有模板）
cat mashang_workspace/outputs/miit_new_car/promptbuilder_runs/batch_407_official_miit_signal_brief.md
```

## 7. 参考文档

| 文档 | 路径 | 内容 |
|------|------|------|
| Promptbuilder 方法论 | `docs/miit_promptbuilder_draft.md` | 8 个 Prompt 模块、字段清洗、校验规则 |
| MIIT 模块 README | `research_scripts/miit_new_car/README.md` | 脚本功能、数据流、配置 |
| 第 407 批信号简报 | `outputs/miit_new_car/promptbuilder_runs/batch_407_official_miit_signal_brief.md` | Dry Run 样例输出 |
| 第 407 批 Evidence | `outputs/miit_new_car/evidence/batch_407_official_source_evidence.json` | 三层证据 |
| 项目 AGENTS.md | `AGENTS.md` | 项目级 Agent 指南 |
