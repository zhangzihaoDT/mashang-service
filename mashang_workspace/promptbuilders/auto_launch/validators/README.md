# Validators — AI 返回结果校验与归一化

## 定位

Validators 是 Auto Launch workflow 中的**质量保证层**，负责：
1. **validate_ai_response**: 检查 AI 返回是否满足 Prompt 要求的输出结构、来源标注、确认状态区分
2. **normalize_ai_response**: 将 AI 原始 Markdown 输出转换为标准化 evidence JSON

## 当前实现

两个脚本实际位于 `examples/` 目录下（历史原因，Makefile 和 Golden Prompts 已依赖该路径）：

| 脚本 | 路径 |
|------|------|
| validate_ai_response.py | `../examples/validate_ai_response.py` |
| normalize_ai_response.py | `../examples/normalize_ai_response.py` |

## 工作流程

```
AI raw.md
    │
    ▼
validate_ai_response.py  ───→  validation.json（通过/不通过 + 差距报告）
    │
    ▼
normalize_ai_response.py ───→  normalized_evidence.json（标准化 JSON）
                              + executive_brief.md（可读摘要）
```

## 用法

```bash
# 校验 AI 返回
python ../examples/validate_ai_response.py \
  --case-name my_case \
  --raw-file path/to/response.raw.md \
  --prompt-file path/to/prompt.md \
  --output path/to/validation.json

# 归一化
python ../examples/normalize_ai_response.py \
  --case-name my_case \
  --raw-file path/to/response.raw.md \
  --prompt-file path/to/prompt.md \
  --validation-file path/to/validation.json \
  --normalized-output path/to/normalized_evidence.json \
  --report-output path/to/brief.md
```
