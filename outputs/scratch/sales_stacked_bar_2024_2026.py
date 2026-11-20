"""临时代码：2024—2026 年销量堆叠柱状图（brand_monthly 上险销量）。

口径：
- 数据源 dataset/TP&MIX-ways/parquet/brand_monthly.parquet（乘用车上险数据）
- 年度 = date_month 的自然年合计（未年化），2026 年仅含 1–10 月
- 维度 = 品牌（brand），销量 = sales（辆）
- 选中品牌 = 2026 年累计销量 Top N（默认 15），其余品牌归入「其他品牌」
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "dataset" / "TP&MIX-ways" / "parquet" / "brand_monthly.parquet"
OUT_CHART = ROOT / "outputs" / "charts"
OUT_TABLE = ROOT / "outputs" / "tables"
YEARS = ["2024", "2025", "2026"]
TOP_N = 15

for fam in ("Noto Sans CJK SC", "Hiragino Sans GB", "PingFang SC", "Heiti TC"):
    if any(f.name == fam for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [fam, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False

brand = pd.read_parquet(SRC, columns=["date_month", "brand", "sales"])
brand = brand.assign(year=brand["date_month"].str[:4])
brand = brand[brand["year"].isin(YEARS)]

pivot = brand.pivot_table(index="brand", columns="year", values="sales", aggfunc="sum")
pivot = pivot.reindex(columns=YEARS).fillna(0.0)

top = pivot.sort_values("2026", ascending=False).head(TOP_N).index.tolist()
rest = pivot.drop(index=top)
rest_label = f"其他品牌（{len(rest)} 家）"
pivot = pd.concat([pivot.loc[top], rest.sum().to_frame(rest_label).T])

year_totals = pivot[YEARS].sum()

# ---- 表格输出 ----
table = (pivot[YEARS] / 1e4).round(2)
table.index.name = "品牌"
table = table.rename(columns={"2024": "2024年(万辆)", "2025": "2025年(万辆)", "2026": "2026年1-10月(万辆)"})
table.loc["合计"] = (year_totals / 1e4).round(2).values
OUT_TABLE.mkdir(parents=True, exist_ok=True)
table.to_csv(OUT_TABLE / "sales_stacked_2024_2026_brand.csv", encoding="utf-8-sig")
print(table.to_string())

# ---- 图表 ----
fig, ax = plt.subplots(figsize=(13, 7.6), dpi=200)
chart = (pivot[YEARS] / 1e4).T  # rows = year, cols = 品牌（万辆）
chart.index = ["2024 年", "2025 年", "2026 年\n(1–10 月)"]
colors = plt.get_cmap("tab20").colors
palette = ["#c8ccd4" if name.startswith("其他品牌") else colors[i % 20]
           for i, name in enumerate(chart.columns)]

bottom = pd.Series(0.0, index=chart.index)
for col, color in zip(chart.columns, palette):
    ax.bar(chart.index, chart[col], bottom=bottom, width=0.55, color=color,
           edgecolor="white", linewidth=0.8, label=col, zorder=3)
    bottom = bottom + chart[col]

for i, year in enumerate(chart.index):
    ax.text(i, bottom[year] + 4, f"{bottom[year]:,.0f} 万辆", ha="center", va="bottom",
            fontsize=11, fontweight="bold", zorder=5)

ax.set_ylabel("上险销量（万辆）", fontsize=11)
ax.set_xlabel("")
ax.set_title("2024—2026 年乘用车品牌上险销量堆叠对比", fontsize=17, fontweight="bold", pad=26)
ax.text(0.5, 1.02, f"Top {TOP_N} 品牌按 2026 年累计销量排序，其余归入「其他品牌」；2026 年为 1–10 月累计（未年化）",
        transform=ax.transAxes, ha="center", va="bottom", fontsize=10.5, color="#555555")
ax.set_ylim(0, float(bottom.max()) * 1.14)
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
ax.grid(axis="y", color="#e6e6e6", zorder=0)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

handles = [Patch(facecolor=c, edgecolor="white", label=l) for c, l in zip(palette, chart.columns)]
ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False,
          fontsize=9.5, ncol=1, title="品牌", title_fontsize=10.5)

plt.tight_layout()
OUT_CHART.mkdir(parents=True, exist_ok=True)
out_png = OUT_CHART / "sales_stacked_2024_2026_brand.png"
fig.savefig(out_png, bbox_inches="tight", facecolor="white")
print("saved:", out_png)
print(pd.DataFrame({"year": chart.index, "万辆": bottom.values}).to_string(index=False))
