# research_apps — Research Applications（研究单元层）

独立研究型子项目（Research Applications / Research Programs）的 **canonical 归类层**，
对应冻结五层命名（根 README §1）的第 5 层。

## 定位（边界，务必遵守）

`research_apps/` **只负责归类**，不提供任何新的运行语义、Python namespace 或共享业务逻辑：

- 不定义 namespace：各项目保留自己的顶层包名/执行约定（如 `auto_launch`），不做
  `research_apps.auto_launch` 式包化重写。
- 不提供运行框架：项目各自拥有 CLI / Makefile / state / engine / contracts / gate / artifacts。
- 不被 Runtime 吸收：编排经 `mashang_runtime_v2` 的声明式 `feature_jobs` 调用，业务代码不复制进 runtime。

### 硬约束：不产生隐形共享层

**不得**在 `research_apps/` 下逐渐出现 `common/` / `utils/` / `shared/` 之类的共享目录。
第 4、5 个项目进来后若出现横向需求，一律沉淀到既有共享层：

```text
shared/          业务语义（operators / schema / loaders）
capabilities/    领域无关基础能力（OCR / Search / Notify / …）
mashang_workspace/  日常业务分析脚本与工具
```

跨 Research Application 的代码若复用于多个上层，先判断归属（业务语义→shared、领域原语→capabilities、
日常分析→workspace），再沉淀；不允许在本层新建"隐形公共底座"。

## 成员

| Research Application | 研究对象 |
|----------------------|----------|
| `MIIT/` | 工信部车型与申报研究 |
| `auto_launch/` | 新车上市与竞争动态研究 |
| `nev_apeal/` | 新能源用户体验研究 |
| 未来 `project_4/5` | 应符合本层判定准则（长期研究对象 + 自身 state/engine/contracts/gate/artifacts）再立项 |

## 编排接入约定

- 从仓库根统一启动；外部 CLI 用 `PYTHONPATH=research_apps` 使项目包可被 `python -m <app>.cli ...` 找到。
- 项目内若引用仓库根（`capabilities.*` / `.env` / `dataset`），用显式 repo-root 锚点，不依赖调用 cwd。
- `mashang_runtime_v2/config/runtime_v2_config.json` 的 `feature_jobs` 是编排入口
  （job 声明式 argv/cwd/参数白名单/artifact），项目内 state/产物路径相对各自目录。

## 沿革

2026-09：`research_apps/` 建立为 canonical 归类层，MIIT / auto_launch / nev_apeal 一并迁入
（原位于仓库根）；此前已完成 Runtime V2 Core Extraction 与 nev_apeal feature-job 编排 PoC。
