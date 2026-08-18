# NEV-APEAL Research Agent Guide

## Research Loop

遵循 `research_loop.md`：先建立 Measurement/Data Contract，再记录 Signal，形成可检验 Hypothesis，最后进行 Topic Analysis。

## Statistical Source of Truth

`topic_tournament.md` 顶部的 **Research Funnel / Topic Mapping** 是研究过程的唯一统计事实源。新增、复跑、晋级或淘汰 Topic 时，必须同步更新映射与计数（Evidence / Run / Topic / Finalist / Champion / Production 各层），不得从目录或 evidence 临时反推。

## Evidence Rules

- 所有数字必须能追溯到 `data/source.sav`、变量、筛选条件、权重与样本量。
- 关联不能写成因果；配置、品牌、价格和购买任务差异默认视为 observational signal。
- 横截面数据不能支持跨年趋势或市场份额变化。
- 每轮研究状态写入对应 `runs/<topic>/`，不要覆盖历史证据。
