# vehicle-launch-deep-dive v1.2 稳定化收口

日期：2026-11-11。范围：独立开发任务，仅 Skill、研究计算/规划/渲染、专项回归与交付证据；未修改原始数据、业务定义、jobs、调度或 business_scripts。未刷新、未推送。

## 结论与精简清单

正式链路保留 **5 项 PASS** 描述性能力，**8 项 UNVERIFIED** 暂停，**3 项 FAIL 能力组**移除。所有对标逐一比较，不补经营推测、不保持十问篇幅。

- PASS：Q1 等窗口累计锁单；Q2 日增/累计与边际差；Q3 首日占比/尾段日均；Q4 上市前小订池事件与二元算术分解；Q5 来源四分及差额分解。
- UNVERIFIED：区域/渠道、网络描述、产品/客群、同档客群、座椅/六座、质量/兑现、竞争 PK、延长曲线/PNG。
- FAIL 能力组：版本缺口归因；待转化/封盘剩余与潜力；经营主因/需求/购买力判断。
- 不同状态可以存在于同一历史模块中：例如 Q4 事件计数保留，旧待转化与主因判断删除。以具体子能力为准，不能给整章笼统 PASS。

[已验证能力清单](../../../.opencode/skills/vehicle-launch-deep-dive/references/verified-capabilities.md) 列出每项适用条件、数据依赖、验证案例及限制；[逐函数审计](vehicle_launch_v12_stable/function_audit.csv) 覆盖精简前 **200 个函数/类**及其处置。

三个实现文件由 **6,277 行缩至 914 行**，约减少 **85.4%**；不是仅隐藏报告区块，未认证计算、旧文案、CSV、JSON 指标和追问维度均退出正式链路。

## 逐项审计依据

| 历史问题 / 模块 / 报告区块 | 认证 | 决定与依据 |
|---|---|---|
| Q1 累计、Q2 每日差额 | PASS | 两案例原始订单逐日复算；差额不合并基准，不使用占总差额百分比 |
| Q3 首日/尾段 | PASS 子集 | 只保留可复算的描述指标；删除“首日占比高所以后续更弱”等跳跃判断及衰减/稳态推断 |
| Q4 池规模、锁单/退款事件、率、规模×率分解 | PASS 子集 | 两案例独立复算；明确池包含配置起日前记录，锁退允许重叠；只做算术分解 |
| Q4 经营主次、预售日均反事实 | FAIL / UNVERIFIED | 相对变化与百分点不能直接比较主次；机械延长预售天数未验证，删除 |
| Q5 来源 | PASS 子集 | 三个主要来源加上市日后残余，四类之和等于全部锁单；残余也参与差额分解 |
| Q5 下单流程判断 | FAIL | 占比接近不能证明流程一致，占比差异不能证明需求差异，删除固定判断 |
| Q6 区域、省份车型、线索渠道 | UNVERIFIED | 局部数字或历史可运行不足以完成比较/结论/呈现联合认证，停用 |
| Q7 网络描述 / 网络分解与主次 | UNVERIFIED / FAIL | 先舍入单店均值导致“精确”恒等式偏差：CM3 对 LS8 +2.5单，对 LS9 +2.0单；本轮不修复专题，整体停用 |
| Q8 产品、配置、行为、客群、集中度 | UNVERIFIED | 字段映射和局部核对不等于跨案例解释成立，停用全部正式输出 |
| Q8b 同档 / Q8c 座椅、六座 | UNVERIFIED | 无电量段崩溃修复只证明可运行；CM3 座椅缺字段；同电量不等于完整可比，停用 |
| Q8d 版本缺口 | FAIL | 同档存在性不足以认证版本缺口归因，固定缺口/贡献逻辑移除 |
| Q9 质量与交付 | UNVERIFIED | 事件语义及历史快照回填尚未联合验证，停用 |
| Q10 剩余状态、锁退速度、潜力区间 | FAIL | 封盘池锁退重叠：CM3 24、LS8Neo 9、LS8 8、LS9 7单；旧算法重复扣除，速度又混入非池锁单，全部删除 |
| 竞争 PK、参考延长线、PNG | UNVERIFIED | 不属于本次双案例已验证交付范围；停止自动读取及渲染，旧参数显式报错 |
| 启发式主线、经营判断、观察建议 | FAIL / UNVERIFIED | 固定历史判断与未验证假设不再进入 Findings 或报告 |

注意：上表“封盘池重叠”含上市当日新增；正式 Q4 上市前池的重叠分别为 CM3 **7**、LS8Neo **6**、LS8 **5**、LS9 **6**单。两者不是同一集合。原来声称“剩余池恒等式通过”的记录不能覆盖这个问题。

[缺陷数值证据](vehicle_launch_v12_stable/baseline_defects.json) 基于收口前产物及原始订单复算。CM3 旧差额+42单却曾给出2179%贡献，预售相反方向项曾出现864%；稳定版不再生成贡献占比。

## 历史验收重新解释

