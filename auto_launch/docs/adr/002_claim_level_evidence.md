# ADR-002: Claim-level Evidence & Quality Status

**状态**: 已批准
**日期**: 2026-07-30
**影响范围**: search_agent_v2（evidencer.py / orchestrator.py / claim_evaluator.py 新模块）
**版本**: v2.3

---

## 问题

当前 v2.2 的 evidence 体系只回答 **"这个字段有没有被命中"**（covered / missing）：

```
fields_coverage: {
  buzz_volume: covered,      # ✓
  sentiment: missing,        # ✗
  ...
}
```

无法回答：
- 关于某个结论的**证据链**是什么？
- 单个证据的**可信度**有多高？（是官方数据还是路边社？是定量的还是定性的？）
- 是否存在**反证**？

## 方案

将证据评估从 **field-level binary coverage** 升级为 **claim-level multi-quality evidence**：

```
旧：task → results → overall decision
新：task → claims → 每个 claim 的 evidence set → 每个 evidence 的 quality → 整体 conclusion
```

### 数据结构

```python
EvidenceQuality = missing | mention_only | indirect | qualitative
                 | quantitative | officially_confirmed | contradicted

EvidenceItem = {
  source: str,        # 信源名称
  title: str,         # 标题
  snippet: str,       # 正文片段
  quality: str,       # 证据质量等级
  claim_field: str    # 关联的 claim 字段
}

Claim = {
  field: str,         # 字段名（如 buzz_volume）
  label: str,         # 中文标签（如 "声量信号"）
  status: str,        # unknown | partial | probable | confirmed | contradicted
  evidence: [EvidenceItem],
  summary: str
}
```

### 证据质量等级定义

| 等级 | 含义 | 判断依据 |
|------|------|----------|
| `missing` | 无相关结果 | 未命中 match_keywords |
| `mention_only` | 仅提及，无实质信息 | 命中关键词但 snippet 无细节 |
| `indirect` | 间接相关 | 同一品牌/车型有结果但非该字段 |
| `qualitative` | 有定性描述 | 含程度/情感词（"爆火"、"热议"、"好评"） |
| `quantitative` | 有定量数据 | 含数字+单位（"999台"、"27分钟"、"34.98万"） |
| `officially_confirmed` | 官方确认 | 信源为 official 类型 |
| `contradicted` | 反证 | 含否定词+负面/正面反转（"断崖式下滑" vs "爆火"） |

### Claim 状态聚合规则

| evidence 分布 | claim status |
|---------------|-------------|
| 全部 missing | unknown |
| 有 contradicted | contradicted |
| 有 officially_confirmed | confirmed |
| 有 quantitative + 多源 | probable |
| 有 qualitative + 多源 | partial |
| 仅 mention_only | unknown |

### 集成方式

不重写现有 pipeline，而是在现有 evidence 评估后**追加一层**：

```
Search → evaluate_evidence（field-level coverage，原流程不变）
       → claim_evaluate（claim-level evidence，新增）
       → gap_analyze → rewrite → loop
```

`claim_evaluate` 是纯分析模块，不参与搜索循环控制。它的输出附加在最终返回结果中。

### 与现有体系的兼容性

- 保留 field-level `tier_breakdown` 和 `fields_coverage`（向下兼容）
- `claim_evaluate` 输出作为 `final_evidence` 的 `claims` 子字段
- 不改变停止决策逻辑，claim 状态仅供分析和报告使用

### 不做的事

- 不引入 LLM 做 claim extraction（当前用规则）
- 不改变搜索循环的停止条件
- 不替换 field-level coverage
