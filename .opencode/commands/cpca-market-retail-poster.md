---
description: 直接调用 CPCA 全国乘用车市场零售简报海报 Business Job
---

调用 `.venv/bin/python -m jobs.cli --job cpca-market-retail-poster --format json`。有明确统计截止日时传 `--job-param date=YYYY-MM-DD`，已授权生成时传 `--job-param mode=render`。将 Job 返回的预检、待验收或失败状态直接反馈给用户，手动验收入口见 Job 契约。

$ARGUMENTS
