---
name: vehicle-launch-deep-dive
metadata:
  version: "1.2"
  scope: new_vehicle_launch_deep_dive
description: 新车上市等生命周期描述性对比。仅提供已验证的累计锁单、日增与差额、观察期节奏、上市前小订池事件及来源算术分解；不提供未验证的经营归因、客群专题或未来潜力判断。
---

# vehicle-launch-deep-dive v1.2 稳定版

以业务定义中的代际为对象，比较各自上市后相同天数。只调用 [已验证能力清单](references/verified-capabilities.md) 中的 PASS 能力；能力认证 PASS 与单次 Gate A PASS 是两项不同要求。

## 执行

从仓库根目录运行：

```bash
.venv/bin/python workspace/research_scripts/launch_deep_dive.py \
  --gen CM3 --benchmarks LS8 LS9 --as-of 2026-09-27 --format all

.venv/bin/python workspace/research_scripts/launch_deep_dive.py \
  --gen LS8Neo --benchmarks CM3 LS8 --as-of 2026-11-09 --format all
```

- `--gen`、`--benchmarks`、`--as-of` 必填。as-of 是最后完整观察日，不默认为当天。
- `--plan` 只做前置核验；`--format terminal/json/html/all` 控制呈现；`--output` 指定产物根目录。
- 产物在 `<output>/vehicle_launch_v12_stable/<GEN>_D<N>_<as_of>/`：HTML、method.md、5 张 CSV、metrics.json、research_plan.json、result_contract.json。
- 稳定版不输出延长参考曲线或 PNG；旧 `--context-days` 仅接受 0，`--export-charts` 显式报错。不要复用历史十问报告目录中的旧文件。

## 稳定执行流程

1. 读取业务定义与订单快照；按 `series_group_logic` 优先级归属，上市日只取 `time_periods.{gen}.end`。
2. ResearchPlan 仅含 Q1–Q5 的已验证子能力。UNVERIFIED 与 FAIL 仅列入“不提供分析”清单，不进入正式计算。
3. **Gate A**：核验快照截止、每代际等长窗口、主键唯一、时间顺序、锁单 ≥30、小订池 ≥100。无记录日期无法证明为零时阻断；不补缺日、不静默换截止日。N=1 时不提供尾段分析。
4. 计算描述性指标并生成 Findings。每个对标独立比较，结论绑定全部数值、指标路径、方向与适用窗口。
5. **Gate B**：数值、方向、来源完备性、日增累计、差额、池事件率及二元分解恒等式。失败即退出，不写成功产物。
6. **Gate C**：逐个核对 HTML 指标单元格实际文本、结论正文与“不提供”说明。通过后写报告；计算前后输入 SHA256 必须一致。
7. 交付附来源、过滤、窗口、限制及可复现命令。不可回答的部分明确写“本次不提供分析”。

## 边界

- 不改原始数据、正式业务定义、调度或业务脚本；不刷新、不推送。
- 零售锁单只取用户车；小订池允许空订单类型，均剔除测试单、总部主理店及非零售。
- 上市前小订池 = 全部 `intention_payment_time < T0`，含早于配置预售起日记录；必须披露数量，不能称为严格预售期 cohort。
- 锁单与小订退款可同时发生。保留事件计数及重叠核验，**不计算待转化或封盘剩余池，不推演潜力**。
- 四类来源含上市日后残余；“无小订记录”不得解释为真实直接需求或流程证据。
- 分解只表示算术关系，不比较百分比变化与百分点变化来判定主因；不提供贡献占比。
- 当前快照事件截断不等于历史冻结快照；订单归属/类型/事件回填可能影响历史重建。
- 新问题可以在实际任务中探索，产物放 `workspace/scratch/` 或独立探索输出，不能混入稳定报告。新方法需原始数据独立复算、反例/边界检查、呈现与可复现验收通过后另行加入；不追求十问完整性。

## 参考

- [已验证能力清单](references/verified-capabilities.md)：适用条件、数据依赖、双案例证据、限制与移除项。
- [口径](references/metrics.md)、[方法](references/method.md)、[质量检查](references/evidence.md)、[反模式](references/pitfalls.md)。
- [报告骨架](templates/report-outline.md)、[口径文档骨架](templates/method-doc-outline.md)。
- 验收总报告：`workspace/outputs/reports/vehicle-launch-deep-dive_v1.2_稳定化收口.md`。

v1.0–v1.2 历史验收保留，作为审计来源，不再代表全部专题已认证。收口前代码保存在 Git `2fded9d`；本轮保持 v1.2 版本号。
