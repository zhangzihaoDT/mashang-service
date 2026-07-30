"""search_agent_v2 — 证据驱动的 Agent 搜索闭环

核心管线:
  搜索 → 搜索结果评价 → 信息缺口识别
    → 动态 Query 改写 → 证据充分性判断
        ├─ 不充分：继续搜索
        └─ 充分：停止并生成结论

v2.3 新增:
  Claim-level evidence — 每条 claim 的 evidence set + quality status
  Evidence quality: missing → mention_only → indirect → qualitative → quantitative → officially_confirmed → contradicted

停止策略三层:
  confirmed  — 官方源+多独立源+字段覆盖率达标
  fallback   — 非官方源但多源互证
  hard_limit — 达到资源上限，返回 insufficient_evidence

关键区别于 V1:
  - 不再按固定模板数量决定搜索结束
  - Query 由信息缺口动态生成，而非 staged 模板
  - Profile 仅控制最大资源边界，不控制 Query 数量
  - Claim-level 评估而非仅 field-level coverage（v2.3）
"""