- [LS8Neo 会话复盘](LS8Neo_上市深度研究_会话复盘与方法沉淀.md)：保留业务窗口、过滤、原始复算和复现纪律；不把探索专题变成认证能力。
- [v1.0 验收](vehicle-launch-deep-dive_v1.0_验收报告.md)：28项数字一致和边界通过是局部证据；同档崩溃与模板固化不构成全部专题 PASS。
- [v1.1 修复记录](vehicle-launch-deep-dive_v1.1_缺陷修复报告.md)：保留缺数据保护、绝对差表达和复现要求；撤销剩余池“准确”的推断，删除启发式经营主线。
- [v1.2 规划记录](vehicle-launch-deep-dive_v1.2_Validated_Research_Planning.md)：Gate A PASS 仅说明可执行，不证明结论；旧 Gate B/C 只记录不阻断、只核少量数值与标题的问题已收口。

## 质量底线与执行链路

- ResearchPlan 只列 PASS 白名单；UNVERIFIED/FAIL 只进入“不提供分析”说明。直接调用 build_context 也必须重新做 Gate A，不能用 allowed 参数放行未知能力。
- Gate A 保留30单/100池下限，并核验新鲜度、每日记录覆盖、订单主键、事件顺序、窗口和代际。未来对标或缺日不能补零；退款为日期粒度，顺序检查使用日期而非伪造日内时点。
- Gate B 对全部 Findings 数值、正文、方向以及日增累计、来源、率、两项分解校验；先舍入再算不被接受。
- 原池三条恒等式仍保留，新增独立互斥性和非负性要求；重叠或缺互斥证据必须失败。旧失败场景进入回归测试，没有删失败测试或放松阈值来通过。
- Gate C 对149个实际 HTML 数值/日期单元格、全部发现正文及停用说明核验。先在内存渲染，B/C失败非零退出且不写本次成功产物。
- 稳定报告使用独立目录，与历史十问产物分开；运行前后 SHA256 一致才写出。JSON 只宣告已验证追问维度。

## CM3 与 LS8Neo 回归结果

| 案例（截止日） | D1–D5零售累计 | 保留能力独立复算 | Gate B | Gate C显示单元格 | 同参数重跑 |
|---|---|---|---|---|---|
| CM3（2026-09-27） | CM3 3,739 / LS8 3,773 / LS9 3,697 | 5/5 PASS | 76/76 | 149/149 | PASS |
| LS8Neo（2026-11-09） | LS8Neo 2,166 / CM3 3,739 / LS8 3,773 | 5/5 PASS | 76/76 | 149/149 | PASS |

每个案例均复核全部代际的每日计数、池规模与锁退事件/重叠、来源、首日占比/尾段日均、所有对标差额与分解；独立脚本不调用生产计算和过滤函数，代际归属仍使用正式共享规则。

- [CM3 证据](vehicle_launch_v12_stable/regression/CM3/vehicle_launch_v12_stable/CM3_D5_2026-09-27/independent_evidence.json) · [正式样例报告](vehicle_launch_v12_stable/regression/CM3/vehicle_launch_v12_stable/CM3_D5_2026-09-27/report.html)
- [LS8Neo 证据](vehicle_launch_v12_stable/regression/LS8Neo/vehicle_launch_v12_stable/LS8Neo_D5_2026-11-09/independent_evidence.json) · [正式样例报告](vehicle_launch_v12_stable/regression/LS8Neo/vehicle_launch_v12_stable/LS8Neo_D5_2026-11-09/report.html)
- 同目录 reproducibility.json：比较5张CSV、metrics、plan、HTML、method、Result Contract，只有 generated_at 允许变化。
- 浏览器呈现：CM3_D5_2026-09-27 PASS, LS8Neo_D5_2026-11-09 PASS；[桌面/移动端记录](vehicle_launch_v12_stable/visual_qa.json)，两案例各9张表、149个绑定单元格。
- 专项16项测试：真实案例、前置阻断、未知计划、单日窗口、未来对标、锁退重叠、数值/方向/正文篡改、分解错误与B/C失败禁止交付。按 `make verify-scope` / `make verify` 限定范围执行，未运行全量pytest或CI。
- 全范围首次验证中仅报告模块直接运行的 import 路径失败；已修正并按改动范围复验。后续移动端长文本溢出也修复，保留检查记录，最终结果见 [验证记录](vehicle_launch_v12_stable/verification_summary.json)。
- Skill frontmatter校验通过；`git diff --check`通过。

原始数据SHA256：`ce17aec76813ac8c9ca3f04c15d202e31a67a0827f376cfaee75d1ecdfc6e103`。业务定义SHA256：`c1310c398aa03882e29549fc1855c6885b91b3910a8d6416cd4c431102763d6f`。数字仅对本快照有效；不能把重复生成当作历史快照不变的保证。

## 更新后的 Skill 与后续原则

入口：[SKILL.md](../../../.opencode/skills/vehicle-launch-deep-dive/SKILL.md)。清单、方法、口径、证据、反模式及两个模板已同步，版本仍为1.2。

后续新研究可单独探索；探索结果不进入正式报告。只有原始复算、反例/边界、呈现及复现全部验证的方法才另行进入稳定白名单。对于本次不能回答的经营问题，报告明确“不提供分析”，不以推测补齐。

Git：`2fded9d` 保留收口前v1.2完整实现与规划记录，稳定版另作提交；无需在当前 Skill 中保留可误调用的旧业务实现。按上述范围作为 **v1.2 稳定版本关闭本轮工作**，不表示暂停专题已经被修复或认证。
