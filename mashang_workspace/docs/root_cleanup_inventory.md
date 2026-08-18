# Root Cleanup Inventory — Phase 7 (Historical)

> Generated: 2026-06-11 · Updated: 2026-06-16 (Phase 2)
>
> **注意**：本文档记录了 Phase 7 时期根目录清理的原始计划与执行结果。
> 此后项目结构已进一步演化，以下章节反映了**当前已稳定的结构边界**。

## Current Status / 当前结构说明

自 Phase 7 之后发生的关键变化：

| 演化 | 说明 |
|------|------|
| `shared/` 成为 canonical | 共享算子、Schema、Loader 的**唯一可信来源**，新增 `loaders/` 子目录 |
| `mashang_runtime/` 标记 frozen | 不再新增依赖，operators/schema 的 canonical 版本已迁移到 `shared/` |
| 根目录 `docs/` | Phase 1 调整为 service 级白名单管理，仅允许 `tp_and_mix_ways_dataset.md` |
| 根目录 `scripts/` | 调整为 service 级构建脚本，仅允许 build/render 相关脚本 |
| 根目录 `tests/` | 调整为 service 级测试，仅允许 `test_tp_and_mix_ways_dataset_build.py` |
| `dataset/incoming/` | 新增为 service 级外部原始数据入口（浏览器/飞书下载） |
| Playwright MCP | 配置在 `opencode.jsonc`，定位为 service 级 browser ingestion 能力 |
| `.local/` | 浏览器 profile / 登录态，已加入 `.gitignore` |
| `mashang_workspace/inputs/` | 已废弃，飞书下载入口统一为 `dataset/incoming/feishu/` |

## Phase 7 清理前状态 (Historical)

| 根目录 | 文件数 | Workspace 对应目录 | 文件数 | 差异 | 处理方式 |
|--------|:------:|-------------------|:------:|------|----------|
| `docs/` | 11 | `mashang_workspace/docs/` | 11 | 完全重复 | → archive |
| `scripts/` | 28 | `mashang_workspace/scripts/` | 28 | 已补齐 `lock_release_analysis.md` | → archive |
| `eval/` | 12 | `mashang_workspace/eval/` | 15 | 已补齐 `runtime_cases.jsonl` `regression_notes.md` | → archive |
| `tests/` | 8 | `mashang_workspace/tests/` | 10 | 完全重复 | → archive |
| `utils/` | 1 | `mashang_workspace/utils/` | 2 | workspace 多 `paths.py` | → archive |
| `outputs/` | 8 | `mashang_workspace/outputs/` | 7 | 生成文件，不存档 | → archive |

## 迁移到 archive/root_legacy/ 的文件

| 源路径 | 归档路径 |
|--------|----------|
| `docs/` (11 文件) | `archive/root_legacy/docs/` |
| `scripts/` (28 文件) | `archive/root_legacy/scripts/` |
| `eval/` (12 文件) | `archive/root_legacy/eval/` |
| `tests/` (8 文件) | `archive/root_legacy/tests/` |
| `utils/` (1 文件) | `archive/root_legacy/utils/` |
| `outputs/` (8 文件) | `archive/root_legacy/outputs/` |

## 当前根目录关键目录/文件

| 路径 | 分类 | 说明 |
|------|------|------|
| `dataset/` | ✅ service 共享 | 共享数据底座（含 `TP&MIX-ways/` `incoming/` `wechat/`） |
| `shared/` | ✅ service 共享 | canonical operators / schema / loaders |
| `scripts/` | ✅ service 构建 | 构建/渲染脚本（白名单管理） |
| `docs/` | ✅ service 文档 | 仅 `tp_and_mix_ways_dataset.md`（白名单管理） |
| `tests/` | ✅ service 测试 | 仅 `test_tp_and_mix_ways_dataset_build.py`（白名单管理） |
| `mashang_workspace/` | ✅ workspace | 日常主工作区 |
| `mashang_runtime_v2/` | ✅ service | 新 Runtime 架构实验 |
| `opencode.jsonc` | ✅ service 配置 | OpenCode + MCP Playwright 配置 |
| `Makefile` | ✅ service 命令 | eval / build / pipeline |
| `pyproject.toml` | ✅ service 配置 | Python 项目配置 |
| `.github/` | ✅ service CI | CI 工作流 |
| `.env` | 🟡 本地 | 共享环境变量（gitignored） |
| `.venv/` | 🟡 本地 | 共享虚拟环境（gitignored） |
| `.local/` | 🟡 本地 | 浏览器 profile / 登录态（gitignored） |
| `node_modules/` | 🟡 本地 | NPM 依赖（gitignored） |
| `main.py` | 🟡 legacy 兼容 | Root CLI 入口 → 委托 `mashang_runtime.main` |
| `feishu_bot.py` | 🟡 legacy 兼容 | Root 飞书入口 → 委托 `mashang_runtime.feishu_bot` |
| `mashang_runtime/` | 🟡 legacy frozen | 不再新增依赖，frozen |
| `HTML/` | 🟡 展示 | 工信部新车 HTML |
| `test/` | 🔴 已废弃 | 临时分析脚本（gitignored） |
| `logs/` | 🔴 已废弃 | 运行时日志（gitignored） |
| `outputs/` | 🟡 service 产物 | 品牌资产 / 渲染报告 / 提交物 |

### 不再存在的目录

以下目录已在 Phase 7 归档或后续清理中移除：
- `agent/` → 已迁入 `mashang_runtime/agent/`
- `tools/` → 已迁入 `mashang_runtime/tools/`
- `operators/` → canonical 版本在 `shared/operators/`
- `schema/` → canonical 版本在 `shared/schema/`
- `eval/` → 已迁入 `mashang_workspace/eval/`
- `utils/` → 已迁入 `mashang_workspace/utils/`
- `设计方案/` → 已迁入 `mashang_runtime/design_docs/`
- `archive/` → 已删除

## 风险说明

1. **根目录 docs/scripts/tests 白名单**: 仅允许 service 级文件，workspace 私有资产应放在 `mashang_workspace/` 下
2. **shared 是 canonical**: `shared/operators/` 和 `shared/schema/` 是唯一可信来源，`mashang_runtime/` 中的副本仅供 frozen legacy 兼容
3. **飞书下载入口**: 统一为 `dataset/incoming/feishu/`，workspace 不负责下载，只消费数据
4. **Playwright MCP**: 配置在 `opencode.jsonc`，浏览器 profile 在 `.local/playwright-mcp/feishu/`（gitignored）
5. **git history**: 归档不删除 git history，仅物理移动文件
