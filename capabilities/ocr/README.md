# capabilities/ocr — OCR Base Capability

## 能力定位

**截图 / 图片 → 结构化文本（raw_text / markdown / tables）的领域无关 OCR 原语。**

不负责任何业务解析（如"从公告图里提取车型字段"）——那是业务层的职责。

## namespace 与入口

- Python: `from capabilities.ocr.ocr_service import process_image`
- CLI: `python -m capabilities.ocr.ocr_service --image <path> [--provider volcengine|mock] [--mode general_ocr|document_parse] [--force-refresh] [--output-root <dir>]`
- 消费方统一从仓库根 import `capabilities.ocr.*`。

## 双模式

| mode | 后端 | 输出侧重 |
|------|------|----------|
| `general_ocr` | 火山 `VisualService.ocr_normal()` 通用文字识别 | 逐行文字 + blocks + 简单表格 |
| `document_parse` | 火山 `VisualService.ocr_api()` 智能文档解析 | markdown（含表格）、结构化 blocks |

## providers

- `volcengine`：真实 provider。
- `mock`：离线桩，无需密钥，供测试与冒烟（不联网）。

## env 依赖

| 变量 | 说明 |
|------|------|
| `VOLCENGINE_ACCESS_KEY_ID` / `VOLCENGINE_SECRET_ACCESS_KEY` | 火山密钥（volcengine provider 必需） |
| `VOLCENGINE_REGION` | 默认 `cn-north-1` |
| `VOLCENGINE_OCR_SERVICE_ID` | veImageX service id（可选） |
| `VOLCENGINE_DOCUMENT_PARSE_TABLE_FORMAT` | 表格格式 `markdown`/`html`，默认 `markdown` |

缺密钥时 volcengine provider 返回 `status="failed"` 并给出明确错误；mock 无此限制。

## outputs

- 默认输出根：仓库 `outputs/ocr/`（`raw/{provider}/<id>.json` + `results/<id>.json`），可用 `--output-root` 覆盖。
- 缓存 content-addressed：`ocr_result_id = sha256(image_bytes : provider : mode)`，同图重复调用命中缓存（`status="cached"`），`--force-refresh` 跳过。
- `outputs/ocr/` 已 gitignore（可重建缓存）；历史证据 JSON 保留入库。

## 可靠性设计

- QPS 限制：单并发、最小间隔 1.2s（`MIN_INTERVAL_SECONDS`）。
- 重试：失败重试 3 次，退避 2/5/10s。
- 质量信号：`OcrQuality`（mean_confidence / low_confidence_blocks / needs_manual_review），低置信输出标记人工复核。

## tests

- 随包测试：`capabilities/ocr/tests/`，mock 离线全绿。
- 已纳入 `make test` / `make ci` 门禁。

## 适用 / 不适用

- 适用：MIIT 公告截图、来源页截图、票据/表格类图片 → 文本与表格。
- 不适用（not for）：
  - 车型字段/参数的结构化解析（业务层：Feature 模块或 workspace scripts）。
  - 视频、音频、大文件多页文档识别（document_parse 按单图接口接入，批处理由上层编排）。
  - 非 OCR 的图像理解/多模态问答。

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| — | 曾为 MIIT 公告详情页截图解析（已随 miit_new_car 迁移，能力在 MIIT/scripts 重新实现中） | 无活跃调用 |

## 历史沿革

- 原位于仓库根 `ocr/`（commit `50be5b9`），为 MIIT 公告图片工作流提供 OCR；
- 2026-09 按 Base Capabilities 层规划迁至 `capabilities/ocr`，import namespace 改为 `capabilities.ocr`，输出根迁至 `outputs/ocr/`；
- 逻辑与接口保持不变。
