# ChatGPT Plan Templates

## 定位

本目录存放可**直接复制到 ChatGPT Plan 中手动运行**的 Prompt 模板。

## 设计原则

- 所有模板必须**自包含**，不能依赖 ChatGPT 读取本地文件路径
- 配置数据（watchlist、event_types、source_tiers 等）已内联展开在 Prompt 中
- 本地 repo 路径仅作为 provenance 标注，不作为运行依赖
- 每次 watchlist 或 event_types 变更后，应同步更新本目录下的模板

## 手动运行后

建议把 ChatGPT Plan 输出的 JSON 保存到本地：

```
mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor/raw_ai_output.json
```

然后运行 intake：

```bash
make auto-launch-intake \
  SAMPLE=mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor/raw_ai_output.json \
  OUT_DIR=mashang_workspace/outputs/auto_launch/{{MONITOR_DATE}}_daily_monitor
```

## 模板列表

| 模板 | 说明 | 能力定位 |
|------|------|----------|
| `daily_sales_action_monitor.md` | LS8 竞品销售动作日更监控 | 发现 + 归类 + 证据 + 轻量影响判断 |
