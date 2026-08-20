---
name: nev-research
description: 编排 NEV-APEAL 研究流程；读取 canonical context 与 state，路由当前研究阶段，调用现有 Research Engine / CLI，验证状态与产物，并确认研究对象已持久化。
compatibility: opencode
metadata:
  project: nev_apeal
  role: orchestration
---

# NEV Research

## 能力边界

本 Skill 是 `nev_apeal` 之上的研究流程编排层，不是新的 Research Engine。

它只负责：

```text
READ → ROUTE → INVOKE → VERIFY → PERSIST
```

它不负责：

- Analyze：由现有分析模块和 Research Engine 负责
- Derive question：由 Research Engine 负责
- Select candidate：由 Qualification Protocol 负责
- Score：由 Topic Tournament 负责
- 定义统计阈值、样本门槛、效应量门槛或排序规则
- 保存具体 axes、Topic、Signal 数字或当前 Champion 结论

如果一条规则可能改变相同数据上的研究结果，它不应只写在本 Skill 中；应放入 Engine、Contract、Qualification Protocol、Tournament 或 canonical Context，并进行版本化。

## READ

开始任何研究动作前，读取 canonical context 和当前 state。

优先检查：

1. `nev_apeal/README.md`
2. `nev_apeal/contracts/measurement.json`
3. `nev_apeal/contracts/variables.json`
4. `nev_apeal/contracts/modules.json`
5. `nev_apeal/contracts/signal_contract.json`
6. `nev_apeal/research/topic_tournament.md`
7. `nev_apeal/reports/signal_board.md`
8. 当前 `nev_apeal/research/runs/<topic>/state.yaml`
9. 当前 Run 的 `hypotheses.yaml`、`queue.yaml` 和 `evidence.jsonl`

读取时区分：

- canonical context：数据、测量口径、Signal Contract、Topic/Tournament 事实
- runtime state：当前 Run、队列、证据链和 terminal 状态
- task input：本轮用户要求或新数据 wave

不要从目录数量、自然语言报告或临时输出反推统计事实。若 canonical state 与临时报告冲突，以项目规定的 canonical source 为准，并记录冲突。

不得因为读取状态而重复运行已完成的 evidence。需要 replay、new data wave 或方法版本升级时，必须明确说明理由并创建新的可追踪运行记录。

## ROUTE

根据 READ 得到的 state，识别当前唯一主要研究阶段：

| 阶段 | 路由条件 | 下一步 |
|---|---|---|
| Discovery | Discovery 已开放且尚未完成当前冻结批次 | 调用冻结 Discovery Engine |
| Qualification | 已有 Signal / Candidate，尚未完成资格验证 | 调用 Qualification Protocol |
| Topic Research | Topic Run 非 terminal，仍有未解决问题 | 调用 Research Engine 的下一步动作 |
| Tournament | Topic 已 terminal，Tournament 尚未同步 | 更新并验证 Topic Tournament |
| Production | 已有 Champion，任务涉及正式交付 | 只读取 Champion-led findings |
| Blocked | 缺少 contract、state、输入或合法 transition | 停止并报告缺失项，不自行假设 |

同一轮只选择一个主要阶段。不要绕过阶段顺序，也不要把 Discovery Signal 直接当作 Topic 或 Champion。

Terminal 的具体状态、晋级条件和评分规则以 canonical Context、Engine 和相应 Protocol 为准；Skill 不重新定义它们。

## INVOKE

从 `mashang-service` 根目录进入 `nev_apeal` 后，调用已有入口，不复制其实现：

```bash
PYTHONPATH=. ../.venv/bin/python cli.py contracts
PYTHONPATH=. ../.venv/bin/python cli.py run <analysis-command> [args]
PYTHONPATH=. ../.venv/bin/python cli.py research <research-action> --topic <topic> [args]
```

研究状态动作通过现有 CLI 调用：

- `state`：读取 Run state
- `next`：获取 Engine 选择的下一项动作
- `add-evidence`：写入 Evidence
- `update`：写入 state 更新
- `stop-check`：执行 Engine stop-check
- `derive-questions`：调用 Engine 派生问题；Skill 不自行推导

分析命令、参数、统计方法和结果解释由 `nev_apeal/analysis/`、Discovery Engine、Qualification Protocol 与 Tournament 定义。Skill 只负责正确路由和调用，不在文本规则中重述这些方法。

调用失败、输入不完整或返回状态不明确时，不跳到下一阶段，不手工伪造结果。

## VERIFY

每次 INVOKE 后执行最小必要验证：

1. 命令是否成功完成，失败是否被明确记录。
2. 输出是否符合对应 Contract；缺字段时不得把结果当作合格证据。
3. state transition 是否被 Engine / Protocol 允许。
4. 当前状态是否仍有 open question、未完成 Gate 或高优先级阻塞项。
5. Topic Run 是否应继续，或已进入 terminal。
6. terminal 后是否触发 Tournament 同步。
7. `REJECTED`、`INCONCLUSIVE` 或 coverage 不足的结果是否被阻止晋级 Champion。
8. Production 输出是否只引用 Champion-led finding。
9. Production Deck 是否携带符合 `contracts/slide_contract.json` 的每页 metadata block，并通过 `scratch/validate_slide_contract.py`（0 error）。
10. Production 渲染产物是否通过 `scratch/render_qa.py`（0 error）；`warn` 项进入人工复核清单，不得静默放行。
11. 修改 Slide Contract / validator / renderer / visual identity / palette / SKILL / Production routing 后，是否重放 `scratch/replay_golden_case.py` 且结果为 PASS（slides=10，semantic 0/0，render 0/0）。未 PASS 不得合并。

`VERIFY` 只检查 Engine / Contract / Protocol 的执行结果，不新增统计门槛，不重新评分，也不替代 stop-check。

每轮 Topic Research 完成后都必须执行：

```bash
PYTHONPATH=. ../.venv/bin/python cli.py research stop-check --topic <topic>
```

没有通过 stop-check 时，不得把 Run 写成 READY 或结束研究。

## PERSIST

确认研究对象已落盘，并且引用关系可追踪：

- Discovery 结果持久化为符合 Signal Contract 的 Signal
- Qualification 决策持久化为 Candidate / validation queue 记录
- Topic Research 结果通过 `add-evidence` 写入对应 `evidence.jsonl`
- Hypothesis、queue 和 state 与本轮 Evidence 保持一致
- terminal Topic 同步到 Topic Tournament 的 canonical 记录
- Champion 变化后同步其 Production 边界和引用关系

持久化完成前，不把本轮结果写入报告、不向后续阶段宣称完成，也不把自然语言摘要当作 Evidence。

每个 Evidence 必须能够回溯到数据源、变量、筛选条件、权重、样本支持、分析结果和适用边界。观察性横截面结果不得被 Skill 改写为因果、纵向趋势或产品质量衰减。

## 操作护栏

- 先 READ，再 ROUTE；不得根据用户一句话直接运行分析。
- 不重复已有 evidence，除非有明确 replay、new data wave 或版本变化理由。
- 不绕过 Engine、Contract、Qualification 或 Tournament。
- 不因显著性、effect size 或单个 Signal 自动创建 Topic。
- 不将 `REJECTED` / `INCONCLUSIVE` evidence 晋级为 Champion。
- 不在 Skill 中硬编码当前 Topic 排名、统计数字、25 axes、T1-T10 或特定业务结论。
- 当前项目处于 Production / Content Locked 阶段时，除非出现明确的新数据 wave 或重启指令，不主动扩张研究。
