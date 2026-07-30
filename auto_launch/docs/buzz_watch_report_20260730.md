# 声量热度搜索报告

**搜索日期**: 2026-07-30 | **时间窗口**: 最近 7 天 | **搜索引擎**: 豆包搜索 (Volc Search)
**Pipeline**: search_agent_v2 — buzz_watch mode (lite_scan profile)
**Pipeline 版本**: v2.1 (P0-1~4 已修复)

---

## 概述

使用 V2 Agent 搜索闭环，对 3 个车型执行声量/热度/微信指数相关的定向搜索，每车型 1 轮 3 条查询。

覆盖字段（三层结构）：
- **identity**: brand, model
- **metadata**: source
- **evidence**: buzz_volume, key_fact, wechat_index, social_discussion, sentiment

---

## 搜索过程

每车型的搜索由 Agent 闭环自动执行：

### 1. 意图编译

用户请求 → 编译器识别目标品牌/车型、时间窗口（最近 7 天）。检测到"微信指数""声量""热度"关键词后，自动切换至 `buzz_watch` 模式。完整实体保留（如 `MONA L03` 而非仅 `MONA`）。

### 2. 初始搜索（Round 1）

加载 `buzz_watch` 初始模板生成 3 条查询，调用豆包搜索 API：

- `{target} 微信指数 最近7天`
- `{target} 声量 热度 讨论 最近7天`
- `{target} 关注度 搜索指数 话题 最近7天`

每车型 3 条 × 8 条结果 = **24 条原始结果**。

### 3. 搜索结果评价

`evidencer` 对所有结果进行结构化评估：

- **独立来源计数**：按域名去重，统计独立信源数 ✅
- **官方来源计数**：按唯一域名判定，不依赖正文关键词误匹配（P0-1 修复）
- **字段覆盖率计算**：三层加权——identity × 1.0, metadata × 0.6, evidence × 0.8（P0-2 重构）
- **共享起源检测**：以标题前 30 字为指纹，识别雷同内容

### 4. 信息缺口识别

`gap_analyzer` 输出结构化缺口：

```json
{
  "covered_fields": ["model", "wechat_index"],
  "missing_fields": ["brand", "buzz_volume", "key_fact", "sentiment", "social_discussion", "source"],
  "tier_breakdown": {
    "identity": {"covered": 1, "total": 2, "covered_weight": 1.0, "weight": 2.0},
    "metadata": {"covered": 0, "total": 1, "covered_weight": 0, "weight": 0.6},
    "evidence": {"covered": 1, "total": 5, "covered_weight": 0.7, "weight": 3.5}
  }
}
```

### 5. 停止判断（P0-3 修复）

每轮结束后，`evidencer` 按三层策略评估：

| 条件 | 要求 | 本任务结果 |
|------|------|----------|
| **confirmed** | identity 覆盖 ≥ 80%, metadata ≥ 80%, evidence ≥ 80% | ❌ 三层均未达标 |
| **fallback** | 独立源 ≥ 3, 共享起源 ≤ 50%, evidence ≥ 70% | ❌ evidence 覆盖不足 |
| **hard_limit** | 达到 max_rounds (1) / max_queries (3) / max_calls (5) | ✅ **hard_limit** |

修复前 `conclusion_status` 为 `None`（`decision_table` 未命中）。修复后：**`conclusion_status: insufficient_evidence`**，`condition_met: hard_limit`。

---

## MONA L03

| 指标 | 值 |
|------|----|
| 独立来源数 | 15 |
| 官方来源数 | 0 |
| 字段覆盖率 | **30.2%** |
| 三层覆盖 | identity: 1/2 (model ✓), evidence: 1/5 (wechat_index ✓) |
| 共享起源率 | — |
| API 调用 | 3 |
| 搜索轮次 | 1 |

**查询**:
- MONA L03 微信指数 最近7天 ✅ **完整实体保留**
- MONA L03 声量 热度 讨论 最近7天
- MONA L03 关注度 搜索指数 话题 最近7天

---

## 吉利银河 TT

