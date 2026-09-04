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
}
```

无法回答：
- 关于某个结论的**证据链**是什么？
- 单个证据的**可信度**有多高？
- 证据是**支持还是反对**这个结论？
- 结论的**具体内容是什么**（声量高/低？口碑正面/负面？）？

## 方案

将证据评估从 **field-level binary coverage** 升级为 **claim-level multi-quality evidence**。

核心原则：`claim_evaluate` 是纯分析模块，不参与搜索循环控制。

```
Coverage 负责: Search Loop
Claim    负责: Result Understanding
```

### 数据结构

Evidence 有两个正交维度：

```
quality    — 证据本身是什么（mention_only / qualitative / quantitative / official）
direction  — 证据对 claim 的支持关系（support / contradict / neutral）
```

```python
# 证据质量（描述"证据是什么"）
EvidenceQuality = missing | mention_only
                 | qualitative        # 有定性描述（程度/情感词）
                 | quantitative       # 有定量数据（数字+单位）
                 | official           # 官方源

# 证据方向（描述"证据支持还是反对 claim"）
EvidenceDirection = support | contradict | neutral

EvidenceItem = {
  source: str,
  title: str,
  quality: str,         # mention_only | qualitative | quantitative | official
  direction: str,       # support | contradict | neutral
  claim_field: str,
}

Claim = {
  field: str,           # 字段名（如 buzz_volume）
  label: str,           # 中文标签（如 "声量信号"）

  value: str,           # 聚合后的结论内容
                        #   buzz_volume → high / low
                        #   sentiment   → positive / negative / mixed
                        #   key_fact    → present / absent
                        #   依 evidence 的 direction 分布推断

  status: str,          # 聚合后的确信度
                        #   unknown  — 证据不足
                        #   partial  — 有定性证据
                        #   probable — 有定量证据
                        #   confirmed— 有官方证据

  evidence: [EvidenceItem],
  summary: str,
}
```

### 证据质量定义

| quality | 含义 | 判断依据 |
|---------|------|----------|
| `missing` | 无相关结果 | 未命中 match_keywords |
| `mention_only` | 仅提及关键词 | 命中 match_keywords 但无实质细节 |
| `qualitative` | 有定性描述 | 含程度/情感词（"爆火"、"热议"、"好评"） |
| `quantitative` | 有定量数据 | 含数字+单位（"999台"、"27分钟"、"34.98万"） |
| `official` | 官方源 | 信源为 official 类型 |

### direction 判断逻辑

对每条 evidence，判断它对 claim 默认值的支持/反对关系：

```
if 文本含 field 相关的反证关键词 → direction = contradict
elif 文本支持该 field 的默认值   → direction = support
else                             → direction = neutral
```

反证关键词按 field 配置（如 `sentiment` 的 "投诉"、"被骂"；`buzz_volume` 的 "无人问津"、"零关注"），非全局一刀切。

### Claim 状态聚合

```
score = sum(evidence quality scores)

  official      +3
  quantitative  +2
  qualitative  +1
  mention_only  0

≥6  → confirmed
3~5 → probable
1~2 → partial
0   → unknown
```

### Claim value 推断

```
support_count >> contradict_count → value = 默认正面值
contradict_count >> support_count → value = 负面值
support ≈ contradict              → value = mixed
```

### 集成方式

```
Search → evaluate_evidence（field-level coverage，原流程不变）
       → claim_evaluate（claim-level evidence，新增）
       → gap_analyze → rewrite → loop
```

`claim_evaluate` 不改变停止决策逻辑，claim 状态仅供分析和报告使用。

### 与现有体系的兼容性

- 保留 field-level `tier_breakdown` 和 `fields_coverage`（向下兼容）
- `claim_evaluate` 输出作为最终结果的 `claims` 子字段
- 不改变搜索循环的停止条件

### 不做的事

- 不引入 LLM 做 claim extraction
- 不改变搜索循环的停止条件
- 不替换 field-level coverage
