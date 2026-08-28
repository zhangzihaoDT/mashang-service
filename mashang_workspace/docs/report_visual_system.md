# Report Visual System

## Overview

mashang-service 报告视觉体系，沉淀自两个成功案例：
- `pk_weekly_compare_ls8_ls9` — 表格型情报报告
- `竞争洞察A3人群流转` — 图表型情报报告

## CSS 组件库

所有可复用组件定义在 `templates/report_style.css`，通过 `<link rel="stylesheet" href="../../templates/report_style.css">` 引入。

### 页面外壳

| Class | 用途 |
|-------|------|
| `.report-page` | body class，浅灰背景 + 标准字体 |
| `.report-container` | 居中容器，max-width: 1360px |
| `.report-title` | h1 标题，蓝色左侧强调线 |
| `.report-subtitle` | 副标题/数据源说明 |
| `.report-section` | 每个图表/表格的外层容器 |
| `.section-title` | 章节标题 h2，蓝色左侧线 |
| `.section-note` | 图表说明文字 |
| `.chart-box` | Plotly 图表的白色卡片容器 |

### 摘要卡片

```html
<div class="summary-grid">
  <div class="summary-card">
    <div class="summary-value">核心数字</div>
    <div class="summary-label">指标名称</div>
    <div class="summary-hint">补充说明</div>
  </div>
</div>
```

### 表格

```html
<table class="report-table">
  <thead><tr><th>...</th></tr></thead>
  <tbody>
    <tr><td class="num">数字</td></tr>
    <tr class="section-row">分组行</tr>
  </tbody>
</table>
```

- 表头：浅灰底 + 深蓝文字 + 蓝色底边（无大面积深蓝）
- 斑马纹：`--zh-row-alt` (#FAFAFA) 极浅灰
- Hover：`--zh-row-hover` (#F3F6F8)
- 数字：`.num`（tabular-nums + 加粗）
- 排名：`.rank`（居中 + 浅灰文字）
- 正负 delta：`.delta-positive` / `.delta-negative`

### Badge

| Class | 背景 | 用途 |
|-------|------|------|
| `.badge` | 通用基类 | 半透描边 |
| `.badge-blue` | 浅蓝底 + 蓝边 | 常规标签 |
| `.badge-gold` | 浅金底 + 金边 | 重点标签 |
| `.badge-muted` | 浅灰底 + 灰边 | 次要标签 |
| `.badge-six-seat` | 浅金描边 | 6座标记，仅用于表格内 |
| `.badge-key` | 浅金描边 | 关键车型/事件标记 |

### Barcell（排名数据条）

```html
<div class="barcell"><div class="bar" style="width:60%;"></div><div class="txt">数据</div></div>
<div class="barcell"><div class="bar six" style="width:40%;"></div><div class="txt">数据</div></div>
```

- Track：极浅灰 #F8FAFC + 圆角
- Bar：左 3px 强调线 + 低透明填充
- `.bar`：蓝色（本品）| `.bar.six`：金色（事件）| `.bar.positive`：绿色 | `.bar.negative`：红色
- txt：加粗 + tabular-nums

## Plotly 图表主题

统一主题函数在 `utils/plotly_theme.py`：

```python
from utils.plotly_theme import ZH, apply_zh_theme, get_series_color

# 按业务角色取色
color = get_series_color('own')           # 本品
color = get_series_color('event')         # 事件车型
color = get_series_color('competitor', 0) # 普通竞品（轮循 steel/sage/mauve/sky_muted）
color = get_series_color('ash')           # 参考线

# 应用统一视觉
apply_zh_theme(fig)

# 双Y轴零线对齐
align_dual_zero(fig, y1=y1_data, y2=y2_data)
```

### 颜色语义

| Role | Hex | 使用场景 |
|------|-----|---------|
| `own` | #174A7C | 本品、主指标、主结论 |
| `event` | #D79A36 | 事件车型、关键冲击、重点高亮 |
| `steel` / `sage` / `mauve` / `sky_muted` | #4F6F82 / #7A8B76 / #7D6A8E / #6A93B8 | 普通竞品轮循 |
| `ash` | #9AA3AD | 参考线、均值、累计线 |
| `positive` / `negative` | #2A9D8F / #D95F59 | 正负变化 |

### 主题配置

| 属性 | 值 |
|------|-----|
| paper_bgcolor | #FFFFFF |
| plot_bgcolor | #FFFFFF |
| gridcolor | #EEF2F6 |
| axis linecolor | #C7CDD4 |
| yaxis zerolinecolor | #6B7280, width=2 |
| xaxis zeroline | False |
| yaxis zeroline | True |
| tickfont color | #5F6B7A |
| axis title color | #374151 |

## 约束规则

1. 报告优先使用 `report_style.css`，不在脚本内重复写整套 CSS。
2. 允许保留少量报告专属 CSS（仅 layout 或特殊业务样式），不重复定义全局 color token。
3. Plotly 图表调用 `apply_zh_theme`，颜色通过 `get_series_color(role)` 分配。
4. 颜色按业务角色分配，不按 series 顺序机械分配。
5. 表格明细优先 HTML table，趋势/关系/分布才用 Plotly。
6. 普通背景、斑马纹、表格分栏不得使用浅蓝（`--zh-blue-100`）。
7. 金色只用于重点、事件、警示、6座标记、关键进度条。
8. y=0 zeroline 对净流入/净流出/正负变化图表必须显著。
9. **静态资源路径约定**：报告落在 `mashang_workspace/outputs/reports/`，模板/资产在 `mashang_workspace/templates/` 与 `assets/`，因此 `<link>/<img>` 必须用 **`../../templates/report_style.css`、`../../assets/brand/...`**（`report_base.html` 的 `static_prefix` 传 `../..`）。用 `../` 会指向不存在的 `outputs/templates/`，导致 CSS 不渲染——`market_state_observation` 曾踩此坑。
9. 超过 6 个系列时，高亮本品/事件车型，其余竞品降为低饱和灰蓝或透明度。
