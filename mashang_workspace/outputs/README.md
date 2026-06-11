# Outputs — 输出目录规范

## 目录结构

```
outputs/
├── reports/          # HTML / Markdown 分析报告
│   ├── release_curve_analysis.html
│   ├── atp_report.html
│   └── daily_lock_summary.md
├── charts/           # PNG / SVG / HTML 图表
│   ├── lock_trend.html
│   ├── city_distribution.png
│   └── model_share_pie.svg
└── tables/           # CSV / Parquet / XLSX 结果表
    ├── lock_by_model_2026-06-10.csv
    ├── city_distribution_2026-06.csv
    └── predicted_locks.parquet
```

## 命名规范

建议文件命名包含以下信息：

```
{主题}_{日期}_{口径}.{扩展名}
```

示例:
- `lock_by_model_2026-06-10_daily.csv`
- `city_distribution_2026-06_monthly.csv`
- `atp_2026-05_report.html`

## 使用说明

- **reports/**: 存放可发布的完整分析报告 (HTML/MD)
- **charts/**: 存放可视化图表 (PNG/SVG/HTML)，供报告引用
- **tables/**: 存放结构化数据表 (CSV/Parquet/XLSX)，供进一步分析

## 注意事项

- 临时分析文件建议使用 `scratch/` 或 `test/` 目录
- 稳定输出的文件才放入 `outputs/`
- 大文件 (>50MB) 建议用 Parquet 而非 CSV
