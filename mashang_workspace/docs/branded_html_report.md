# Branded HTML Report — 品牌化 HTML 数据报告

## 报告风格

- 品牌：Raccoon Research
- 配色：清爽蓝白暖金调色板，定义见 `assets/brand/brand_palette.json`
- 背景：暖白 cream (#FFF9EF)
- 卡片：白色圆角 + 轻柔阴影
- 标题：深蓝 `--zh-deep-blue`
- 正文字体：系统字体栈（PingFang SC / Microsoft YaHei / sans-serif）
- 图表：优先 Plotly CDN 交互图表
- 整体：克制、数据报告风、可 file:// 本地打开

## 报告结构

1. **Header** — raccoon 头像 + Raccoon Research + 报告元信息
2. **Hero** — 核心结论摘要
3. **KPI 卡片网格** — 3–5 个关键指标
4. **分析正文** — 图表、表格、解读
5. **Methodology** — 数据口径、模型方法、假设
6. **Footer** — zihao_signature + 品牌语

## 品牌资产

```
mashang_workspace/assets/brand/
├── brand_palette.json
├── raccoon_avatar_light.png
└── zihao_signature_transparent.png
```

## 模板

```
mashang_workspace/templates/
├── report_base.html         # Jinja2 基模板
├── report_style.css         # 品牌 CSS
├── report_generic.html      # 通用报告
└── forecast_report.html     # 预测报告专用
```

## 输出路径

```
mashang_workspace/outputs/reports/
```

## 渲染方式

```bash
# 从 Result Contract JSON 渲染
python utility_scripts/render_html_report.py \
  --input outputs/tables/result.json \
  --output outputs/reports/report.html

# 从 pipe 渲染（分析脚本 → 报告）
python runtime_scripts/daily_lock_count.py --format json \
  | python utility_scripts/render_html_report.py
```

## 示例报告

- `outputs/reports/june_2026_forecast.html` — 预测报告
- `outputs/reports/lock_release_curve.html` — 释放曲线
- `outputs/reports/lock_predict_backtest.html` — 回测报告
- `outputs/reports/w24_weekend_analysis.html` — 周报分析
- `outputs/reports/ls8_city_distribution_2026-06-14.html` — 城市分布

## Skills Catalog 页面

workspace skills 目录页面，用于展示 mashang_workspace 下已沉淀的 workspace 级 Agent skills 能力体系。

- 输出路径：`outputs/reports/workspace_skills_catalog.html`
- 数据备份：`outputs/reports/workspace_skills_catalog.json`、`outputs/reports/workspace_skills_catalog.md`
- 页面用途：作为 Agent Harness 能力目录截图，展示分层体系和 skill 详情
- 生成方式：`python utility_scripts/build_workspace_skills_catalog.py` 或 `make build-workspace-skills-catalog`
- 输出文件：
  - `outputs/reports/workspace_skills_catalog.json` — 结构化数据
  - `outputs/reports/workspace_skills_catalog.md` — Markdown 文档
  - `outputs/reports/workspace_skills_catalog.html` — 品牌化 HTML 页面

## 不要做的事

- 不要用于正式申报书/通知/公文（用 repo root `official_document_render`）
- 不要用于 Word/PDF 输出
- 不要重新设计视觉风格
- 不要硬编码具体报告内容
- 不要直接编辑 `templates/` 或 `assets/brand/` 下的现有文件，除非有全局 style 更新
