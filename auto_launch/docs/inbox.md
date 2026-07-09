# Inbox MVP — 极简信息漏斗

## 定位

Inbox 是 auto_launch 的极简信息入口漏斗，执行"先收缩、再放大"策略下的第一步收缩。

当前只做一件事：**把 ChatGPT daily run 的 raw text 输入，经过极简二分类，写入本地事实库。**

不做：
- 多级分桶（candidate / discovery_signal / context_only / needs_review）
- Review queue
- impact score
- 复杂 UI 或 HTML 报告

## 使用方式

### 从文件导入

```bash
python -m auto_launch.cli inbox --input daily_run.md --date 2026-07-09
```

输出示例：
```
Inbox Summary — 2026-07-09
  Raw items:  8
  Kept:       6
  Discarded:  2

  [KEEP]
    1. [智己][LS6] 权益调整 — 智己 LS6 限时权益调整
    2. [极氪][7X] 开启交付 — 极氪 7X 开启交付
    ...

  [DISCARD]
    1. 行业观察：2026 年下半年新能源市场展望  (opinion_or_prediction)
    2. 宁德时代发布第三代换电方案  (no_brand_or_model)
```

### 交互模式

```bash
python -m auto_launch.cli inbox
```

粘贴 ChatGPT daily run 结果，输入 `/done` 结束。系统解析后询问是否写入事实库。

### 查询事实

```bash
# 最近 7 天所有事实
python -m auto_launch.cli facts

# 按品牌筛选
python -m auto_launch.cli facts --brand 智己

# 按事件类型
python -m auto_launch.cli facts --event-type 权益调整

# 最近 14 天
python -m auto_launch.cli facts --days 14

# 统计概览
python -m auto_launch.cli facts --stats
```

## ChatGPT Daily Run 格式

推荐使用结构化 Markdown 格式，Inbox 可自动提取品牌、车型、事件类型等字段：

```markdown
## 智己 LS6 限时权益调整

- 品牌: 智己
- 车型: LS6
- 事件类型: 权益调整
- 时间: 2026-07-09
- 摘要: 智己 LS6 推出限时权益...
- 来源: immotors.com
- 信源等级: tier_1_official
```

## keep / discard 规则

### KEEP

1. 明确品牌/车型 + 明确事件类型 + 明确信源
2. 明确品牌/车型 + 明确营销动作（上市、预售、权益、交付、发布会、价格、配置等）
3. 涉及 watchlist 核心事件（上市、交付、权益、价格、预售、发布会）
4. 品牌/车型来自以下 watchlist：

   智己、极氪、领克、问界、智界、享界、尊界、尚界、鸿蒙智行、理想、小米、蔚来、乐道、萤火虫、小鹏、阿维塔、深蓝、零跑、腾势、方程豹、比亚迪、特斯拉、埃安、岚图、大众、宝马、奔驰、奥迪、吉利、长城

### DISCARD

1. 没有明确品牌/车型
2. 没有明确事件类型或动作
3. 泛泛评论、预测、态度、观点（含"我觉得、我认为、预计、预测"等关键词）
4. 与 watchlist 品牌无关
5. 无法形成结构化事实

> **第一版宁可少收，不要污染事实库。**

## 事实库去重逻辑

```text
fingerprint = MD5(brand + model + event_type + event_date + normalized_title)
```

- 如果 fingerprint 不存在 → 新增记录（seen_count=1）
- 如果 fingerprint 已存在 → 不新增，更新 last_seen，seen_count+1

## 数据库

- 位置：`auto_launch/outputs/facts/auto_launch_facts.sqlite`
- 引擎：SQLite（Python 标准库 sqlite3，无外部依赖）
- 表结构：单表 `facts`，含 brand / model / event_type / event_date / title / claim / source_name / source_url / source_tier / seen_count / first_seen / last_seen / fingerprint 等字段

## MVP 边界

| 模块 | 状态 |
|------|------|
| inbox --input file | ✓ |
| inbox 交互模式 | ✓ |
| keep / discard 二分类 | ✓ |
| 事实库写入 | ✓ |
| 去重（fingerprint） | ✓ |
| facts 查询（终端表格） | ✓ |
| facts --stats | ✓ |
| 测试（5 文件，~30 用例） | ✓ |
| 复杂 UI / HTML 报告 | ❌ 不做 |
| Review queue | ❌ 不做 |
| impact score | ❌ 不做 |
| search --to-facts | ❌ 后续迭代 |
