---
name: cpca-market-retail-poster
description: 使用 Business Job 已准备的 briefing.json 和固定视觉资产生成 CPCA 零售简报候选海报。
---

# CPCA 市场零售简报海报渲染

输入为 [Business Job](../../../docs/数据获取/cpca_market_retail_poster_job.md) 生成的 `briefing.json`、[V1.1 Prompt](references/poster-prompt.txt) 和 [10 月 31 日版参考图](assets/reference-poster.png)。Skill 将 `layout` 中的显示文字填入模板，使用现有客户端向 `opencode/gemini-nano-banana-2.1` 提交一次原生请求。输出为候选图及对应的模型回包记录。

程序入口为 `scripts/poster.py` 的 `render(briefing_path, template, reference, output)`，Job 直接调用。业务数据准备、重试控制、验收及发布由 Job 执行。同一次尝试的 `briefing.json` 用于生成和验收。

离线排查可传入 Job 已生成的快照，查看最终 Prompt。

```bash
.venv/bin/python .opencode/skills/cpca-market-retail-poster/scripts/poster.py \
  --briefing "$briefing_path"
```

使用 `--prompt-version V1.2` 可用同一快照复核实验版。独立候选图实验须显式传入 `--generate` 和实验 `--output` 目录。正式生成入口及验收状态见 [Job 契约](../../../docs/数据获取/cpca_market_retail_poster_job.md)。