| 指标 | 值 |
|------|----|
| 独立来源数 | 14 |
| 官方来源数 | 16 |
| 字段覆盖率 | — |
| 已覆盖字段 | wechat_index |
| API 调用 | 6 |
| 搜索轮次 | 2 |

**第 1 轮查询**:
- 吉利银河 TT 微信指数 最近7天 ✅ **完整实体保留**
- 吉利银河 TT 声量 热度 讨论 最近7天
- 吉利银河 TT 关注度 搜索指数 话题 最近7天

**第 2 轮查询（缺口驱动）**:
- 吉利银河 TT 声量 热度 讨论度 最近7天
- 吉利银河 TT 关注度 搜索指数 百度指数 最近7天
- 吉利银河 TT 官方 公告 最近7天

---

## MG 07

| 指标 | 值 |
|------|----|
| 独立来源数 | 21 |
| 官方来源数 | 21 |
| 字段覆盖率 | **46%** |
| 已覆盖字段 | brand, model, wechat_index, sentiment |
| API 调用 | 6 |
| 搜索轮次 | 2 |

**第 1 轮查询**:
- MG 07 微信指数 最近7天 ✅ **完整实体保留**
- MG 07 声量 热度 讨论 最近7天
- MG 07 关注度 搜索指数 话题 最近7天

**第 2 轮查询（缺口驱动）**:
- MG 07 声量 热度 讨论度 最近7天
- MG 07 关注度 搜索指数 百度指数 最近7天
- MG 07 官方 公告 最近7天

---

## 字段覆盖情况

### 三层说明

| 层级 | 权重系数 | 字段 | 覆盖情况 |
|------|:-------:|------|---------|
| **identity** | × 1.0 | brand, model | ⚠️ 部分覆盖（仅 MG 07 补全） |
| **metadata** | × 0.6 | source | ❌ 均未覆盖 |
| **evidence** | × 0.8 | buzz_volume, wechat_index, social_discussion, sentiment, key_fact | ⚠️ wechat_index 全覆盖, sentiment 部分覆盖 |

### 各字段明细

| 字段 | 说明 | 覆盖情况 |
|------|------|---------|
| `wechat_index` | 微信指数/微信文章热度 | ✅ 3/3 车型 |
| `sentiment` | 情感倾向/用户评价 | ✅ MONA L03 + MG 07 |
| `brand` / `model` | 品牌/车型名称 | ✅ MG 07, ⚠️ MONA L03 仅 model |
| `buzz_volume` | 声量信号/讨论度 | ❌ 均未覆盖 |
| `key_fact` | 关键事实 | ❌ 均未覆盖 |
| `source` | 信息来源 | ❌ 均未覆盖 |
| `social_discussion` | 社交讨论 | ❌ 均未覆盖 |

字段覆盖率整体偏低的原因是 **微信指数本身不对外提供 API**，网页搜索能找到的仅为提及"微信指数"的文章，而非指数数值。

---

## Pipeline 信息

- Pipeline: `search_agent_v2` v2.1
- Profile: `lite_scan` (max_rounds=1, max_queries=3, max_calls=5) / `standard_scan` (MONA L03 最终轮)
- 停止条件: `hard_limit`
- 结论状态: **`insufficient_evidence`** ✅（P0-3 修复前为 `None`）
- 停止原因: `hard_limit_reached`
- 原始数据: `/tmp/p0_all.json`（P0 修复后 MONA L03 终版）

### P0 修复清单

| 修复 | 变更内容 | 效果 |
|------|---------|------|
| P0-1 | official_sources 改为唯一域名去重 | 避免正文关键词误匹配 |
| P0-2 | 字段体系拆为 identity/metadata/evidence 三层加权 | 覆盖率计算更有层次 |
| P0-3 | policy 路径修正 + profile limits 传入 evidencer | hard_limit 正确产出结论状态 |
| P0-4 | 从 intent 读取 model，`f"{brand} {model}"` 构造 display | Query 保留完整实体 |

---

*报告由 search_agent_v2 auto_launch 自动生成 · v2.1*
