# Project Skills

本目录只描述和承载项目可发现的 Skill 能力本身。

```text
.opencode/skills/
├── README.md
├── official_document_render/
├── doubao-search/
├── nev-research/
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
