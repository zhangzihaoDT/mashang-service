# Root Cleanup Inventory — Phase 7

> Generated: 2026-06-11

## 清理前状态

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

## 保留在根目录的目录/文件

| 路径 | 原因 |
|------|------|
| `dataset/` | 共享数据底座 |
| `.env` | 共享环境变量 |
| `.venv/` | 共享虚拟环境 |
| `requirements.txt` | 共享依赖 |
| `README.md` | 项目主文档 |
| `AGENTS.md` | 项目级 Agent 指南 |
| `agent/` | Runtime 代码（待后续迁移） |
| `tools/` | Runtime 代码 |
| `operators/` | Runtime 代码 |
| `schema/` | Runtime 代码 |
| `main.py` | Runtime CLI 入口 |
| `feishu_bot.py` | Runtime 飞书入口 |
| `mashang_runtime/` | 产品化 Runtime 分支 |
| `mashang_workspace/` | 日常主工作区 |
| `archive/` | 历史归档 |
| `test/` | 临时分析脚本 |
| `logs/` | 运行时日志 |
| `设计方案/` | 历史设计文档 |
| `HTML/` | 工信部新车展示 |

## 风险说明

1. **模块阴影消除**: 根目录 `eval/` 移除后，Python import `from eval.xxx` 不会再找到旧代码
2. **Runtime import 独立性**: workspace 脚本中 `from operators.*` `from schema.*` 等 Runtime 导入依赖根目录，这些路径未被移动
3. **脚本兼容性**: 如果仍有用户使用 `python scripts/xxx.py`（旧路径），会失败；但 AGENTS.md 已全面更新为 `mashang_workspace/scripts/` 路径
4. **git history**: 归档不删除 git history，仅物理移动文件
