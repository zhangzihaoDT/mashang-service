# diagram-design Integration

## Architecture

`diagram-design` 保持独立 upstream checkout，`mashang-service` 通过项目级 relative symlink 消费它：

```text
/Users/zihao_/Documents/github/diagram-design/
└── skills/diagram-design/
    ├── SKILL.md
    ├── references/
    └── scripts/
            ↑ relative symlink（只读消费）

mashang-service/
├── capabilities/diagram/           # 项目自有图表能力（数据契约 + 几何 + 渲染）
└── .opencode/
    ├── skills/
    │   ├── diagram-design -> ../../../diagram-design/skills/diagram-design
    │   └── mashang-diagram/        # 项目自有派生路由 Skill（实体目录）
    │       ├── SKILL.md
    │       └── references/
    │           └── type-milestone-dumbbell.md
    ├── commands/
    │   └── diagram.md
    └── integrations/
        └── diagram-design.md
```

目录职责：

- `skills/`：能力本身；upstream 只读，`mashang-diagram` 为自有路由层。
- `capabilities/diagram/`：自有图表类型的数据契约与确定性渲染（几何在这里，不在 Skill）。
- `commands/`：显式调用入口。
- `integrations/`：外部能力如何接入本项目。
- `.opencode/README.md`：控制面索引。

## Call Chain

```text
Research outputs
    ↓
/diagram
    ↓
mashang-diagram（项目自有派生路由 Skill）
    ↓
识别 visual type
    ├─ 自有类型 → capabilities/diagram（Capability：数据契约 + 几何 + 渲染）
    └─ 通用类型 → diagram-design（upstream：类型规则 + 视觉规则 + self_check）
    ↓
HTML / SVG artifact
```

在 `mashang-service` 中，Research outputs 主要来自 `research_apps/*` 和
`mashang_workspace/outputs/`。

分层职责：

- **Capability 决定**「这是什么图、数据怎么算、几何怎么画」——`capabilities/diagram`。
- **Skill 决定**「什么时候该用它、怎么放进研究报告、采用什么视觉皮肤」——`mashang-diagram` 负责识别与路由，upstream `diagram-design` 负责通用类型规则与视觉规则。
- 路由层**不写死**任何调色板；图表皮肤通过 capability 的 `DumbbellTheme` 注入。

`/diagram` 只负责保留用户请求并转交 `mashang-diagram`；通用类型的图形类型、视觉规则、style-guide gate 和 artifact 生成规则以 upstream Skill 为准。

## Current Policy

- upstream checkout：`/Users/zihao_/Documents/github/diagram-design`
- consumer（upstream，只读）：`.opencode/skills/diagram-design`
- 项目自有派生路由：`.opencode/skills/mashang-diagram`
- 自有图表能力：`capabilities/diagram`
- command：`.opencode/commands/diagram.md`（→ `mashang-diagram`）
- project marker：`.diagram-design`
- typography profile：`~/.diagram-design/profiles/mashang-research.md`
- artifact target：`mashang_workspace/outputs/`

当前 Profile 只冻结本机 `Noto Sans CJK SC` 字体策略；颜色、布局、spacing、shadow、radius 和 diagram 类型规则继续继承 upstream 默认值。

## Scope

- 不修改 diagram-design upstream 源码。
- 不在项目中复制 upstream Skill；`mashang-diagram` 是派生**路由层**，不内联 upstream type references。
- 项目自有图表类型（当前：Milestone Temporal Dumbbell）在 `capabilities/diagram` 实现，type 规范放在 `mashang-diagram/references/`，不写入 upstream 类型表。
- 不安装全局 Skill 或全局 Command。
- 不通过该 integration 文档创建 Agent。
- Profile 与 marker 遵循 diagram-design 原生解析机制。
