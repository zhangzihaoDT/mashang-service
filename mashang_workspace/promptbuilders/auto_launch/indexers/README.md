# Indexers — Output Index / Archive Workflow

## 定位

Indexers 扫描 `mashang_workspace/outputs/auto_launch/` 下所有 intake output directories，生成统一索引，方便检索、汇总和后续复盘。

## 输入目录结构

扫描的目录下应包含通过 `intake/process_ai_output.py --output-dir` 生成的子目录：

```
outputs/auto_launch/
├── {date}_{event_brand}_{event_model}_{event_type}/
│   ├── raw_ai_output.json
│   ├── normalized.json
│   ├── report.md
│   └── intake_manifest.json
├── {date}_{event_brand}_{event_model}_{event_type}/
│   └── ...
└── ...
```

## 输出

| 文件 | 说明 | 用途 |
|------|------|------|
| `index.json` | 结构化索引 JSON | 后续报告汇总或轻量数据处理 |
| `index.md` | 人类可读索引 Markdown | 快速查看已沉淀事件 |

## build_output_index.py

### 用法

```bash
python indexers/build_output_index.py \
    --input-dir mashang_workspace/outputs/auto_launch \
    --index-json mashang_workspace/outputs/auto_launch/index.json \
    --index-md mashang_workspace/outputs/auto_launch/index.md
```

### 约束

- 不访问网络
- 不调用 LLM
- 不做事实推断
- 仅读取本地的 intake_manifest.json 和 normalized.json
- 不解析或验证原始网页来源
- 损坏的 manifest 会跳过并在 warnings 中记录

## 与 intake workflow 的关系

```
intake (多次执行)
    ↓ 每个事件产出 output-dir/
    ↓
index (build_output_index.py)
    ↓
index.json + index.md
```

## 它不是数据库

- 不存储历史版本
- 不提供查询 API
- 不做事实核验
- 不负责搜索
- 仅做本地文件的轻量聚合

## 后续 Phase 7

- 报告汇总、周报或 dashboard
- 可能基于 index.json 生成汇总报告
