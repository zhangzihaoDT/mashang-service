# eval/ — Product Expert 评测

用于检验 `workflow/issue_discovery.md` 与 `workflow/issue_review.md` 的规则是否被稳定执行。

- `cases/`：评测样例与期望输出。格式见 `cases/README.md`。
- 目标：同一份输入，不同人/agent 执行 discovery + review 后，应得到**结构一致、可追溯**的结果。
- 评测以**规则与结构一致性**为主，不追求逐字相同的措辞。

样例覆盖的维度：

| 维度 | 说明 |
| --- | --- |
| 抽取完整性 | 关键观察是否被抽成 evidence，不遗漏、不臆造 |
| 分类一致性 | `category` / `series` / `business_signal` 是否符合受控词表 |
| 去重正确性 | 同现象跨门店是否合并、重复是否标注 `dup_of` |
| 严重度校准 | `severity` 是否符合 `issue_review.md` 口径 |
| 可追溯性 | 每个 issue 是否可回到 evidence 与原始记录 |
| Attribution 派生 | Convergence 的三维来源是否与 evidence.source_ref 一致 |
| 复现层级 | `recurrence` / `evidence_strength` 是否与 `convergence.md` 冻结规则一致 |
| 时间标准化 | `support_date` 是否按 run 的 `study_year` 标准化，未猜测年份 |
| 单一事实来源 | Pattern/Finding 是否不再内联统计字段 |
