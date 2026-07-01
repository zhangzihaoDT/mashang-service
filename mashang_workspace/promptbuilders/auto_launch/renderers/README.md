# Renderers — 格式渲染层

## 定位

Renderers 将 normalized JSON 渲染为人类可读的格式。

当前只有一个渲染器：`render_markdown_report.py`，输出 markdown 格式。

## 约束

- **只做格式渲染，不做事实推断**
- 不提升置信度
- 不合并 confirmed / inference / unconfirmed
- 不访问网络
- 不调用 LLM

## render_markdown_report.py

### 用法

```bash
python renderers/render_markdown_report.py path/to/normalized.json --output path/to/report.md
```

### 输出结构

所有 markdown 报告包含以下 8 个章节：

1. **一句话结论** — brief 用 executive_summary，event 用 confirmed_facts 摘要
2. **基本信息** — record_type / record_key / our_model / event_model / event_brand / event_type / battle_field / time_window / confidence_level
3. **已确认事实 confirmed_facts**
4. **推断 inferences**
5. **未确认说法 unconfirmed_claims**
6. **证据缺口 missing_evidence**
7. **后续追踪 followup_recommendation**
8. **来源 source_items**

## 样本数据

`examples/reports/` 下的 markdown 报告**仅用于结构测试**，不代表真实事实。

- 来源 URL 均为虚构
- 品牌、车型、价格等数据为示意性内容
