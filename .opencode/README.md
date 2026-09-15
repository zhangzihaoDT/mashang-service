# OpenCode Control Plane

项目级 OpenCode 配置的控制面索引：

```text
.opencode/
├── skills/         能力本身
├── commands/       显式调用入口
├── integrations/   外部能力如何接入本项目
├── verification/   Verification Scope Contract（验证范围契约）
└── README.md       控制面索引
```

## Skills

- `.opencode/skills/README.md`
- `.opencode/skills/official_document_render/`
- `.opencode/skills/doubao-search/`
- `.opencode/skills/nev-research/`
- `.opencode/skills/mashang-diagram/` → 项目自有 diagram 路由 Skill
- `.opencode/skills/diagram-design` → 独立 upstream checkout（只读消费）

## Commands

- `.opencode/commands/diagram.md` → `/diagram`

## Integrations

- `.opencode/integrations/diagram-design.md`

## Verification

- `.opencode/verification/README.md` → Verification Scope Contract：把「充分验证」定义为「命中改动范围的验证」，避免测试范围膨胀。
- `make verify-scope` / `make verify` / `make verify-all`
