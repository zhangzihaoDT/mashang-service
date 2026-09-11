# runs/ — 研究与发现快照

每次完整执行 `workflow/issue_discovery.md` + `workflow/convergence.md` 产出一次 run，
目录不可变，作为可复现快照。

## 布局

```text
runs/<run_id>/
├── run.json           运行元数据（run_id / executed_at / study_year，供时间标准化）
├── evidence.jsonl     最小可追溯观察（schemas/evidence.schema.json）
├── issues.json        问题归并单元（schemas/issue.schema.json）
├── patterns.json      语义模式对象（schemas/pattern.schema.json，含 pattern_key，不含统计）
├── convergence.json   统计快照（schemas/convergence.schema.json，从 evidence 派生）
├── findings.json      业务结论（schemas/finding.schema.json，引用 pattern + convergence）
└── run.md             本次 run 报告
```

## 约定

- `run_id` 形如 `run_001`，顺序递增。
- 数据源始终为仓库外只读文件，run 目录只存结构化产物，不复制原始数据。
- `study_year` 必须显式写入 `run.json`；`support_date` 年份只从这里读取，不从字符串猜测。
- `convergence.json` 必须由 `scripts/derive_convergence.py` 生成，不手工编写。
- 每个 run 需通过可追溯性校验：evidence 全部被引用、issue 全部归入 pattern、
  pattern 全部有 convergence、finding 只引用 confirmed pattern 与已登记 pattern_key。
- 结论变更不修改旧 run，而是新建 run 并标注差异（Temporal Comparison 按 `pattern_key` 对齐）。
