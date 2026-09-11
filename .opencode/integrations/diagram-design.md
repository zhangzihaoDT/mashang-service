# diagram-design Integration

## Architecture

`diagram-design` 保持独立 upstream checkout，`mashang-service` 通过项目级 relative symlink 消费它：

```text
/Users/zihao_/Documents/github/diagram-design/
└── skills/diagram-design/
    ├── SKILL.md
    ├── references/
    └── scripts/
            ↑ relative symlink

mashang-service/.opencode/
├── skills/
│   └── diagram-design -> ../../../diagram-design/skills/diagram-design
├── commands/
│   └── diagram.md
└── integrations/
    └── diagram-design.md
```

目录职责：

- `skills/`：能力本身。
- `commands/`：显式调用入口。
- `integrations/`：外部能力如何接入本项目。
- `.opencode/README.md`：控制面索引。

## Call Chain

```text
Research outputs
    ↓
/diagram
    ↓
diagram-design Skill
    ↓
HTML / SVG artifact
```

在 `mashang-service` 中，Research outputs 主要来自 `research_apps/*` 和
`mashang_workspace/outputs/`。`/diagram` 只负责保留用户请求并转交 Skill；图形类型、视觉规则、style-guide gate 和 artifact 生成规则均以 upstream Skill 为准。

## Current Policy

- upstream checkout：`/Users/zihao_/Documents/github/diagram-design`
- consumer：`.opencode/skills/diagram-design`
- command：`.opencode/commands/diagram.md`
- project marker：`.diagram-design`
- typography profile：`~/.diagram-design/profiles/mashang-research.md`
- artifact target：`mashang_workspace/outputs/`

当前 Profile 只冻结本机 `Noto Sans CJK SC` 字体策略；颜色、布局、spacing、shadow、radius 和 diagram 类型规则继续继承 upstream 默认值。

## Scope

- 不修改 diagram-design upstream 源码。
- 不在项目中复制 upstream Skill。
- 不安装全局 Skill 或全局 Command。
- 不通过该 integration 文档创建 Agent。
- Profile 与 marker 遵循 diagram-design 原生解析机制。
