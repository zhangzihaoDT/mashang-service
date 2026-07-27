# Inbox 管线

Inbox 是 auto_launch 的日报摄入层入口。当前只做一件事：**解析 Planner 日报 → 按章节合约路由 → 幂等入库 5 张表。**

不再支持 ChatGPT Daily Run 自由文本和 keep/discard 二分类。

详见 [`daily_report_pipeline.md`](daily_report_pipeline.md)。
