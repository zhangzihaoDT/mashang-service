# Project Skills

本目录只描述和承载项目可发现的 Skill 能力本身。

```text
.opencode/skills/
├── README.md
├── branded_html_report/         # 品牌化业务报告
├── monthly-market-report/        # 月度市场报告
├── vehicle-launch-deep-dive/     # 新车上市深度研究（等生命周期跨代际对比）
│   ├── SKILL.md
│   ├── references/               # method / metrics / pitfalls / evidence
│   └── templates/                # 报告骨架 / 口径说明骨架
├── cpca-weekly-data-capture/      # 乘联会周度数据采集
├── runtime-eval-diagnosis/        # 历史 Runtime 报告诊断
├── official_document_render/
├── doubao-search/
├── mashang-diagram/              # 项目自有：diagram 路由 Skill（实体目录）
│   ├── SKILL.md
│   └── references/
│       └── type-milestone-dumbbell.md
└── diagram-design -> ../../../diagram-design/skills/diagram-design   # upstream，只读消费
```

边界：

- Skill 的行为规范、references 和 scripts 放在对应 Skill 目录中。
- 外部 upstream 如何接入 `mashang-service`，放在 `.opencode/integrations/`。
- 显式调用入口放在 `.opencode/commands/`。
- 不在本目录复制 diagram-design upstream 源码。
- 项目自有派生 Skill（`mashang-diagram`）是**路由层**：自有图表类型指向 `capabilities/diagram`，通用类型委派 upstream，自身不内联上游 type references、不改 upstream。

当前 diagram 接入说明：

`.opencode/integrations/diagram-design.md`

项目从仓库根目录发现全部 Skills。

**DSH 侧发现路径**：DSH 的文件系统 Skill Provider 扫描的是仓库根的 `.dsh/skills/`、`.agents/skills/`
与用户级 `~/.dsh/skills/`，**不扫描** `.opencode/skills/`。因此本项目自有 Skill 在
`.opencode/skills/<name>/` 编写（OpenCode 约定），并通过
`.dsh/skills/<name> -> ../../.opencode/skills/<name>` 软链暴露给 DSH，保持单一事实来源。

业务脚本在 `workspace/`，分析方法与运营手册在根 `docs/`。
