# runs/ —— 每轮运行记录 / 经验沉淀

每批一个文件（`batch_{batch}.md`），记录**这一批我学到了什么**。
这是项目自己的 operational memory，对后续 Agent 特别有价值（避免重复踩坑）。

```
runs/
├── batch_409.md         ← 409 运行记录
├── batch_410.md
└── eidc_fresh_rebuild.md ← EIDC 401-408 fresh rebuild 工程经验（olefile / scope gate / 验收纪律）
```

每个文件含 4 节：

- **概览** — 该批结果一句话 + 产物链接
- **Run Log** — 时间线：每一步什么时候做的、产出什么
- **Issues** — 遇到的问题（现象 / 状态）
- **Lessons** — 解决方案、关键认识、下一轮改进

> 和 logs/ 的区别：logs 是机器日志；runs/ 是人工沉淀的判断、坑与改进方向。
> 新批次开工前先读上一批的 `Lessons`；批次跑完更新 `runs/batch_{batch}.md`。
