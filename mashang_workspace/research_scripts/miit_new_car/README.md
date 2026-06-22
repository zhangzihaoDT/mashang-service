# MIIT 新车公告批次监控

自动发现工信部装备工业发展中心「公告发布」栏目的最新批次，抓取详情页与附件，解析产品信息，与重点品牌 watchlist 做增量 diff，输出结构化结果。

## 能力定位

本模块是 mashang-service 汽车市场情报系统的官方信源接入能力之一。提供从公告发现到结构化产品的完整流水线，输出结果可被 OpenCode / Agent 后续读取和复用。

## 官方信息源

| 源 | URL | 说明 |
|---|-----|------|
| 公告发布列表 | `https://www.miit-eidc.org.cn/col/col1691/index.html` | 工信部装备工业发展中心车辆准入许可→公告发布 |
| 详情页（示例） | `/art/2026/6/10/art_1691_12455.html` | 每批次详情页面，含附件链接 |
| 附件（示例） | `https://www.miit.gov.cn/datainfo/cpgg/art/2026/art_...html` | 新产品公示清单（HTML） |
| 附件（DOC） | `https://wap.miit.gov.cn/cms_files/filemanager/...doc` | 正式发布的企业及产品清单（DOC） |

## 模块结构

```
mashang_workspace/research_scripts/miit_new_car/
├── __init__.py           # 模块入口
├── discover_batches.py   # 发现最新批次（列表页解析）
├── fetch_batch.py        # 抓取详情页和附件
├── parse_products.py     # 解析附件为结构化产品信息
├── diff_watchlist.py     # 与上一批做增量 diff + 品牌 watchlist 匹配
├── monitor.py            # 串联完整流水线
└── README.md             # 本文件
```

## V0.2 新增能力

| 能力 | CLI | Makefile |
|------|-----|----------|
| 最新公示批次 | `monitor.py --latest-publicity` | `make miit-latest-publicity` |
| 最新正式公告 | `monitor.py --latest-official` | `make miit-latest-official` |
| 多页发现 | `discover_batches.py --pages 3` | `make miit-discover-batches PAGES=3` |
| 附件文本抽取 | `extract_attachment_text.py --batch 408` | `make miit-extract-text BATCH=408` |
| Official Evidence | monitor 自动输出 | `outputs/miit_new_car/evidence/` |

## 使用方式

### 发现最新批次

```bash
# 默认最新 10 条（混合公示+正式）
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py

# 只看公示批次
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --publicity

# 只看正式公告
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --official

# 多页回溯
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --pages 3 --limit 20
```

### 抓取指定批次

```bash
python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408
python mashang_workspace/research_scripts/miit_new_car/fetch_batch.py --batch 408 --no-download
```

### 解析产品

```bash
python mashang_workspace/research_scripts/miit_new_car/parse_products.py --batch 408
```

### 附件文本抽取

```bash
python mashang_workspace/research_scripts/miit_new_car/extract_attachment_text.py --batch 408
```

### Watchlist 增量 Diff

```bash
python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408
python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408 --previous-batch 407
```

### 全流程监控

```bash
# 自动发现并处理最新批次（batch_no 最大）
python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest

# 自动发现并处理最新公示批次
python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-publicity

# 自动发现并处理最新正式公告批次
python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest-official

# 处理指定批次
python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408

# 带自定义 watchlist
python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 \
  --watchlist mashang_workspace/configs/miit_new_car_watchlist.csv
```

### Makefile 命令

```bash
make miit-discover-latest-batch        # 打印最新批次
make miit-discover-batches PAGES=3     # 多页发现
make miit-fetch-batch BATCH=408        # 抓取指定批次
make miit-new-car-monitor              # 监控最新批次
make miit-latest-publicity             # 监控最新公示
make miit-latest-official              # 监控最新正式公告
make miit-extract-text BATCH=408       # 抽取附件文本
```

## 输出文件说明

```
mashang_workspace/outputs/miit_new_car/
├── raw/batch_{N}/                   # 原始数据（不提交 git）
│   ├── metadata.json                # 批次元信息（V0.2: 含 attachment_statuses）
│   ├── detail.html                  # 详情页 HTML
│   ├── links.json                   # 附件链接
│   ├── attachment_status.json       # V0.2: 每个附件下载状态
│   └── attachments/                 # 下载的附件
├── discovery/                       # V0.2: 多页发现结果
│   ├── discovered_batches.json
│   └── discovered_batches.md
├── parsed/                          # 结构化解析结果
│   ├── batch_{N}_products.csv
│   ├── batch_{N}_products.json
│   └── batch_{N}_products.md
├── extracted/                       # V0.2: 附件文本抽取
│   ├── batch_{N}_attachment_text.json
│   └── batch_{N}_attachment_text.md
├── diff/                            # 增量对比结果
│   ├── batch_{N}_watchlist_diff.json
│   └── batch_{N}_watchlist_diff.md
├── evidence/                        # V0.2: Official Source Evidence
│   └── batch_{N}_official_source_evidence.json
└── state/
    └── latest_processed_batch.json  # 最新处理批次记录
```

## Watchlist 配置方式

默认配置文件：`mashang_workspace/configs/miit_new_car_watchlist.csv`

格式：

```csv
brand,keywords
智己,智己;IM;上汽集团
理想,理想
```

- `brand`: 品牌名称
- `keywords`: 分号分隔的关键词，用于匹配企业名称/产品型号/车辆名称

可以通过自定义 CSV 路径覆盖：

```bash
python monitor.py --batch 408 --watchlist /path/to/custom_watchlist.csv
```

## 测试

```bash
# 运行 MIIT 模块测试
python -m pytest mashang_workspace/tests/test_miit_new_car.py -v

# 运行全量项目测试
make test
```

## 已知限制 (V0.2)

1. **附件 404**：`miit.gov.cn` 域的部分附件 URL 在当前环境返回 404（可能是地区限制）。已作为 warning 处理，不中断主流程
2. **DOC 解析**：`.doc` 格式依赖系统工具 `textutil`（macOS）或 `antiword`，不可用时记录为 `unsupported`，不失败。`.docx` 已支持标准 zipfile 解析
3. **结构化字段**：能源类型、电池类型、续航、电机功率等深度参数仍暂未解析（包含在 DOC 中）
4. **分页上限**：jpage API 返回 `totalpage=3`（约 45 条），不是全量历史
5. **网站稳定性**：工信部 EIDC 网站可能间歇性不可达，所有网络请求有 timeout 和重试
6. **附件 URL 时效**：部分公示附件链接可能有时效性，正式公告 URL 更稳定
7. **auto_launch_monitor 联动**：当前只输出 evidence 文件，未自动触发 auto_launch_monitor 主流程

## 后续可扩展方向

- [ ] **飞书通知**：新增 watchlist 匹配结果后自动推送飞书消息
- [ ] **定时任务**：通过 cron / GitHub Actions 定期运行 `miit-new-car-monitor`
- [ ] **车型参数深度解析**：解析 DOC 文件，提取完整的车辆技术参数
- [ ] **与 auto_launch_monitor 联动**：MIIT 发现的新产品自动加入竞品监测 watchlist
- [ ] **历史批次回填**：支持从第 300 批开始填补历史数据
- [ ] **多页发现**：对列表页进行多页翻页，发现更多历史批次
- [ ] **附件格式扩展**：支持 `.xls/.xlsx/.pdf` 等更多附件格式
- [ ] **增量缓存策略**：基于 ETag / Last-Modified 的智能缓存
