# Issue Review — 问题与模式的评审门禁

本文件定义 **Issue / Pattern 的复核规则**。Discovery（`issue_discovery.md`）负责产出候选，
Review 负责在进入 finding 之前拦住：重复、证据不足、严重度失真、伪因果与口径漂移。

## 评审对象与时机

| 对象 | 触发时机 | 通过后状态 |
| --- | --- | --- |
| Issue (`ISS-####`) | 归并完成后 | `candidate → confirmed` |
| Pattern (`PAT-####`) | 聚类完成后 | `candidate → confirmed` |
| Finding (`FND-####`) | 结论起草后 | `draft → ready` |

每次评审在对象上写入 `review`（`reviewed_by` / `reviewed_at` / `decision` / `notes`）。
未评审的候选不得被 finding 引用。

> `Convergence`（`CONV-####`）不是评审对象，而是由 evidence 确定性派生的统计快照
> （见 `workflow/convergence.md`）。评审只校验其与规则一致，不回写主观状态。

## 评审清单

### 1. 可追溯性（硬门禁）

- [ ] 每个 issue 的 `evidence_ids` 全部存在，且 `source_ref` 指向有效 `record_index` + `source_field`。
- [ ] `statement` 不含原文没有的因果词（导致 / 造成 / because of）。
- [ ] benchmark 类证据单独标注 `evidence_type=benchmark`，不与用户原话混为一体。

### 2. 去重与合并（硬门禁）

- [ ] 同 `affected_function` + 同现象未重复建 issue。
- [ ] 跨门店同现象已合并，`store_count` 正确去重。
- [ ] 判定为 `duplicate` / `merged` 的对象必须填 `dup_of`，并停止被下游引用。

### 3. 证据充分性（复现层级由 Convergence 派生）

`recurrence` 与 `evidence_strength` 由 `workflow/convergence.md` 的冻结规则从 evidence 计算，
评审**只校验派生结果与规则一致**，不重新主观判断：

| 对象 | 最低要求 | 不满足时 |
| --- | --- | --- |
| Issue | ≥1 条 evidence 且原文可读 | 退回补证 |
| Pattern `isolated` | `city_store_count = 1`，允许单点 | 可保留为观察 |
| Pattern `repeated` | `city_store_count ≥ 2` | 按 Convergence 重算，不手改 |
| Pattern `systemic` | `city_store_count ≥ 3` 且（跨车型或跨支持时间区间） | 按 Convergence 重算，不手改 |
| Finding | 仅引用 `confirmed` pattern，且其 Convergence `evidence_strength ≥ moderate`（P0/P1） | 退回或标 `draft` |

- 若评审认为 `recurrence` / `evidence_strength` 失真，应检查派生输入
  （`source_evidence_ids` 与 `source_ref`）或校准规则阈值，**不得直接改写 Convergence 结果**。
- 阈值校准必须写进 `workflow/convergence.md` 并同步 `convergence.schema.json`。

### 4. 严重度校准

| severity | 口径 | 典型信号 |
| --- | --- | --- |
| `blocker` | 明确表述拒购 / 退单 / 直接流失风险 | 「拒购风险大」「因此不买」 |
| `high` | 高频或强不满，影响购买决策 | 多店复现的体验硬伤 |
| `medium` | 明确不满但不决定性 | 单店明确抱怨 |
| `low` | 轻微、个别、口头提及 | 一次性小吐槽 |

校准规则：

- **严重度看影响，不看语气**。「用户觉得不爽」不等于 `blocker`。
- 单条原话里说「拒购」但无其他复现，可标 `blocker`，但 `stated_intent` 不得等同于实际流失。
- 跨门店复现的问题，严重度不得低于单店同类问题。
- 严重度变更必须写 `severity_rationale`。

### 5. 伪因果与口径

- [ ] 不把观察性关联写成因果（如「销量差是因为方向盘」）。
- [ ] 不把 stated intent（用户口头意向）当作行为事实（实际锁单/退订）。
- [ ] 门店运营类信号（`operational`）与产品类问题分开，不与产品 issue 混计。
- [ ] category / series / business_signal 取值来自受控词表。

## 状态机

```text
candidate ──confirm──▶ confirmed ──▶ (进入 pattern / finding)
    │
    ├──reject────────▶ rejected      （必填 rejection_reason）
    ├──duplicate─────▶ duplicate     （必填 dup_of）
    └──merge─────────▶ merged        （必填 dup_of）
```

- `needs_evidence`：评审认为证据不足但值得保留，退回 discovery 补证，仍为 `candidate`。
- 已 `confirmed` 的对象若发现新反证，可回退为 `candidate` 并重评（记录在 `review.notes`）。

## 复核触发条件

出现以下任一情况，必须重新评审：

1. 新增 evidence 改变了 Convergence 的 `city_store_count` / `series_count` / `support_period_count`；
2. 新数据 wave / 新一批门店反馈到来（触发新的 Temporal Comparison）；
3. 严重度、category、受控词表发生变化；
4. 下游 finding 结论与 pattern / convergence 证据冲突；
5. 对标竞品信息被证伪或更新。

## 争议处理

- 两人对同一对象状态不一致时，**以证据可追溯性优先**：证据不足方让步。
- 对机制解释有分歧时，保留为 `inconclusive` 或降置信，不强行二选一。
- 无法在 evidence 层解决的分歧，上升到 finding 的 `boundary` 显式记录，而不是隐藏。

## 门禁与产物

- 评审结果回写到对象自身的 `status` / `review` 字段。
- finding 引用前做一次**引用完整性检查**：所有 `pattern_ids` / `issue_ids` 均为 `confirmed`，
  且 `convergence_ids` 均存在、`pattern_key` 均已登记。
- 统计量只从 `runs/<run_id>/convergence.json` 读取；Pattern 与 Finding 不得内联统计字段。
- 评测样例放 `eval/cases/`，用于回归发现与评审规则。

## 边界

- Review 是**质量门禁**，不替代产品决策；它只保证结论「可追溯、不过度、口径一致」。
- 不因追求完美证据而无限期扣留候选；不足以确认的，显式标 `inconclusive` 交付。
