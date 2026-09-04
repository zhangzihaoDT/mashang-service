# Batch 409 运行记录

## 概览

- **公示日期**：2026-07-07
- **结果**：14 品牌归档，小米报告 + 分类报告
- **产物**：[scan_report](../reports/batch_409/scan_report.html) · [category_report](../reports/batch_409/category_report/index.html) · [brand_report（小米）](../reports/batch_409/brand_report/index.html)

## 结论

首批完整跑通 P1→P5。覆盖 17 款 watchlist 车型，插混/增程全部命中车船税第88批目录。

## 阅读

- [run_log.md](run_log.md) — 时间线
- [issues.md](issues.md) — 遇到的问题
- [lessons.md](lessons.md) — 经验沉淀

## Run Log（时间线）

# Batch 409 run_log

| 时间 | 步骤 | 动作 | 产出 |
|------|------|------|------|
| 2026-07-07 | 公告公示 | 记录批次页 / 公告页 | `workflow/config/batches.yaml` 登记 409（page_id/index/tax_batch=88） |
| 2026-07-07 | P1 搜索 | `miit_search.py --batch 409` | scan 快照 + 品牌搜索简报 |
| 2026-07-07~ | P2 归档 | `miit_archive_detail.py --batch 409 --all-missing` | 14 品牌归档（小米/理想/小鹏/特斯拉/岚图/腾势/魏牌/问界/享界/智界/启境/爱咖/猛士/方程豹） |
| 2026-07-10 | P3 补充 | 下载车船税第88批 .doc → textutil → 解析 | 607 款车型 / 163 家企业结构化 JSON |
| 2026-07-13 | P5 报告 | `generate_category_report.py --all` | 分类报告（4 分类）+ index |
| 2026-07-13 | P5 报告 | `generate_miit_reports.py --brand 小米` | 小米单品牌报告（澎程N70/N90） |
| 后续 | 目录收敛 | 模块重组为 5 类资产（reports/data/scripts/runs/workflow） | 本 runs/409 记录 |

## Issues（问题）

# Batch 409 issues

## 首批勘探阶段的问题

| # | 问题 | 现象 | 状态 |
|---|------|------|------|
| 1 | API 403 | `requests.get()` 直接请求搜索 API 返回 403 | 已解决（三头 + cookie priming） |
| 2 | 紧凑 JSON | 部分搜索字段 403 | 已解决（`separators=(",", ":")`） |
| 3 | 列数不对 | 解析结果为空 | 已解决（确认 6 列顺序） |
| 4 | 重复数据 | 同一品牌经 CPSB+QYMC 重复 | 已解决（按 `cpxh` 去重） |
| 5 | JSON 转义 | HTML 片段中 `\"` | 已解决（`json.loads()` 还原） |
| 6 | 照片 URL 转义 | href 匹配不到 | 已解决（先还原 HTML） |
| 7 | 其它字段 | 电池/电机信息藏在长文本 | 已解决（正则提取） |
| 8 | 纯电/燃油车型无名称 | 车船税目录不含 | 已解决（`model_name_map.json` 命名映射） |

## Lessons（经验）

# Batch 409 lessons

## 首批跑通的核心认识

1. **公告页是壳，数据在 iframe + API**：`art_xxx.html` 只是包装，真实数据走
   `/api-gateway/jpaas-publish-server/front/page/build/unit`。用 Playwright network_requests 定位最有效。
2. **反爬三件套 + cookie priming**：Referer / X-Requested-With / UA 缺一不可；首次先 GET index.html。
3. **紧凑 JSON 序列化**：`json.dumps(..., separators=(",", ":"))`，否则部分搜索字段 403。
4. **附件1 详情页 = 参数事实层，附件2 车船税 = 电池/续航事实层**：
   - 尺寸/电机/电池类型/供应商/座位 → 附件1（`.md`）
   - 电池容量/纯电续航/整备质量 → 附件2（车船税 JSON）
5. **纯电/燃油车型车船税目录不收录** → 需要 `model_name_map.json` 补名称、别家目录补续航。
6. **车型合并按 通用名称 → 名称映射 → base ID** 五级 fallback，先定名称再拼报告。

## 下一轮要改进

- 归档是"一次性脚本"，失败会卡死整批 → 需要失败分类 + checkpoint + retry（410 已重构）
- 批次配置散落多个脚本 → 需要单一 `batches.yaml`（410 已收敛）
- 名称映射靠人工检索 → 后续可跟踪媒体报道自动补充
