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

## 使用方式

### 发现最新批次

```bash
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py
python mashang_workspace/research_scripts/miit_new_car/discover_batches.py --limit 3 --format json
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

### Watchlist 增量 Diff

```bash
python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408
python mashang_workspace/research_scripts/miit_new_car/diff_watchlist.py --batch 408 --previous-batch 407
```

### 全流程监控

```bash
# 自动发现并处理最新未处理批次
python mashang_workspace/research_scripts/miit_new_car/monitor.py --latest

# 处理指定批次
python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408

# 带自定义 watchlist
python mashang_workspace/research_scripts/miit_new_car/monitor.py --batch 408 \
  --watchlist mashang_workspace/configs/miit_new_car_watchlist.csv
```

### Makefile 命令

```bash
make miit-discover-latest-batch     # 打印最新批次
make miit-fetch-batch BATCH=408     # 抓取指定批次
make miit-new-car-monitor           # 自动处理最新批次
```

## 输出文件说明

```
mashang_workspace/outputs/miit_new_car/
├── raw/batch_{N}/                   # 原始数据（不提交 git）
│   ├── metadata.json                # 批次元信息
│   ├── detail.html                  # 详情页 HTML
│   ├── links.json                   # 附件链接
│   └── attachments/                 # 下载的附件
├── parsed/                          # 结构化解析结果（可提交）
│   ├── batch_{N}_products.csv       # 产品清单 CSV
│   ├── batch_{N}_products.json      # 产品清单 JSON
│   └── batch_{N}_products.md        # 产品清单 Markdown
├── diff/                            # 增量对比结果（可提交）
│   ├── batch_{N}_watchlist_diff.json
│   └── batch_{N}_watchlist_diff.md
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

## 已知限制

1. **附件格式**：新产品公示清单为 HTML 表格格式，解析依赖表格结构，不同批次的 HTML 结构可能有差异
2. **DOC 格式**：正式发布的附件为 `.doc` 格式，当前仅保留原始文件，未做 DOC→结构化解析
3. **结构化字段**：能源类型、电池类型、续航、电机功率等深度参数暂未解析（这些字段在 DOC 格式中）
4. **分页**：列表页仅解析第 1 页（15 条），历史批次需翻页
5. **网站反爬**：工信部网站有一定频率限制，本模块内置了 timeout 和重试机制

## 后续可扩展方向

- [ ] **飞书通知**：新增 watchlist 匹配结果后自动推送飞书消息
- [ ] **定时任务**：通过 cron / GitHub Actions 定期运行 `miit-new-car-monitor`
- [ ] **车型参数深度解析**：解析 DOC 文件，提取完整的车辆技术参数
- [ ] **与 auto_launch_monitor 联动**：MIIT 发现的新产品自动加入竞品监测 watchlist
- [ ] **历史批次回填**：支持从第 300 批开始填补历史数据
- [ ] **多页发现**：对列表页进行多页翻页，发现更多历史批次
- [ ] **附件格式扩展**：支持 `.xls/.xlsx/.pdf` 等更多附件格式
- [ ] **增量缓存策略**：基于 ETag / Last-Modified 的智能缓存
