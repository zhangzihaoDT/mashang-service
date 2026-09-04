# Decisions

- 将“购买任务 × 产品魅力”作为当前 Topic。
- 将结论状态定为 `REFINED`，不写成购买任务的因果效应。
- 配置扫描仅作为候选 Signal，后续必须控制价格、品牌与车型结构。

## E2E Run Log (2026-08-15)

- R1 Q001 子指数：增购优势集中在感性体验，补能仅 +1.3 → 假设支持（E-003）。
- R2 Q003 控制能源/价格/品牌：增购系数 +18.3(p=4.3e-07) 仍显著 → 非结构混淆（E-004）。
- R3 Q004 城市调节：增购优势各级城市内一致，无反转（E-005）。
- Stop Condition：证据数=5、confidence=high、核心 confounder 已检查 → status=ready。
- SYNTHESIZE：写入 insight.json，由 topic_renderer 生成 reports/topic_x.md。
- 遗留：Q005 性别调节（低价值）未执行；建议设计级 drilldown 前先控制车型结构。

## Agent Run v2 (Iteration 2 验证, 2026-08-18)

- R4 Q006 AEXT drilldown：仅 1 个 rating 题承载全部外观差异，item 层触底（E-006）。
- R5 suppression 追问：sequential coefficient path 显示增购 vs 换购 全程 +18.3，无 suppression；+11.8→+18.3 放大为参照组混淆，H-002 排除（E-007）。derive_questions 无放大不误报（negative control 通过）。
- R6 ADRV item 下钻：总体驾驶感受与转向/操控手感承载差异，制动最弱（E-008）→ mechanism_depth 3。
- R7 explain_gap + 机制综合：外观指数差异>驾驶是指数聚合结构（单题 vs 5题分摊，E-009）；产品机制形成（E-010）→ mechanism_depth 4。
- Stop：5 门禁全开（evidence 10 / confidence / effect_interpreted / mechanism_depth 4 / 无高优先级开放问题）→ status=ready。
- 行为跃迁 vs V1：Ready 不再由"证据数+confidence"触发，必须达到 item 级机制深度且无高优先级开放问题。
