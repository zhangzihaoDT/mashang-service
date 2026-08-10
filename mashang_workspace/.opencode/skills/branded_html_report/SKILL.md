---
name: branded-html-report
description: 生成 mashang_workspace 专属的品牌化 HTML 数据报告，适用于汽车市场洞察、销量预测、锁单释放曲线、模型回测和经营分析报告。使用 Raccoon Research 视觉风格。
---

# branded_html_report

## 能力定位

将汽车经营分析、预测模型、回测评估、市场洞察等结果，渲染为具有 Raccoon Research / mashang 风格的 HTML 数据报告。

## 适用场景

- 销量预测报告
- 锁单释放曲线报告
- 模型回测报告
- 汽车市场洞察报告
- 经营复盘报告
- 用户反馈 / VOC 分析报告
- 车型结构、城市分布、渠道分析报告

## 不适用场景

- 政府正式申报书
- 通知/公文风材料
- Word / PDF 正式材料
- 简历
- PPT
- 纯命令行日志

如用户要求"正式通知风 Word/PDF"，应使用 repo-level `.opencode/skills/official_document_render` skill，调用 `scripts/render_official_document.py`。

## 默认输出位置

```
mashang_workspace/outputs/reports/
```

## 品牌资产路径

```
mashang_workspace/assets/brand/
├── brand_palette.json          # Raccoon Research 色彩调色板
├── raccoon_avatar_light.png    # 品牌头像（light 背景）
└── zihao_signature_transparent.png  # 品牌签名 wordmark
```

## 报告模板路径

```
mashang_workspace/templates/
├── report_base.html            # Jinja2 基模板（品牌 header/footer）
├── report_style.css            # 品牌 CSS（配色/卡片/表格/预测条）
├── report_generic.html         # 通用报告模板（KPI+表格+数据说明）
└── forecast_report.html        # 预测报告专用模板（预测条+场景表）
```

## 渲染脚本

```
mashang_workspace/utility_scripts/render_html_report.py
```

读取 Result Contract JSON（从 pipe 或 `--input`），使用 Jinja2 模板渲染为品牌化 HTML。

```bash
# 从 pipe 渲染
python runtime_scripts/daily_lock_count.py --format json \
  | python utility_scripts/render_html_report.py

# 从 JSON 文件渲染
python utility_scripts/render_html_report.py \
  --input outputs/tables/result.json \
  --output outputs/reports/lock_report.html \
  --title "锁单日报"

# 指定模板
python utility_scripts/render_html_report.py \
  --input contract.json \
  --template forecast_report.html
```

## 品牌风格规则

基于现有模板 (`report_style.css`) 和已生成报告：

- **品牌名**: Raccoon Research
- **配色**: Raccoon Research 调色板（ZH blue/cyan/gold/cream）— 见 `brand_palette.json`
- **头像**: `assets/brand/raccoon_avatar_light.png` — header 左侧
- **签名**: `assets/brand/zihao_signature_transparent.png` — footer
- **品牌语**: 用数据、AI 和一点点常识，研究复杂世界。
- **背景色**: `--zh-cream` (#FFF9EF) 暖白
- **卡片**: `--zh-card` (#FFFFFF) 白色圆角卡片
- **标题**: `--zh-deep-blue` (#06213D) 深蓝标题
- **正文**: `--zh-text` (#1F2D3D) 深灰
- **图表**: 优先使用 Plotly CDN 交互图表 + 表格数据
- **保持克制**: 数据报告风，不花哨，不公文

## 报告推荐结构

1. **Head — Brand** — 品牌头像 + Raccoon Research + 报告元信息
2. **Hero** — 核心结论或预测摘要
3. **Executive Summary** — 3–5 个关键指标卡片
4. **Main Analysis** — 趋势图、结构表、模型结果
5. **Interpretation** — 业务解读
6. **Methodology** — 数据口径、模型方法、假设说明
7. **Risk & Notes** — 风险提示
8. **Footer** — zihao_signature + 品牌语

## Agent 使用步骤

当用户要求"生成品牌化 HTML 报告""做成 Raccoon Research 风格报告""输出 HTML 数据报告""把分析结果包装成报告页"时：

1. 确认数据/分析结果来源。如果是分析脚本的 Result Contract JSON 输出，优先使用 `render_html_report.py` 渲染；
2. 检查是否已有对应 `outputs/tables/`、`outputs/charts/`、`outputs/reports/`；
3. 复用 `utility_scripts/render_html_report.py` + `templates/` 下的模板 + `assets/brand/` 的品牌资产；
4. 不要从零创造一套新风格。CSS、品牌资产和签名已有现成；
5. 生成 HTML 到 `outputs/reports/`；
6. 确保 `file://` 本地打开时 CSS 和图片能正常渲染（`static_prefix` 相对路径正确）；
7. 输出生成路径；
8. 如涉及图表，确认图表文件路径正确或 Plotly CDN 可访问；
9. 如涉及模型或预测，必须包含数据口径、模型假设和回测/误差说明；
10. 如果用户明确要求"正式通知风 Word/PDF"，切换到 repo-level `.opencode/skills/official_document_render` skill。

## 不涉及的行为

- 不生成 Word/PDF 正式材料
- 不生成政府公文风
- 不引入 repo-level `official_document_render` 逻辑
- 不删除已有 outputs/reports 下的任何报告
- 不改写现有模板或品牌资产

## 引用文件

| 文件 | 用途 |
|------|------|
| `utility_scripts/render_html_report.py` | 渲染入口脚本 |
| `templates/report_base.html` | Jinja2 品牌基模板 |
| `templates/report_style.css` | 品牌 CSS |
| `templates/report_generic.html` | 通用报告模板 |
| `templates/forecast_report.html` | 预测报告模板 |
| `assets/brand/raccoon_avatar_light.png` | 品牌头像 |
| `assets/brand/zihao_signature_transparent.png` | 品牌签名 |
| `assets/brand/brand_palette.json` | 品牌调色板 |
