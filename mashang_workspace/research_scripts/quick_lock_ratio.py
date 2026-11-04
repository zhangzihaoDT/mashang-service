#!/usr/bin/env python3
"""
绘制锁单累计同比分析图 (2025 vs 2024 和 2026 vs 2025)：
1. 仅展示累计同比曲线 (Cumulative YoY %)
2. X 轴以 2025 年日期为基准 (0~365天对齐)
3. 包含两条曲线：
   - 2025 累计同比 (相对于 2024)
   - 2026 累计同比 (相对于 2025)
4. Tooltip 显示：
   - 日期 (真实日期)
   - 当日锁单数 (Daily Count)
   - 累计锁单数 (Cumulative Count)
   - 累计同比 (Cumulative YoY)
5. 末端显示数值 Text 标记

新增模块：LS6 车型增程占比趋势 (2025 vs 2026)
- 仅筛选 series='LS6' 且 lock_time >= 2025-09-10
- 计算日增程占比 (Daily REEV Ratio, MA7 Smoothed)
- 添加 2025 和 2026 的年均值虚线 (Weighted Average)
- 2025 vs 2026 对比

样式遵循 skill/visualization-style 规范。
"""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys

import pandas as pd
import numpy as np
import plotly.graph_objects as go

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from utils.plotly_theme import ZH, apply_zh_theme, GRID_COLOR, ZERO_LINE, AXIS_LINE, AXIS_TEXT, AXIS_TITLE

from utils.paths import ensure_shared_on_path  # noqa: E402

ensure_shared_on_path()
from operators.product_attributes import product_type_of  # noqa: E402

COLOR_DARK = "#1F2933"

DEFAULT_INPUT = REPO_ROOT / "dataset" / "order_data.parquet"
_REPORT_DIR = _WS_ROOT / "outputs" / "reports"
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUT = _REPORT_DIR / "quick_lock_ratio.html"
BUSINESS_DEF_PATH = REPO_ROOT / "shared" / "schema" / "business_definition.json"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="绘制锁单累计同比分析图")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="输入 parquet 文件路径")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="输出 HTML 文件路径")
    return parser.parse_args()

def load_business_def() -> dict:
    """加载业务定义文件。"""
    if BUSINESS_DEF_PATH.exists():
        try:
            with open(BUSINESS_DEF_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载 business_definition.json 失败: {e}")
    else:
        print(f"⚠️ business_definition.json 不存在: {BUSINESS_DEF_PATH}")
    return {}

def resolve_power_types(product_names: pd.Series, biz_def: dict | None = None) -> pd.Series:
    """批量判定动力类型（增程/纯电/未知），统一走 shared 产品属性解析。"""
    biz_def = biz_def if biz_def is not None else (load_business_def() or {})
    names = product_names.fillna("").astype(str)
    return pd.Series(
        [product_type_of(name, biz_def) for name in names],
        index=product_names.index,
        dtype="object",
    )


def get_launch_date_for_product(product_name: str, biz_def: dict) -> date:
    """按 product_name 获取上市日期 — 统一走 series_group_logic + time_periods。

    字段语义（见 utils/monitors/launch.py、phase.py）：
      time_periods.{gen}.end = 上市日（不是预售结束日）；
      start = 预售开始日；finish = 权益结束日。

    本脚本不再自行维护「新一代→CM2 / 全新→CM1」的映射，一律由共享
    series_group_logic 归类代际（空格不敏感，支持 LS8/LS8Neo/DM2/CM3 等全部代际）。
    代际无法判定或上市日未确认时返回 None（调用方不得用预售日冒充上市日）。
    """
    if not biz_def:
        return None
    try:
        gen = _generation_of(product_name, biz_def)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 代际识别失败 ({product_name!r}): {e}")
        return None
    if not gen or gen == "其他":
        return None
    end = (biz_def.get("time_periods", {}).get(gen) or {}).get("end")
    if not end:
        return None
    try:
        return datetime.strptime(end, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _generation_of(product_name: str, biz_def: dict) -> str | None:
    """单个 product_name 的代际（series_group_logic），无额外映射。"""
    from operators.series_group_logic import apply_series_group_logic

    name = str(product_name).strip()
    if not name or name.lower() in {"nan", "none", "null"}:
        return None
    frame = pd.DataFrame({"product_name": [name]})
    return str(apply_series_group_logic(frame, biz_def)["series_group_logic"].iloc[0])

def get_product_type_from_name(product_name: str, biz_def: dict | None = None) -> str:
    """根据 product_name 判定动力类型（增程/纯电/未知）。

    统一走 shared 产品属性解析：代际 → 版本 → 动力。LS8 族（LS8/LS8Neo）以
    product_version_series 为唯一事实来源，不再用「含 52/66 即增程」的猜测规则。
    无法解析返回「未知」，不会被默认归为纯电。
    """
    try:
        if product_name is None:
            return "未知"
        name = str(product_name).strip()
        if len(name) == 0 or name.lower() in {"nan", "none", "null"}:
            return "未知"
        biz_def = biz_def if biz_def is not None else load_business_def()
        return product_type_of(name, biz_def)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 动力类型解析失败 ({product_name!r}): {e}")
        return "未知"

# ── 统一数据底座 ─────────────────────────────────────────────
# 口径：本报告所有「锁单数」= order_number 去重后的有效锁单事件。
# 审计结论（2026-10-29）：order_data 锁单行 271,462 行 / 271,462 个唯一 order_number，
# 无跨日期、跨版本、跨状态的重复，故 .size() 与 nunique 数值等价；此处统一为 nunique
# 仅作防御性规范化，不改变历史数值。

def prepare_lock_events(df: pd.DataFrame, biz_def: dict) -> pd.DataFrame:
    """一次性预计算锁单事件的全部派生维度（日期/年份/代际/版本/动力类型）。

    所有图共用同一份结果，避免逐个产品扫描全量数据。
    """
    from utils.paths import ensure_shared_on_path

    ensure_shared_on_path()
    from operators.series_group_logic import apply_series_group_logic
    from operators.product_attributes import resolve_product_attributes

    df = df.copy()
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()]
    if df.empty:
        return pd.DataFrame(columns=["order_number", "lock_date", "year",
                                     "series_group_logic", "product_version",
                                     "product_type", "series"])
    df = apply_series_group_logic(df, biz_def)
    attrs = resolve_product_attributes(df, biz_def)
    keep = [c for c in ("order_number", "series", "product_name") if c in df.columns]
    out = df[keep].copy()
    if "order_number" not in out.columns:
        out["order_number"] = range(len(out))
    out["lock_date"] = df["lock_time"].dt.date
    out["year"] = df["lock_time"].dt.year
    out["series_group_logic"] = attrs.generation.values
    out["product_version"] = attrs.version.values
    out["product_type"] = attrs.power_type.values
    if "series" not in out.columns:
        out["series"] = None
    for w in attrs.warnings:
        print(f"⚠️ {w}")
    return out.reset_index(drop=True)


def daily_lock_counts(events: pd.DataFrame) -> pd.Series:
    """全量日锁单数（order_number 去重）。"""
    return events.groupby("lock_date")["order_number"].nunique().sort_index()


def get_daily_counts(df: pd.DataFrame, year: int) -> pd.Series:
    """获取指定年份的日锁单数 Series (index=date, value=去重锁单数)。"""
    df_year = df[df["lock_time"].notna()]
    df_year = df_year[pd.to_datetime(df_year["lock_time"]).dt.year == year]
    if df_year.empty:
        return pd.Series(dtype=int)
    daily = df_year.groupby(pd.to_datetime(df_year["lock_time"]).dt.date)["order_number"].nunique()
    return daily.sort_index()

def align_to_2025_axis(daily_series: pd.Series, target_year: int) -> pd.DataFrame:
    """
    将指定年份的日数据对齐到 2025 年的日期轴 (MM-DD 对齐)。
    如果是闰年 (2024)，去掉 02-29。
    返回 DataFrame，index 为 2025 日期，包含 'raw_date', 'count'。
    """
    # 2025 全年日期序列 (365天)
    start_2025 = date(2025, 1, 1)
    end_2025 = date(2025, 12, 31)
    idx_2025 = pd.date_range(start_2025, end_2025, freq="D").date
    
    # 构建结果容器
    aligned_data = []
    
    for d_2025 in idx_2025:
        # 构造目标年份的同月同日
        try:
            d_target = date(target_year, d_2025.month, d_2025.day)
            # 查找该日的数据
            val = daily_series.get(d_target, 0)
            real_date = d_target
        except ValueError:
            # 只有当 target_year 非闰年但 d_2025 是 02-29 时才会异常
            # 但 2025 本身是平年，不会产生 02-29，所以这里几乎不会触发
            # 除非 d_2025 来源变了
            val = 0
            real_date = None 
            
        aligned_data.append({
            "axis_date": d_2025,
            "real_date": real_date,
            "count": val
        })
        
    return pd.DataFrame(aligned_data).set_index("axis_date")

def compute_yoy_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """计算核心绘图数据 (累计同比)。"""
    if "lock_time" not in df.columns:
        raise KeyError("缺少 lock_time 列")

    # 1. 预处理
    df = df.copy()
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()]
    
    # 2. 获取各年原始数据
    daily_2024 = get_daily_counts(df, 2024)
    daily_2025 = get_daily_counts(df, 2025)
    daily_2026 = get_daily_counts(df, 2026)
    
    # 3. 对齐数据到 2025 轴
    # 2025 本身 (作为 2025 vs 2024 的分子，2026 vs 2025 的分母)
    df_2025_aligned = align_to_2025_axis(daily_2025, 2025)
    
    # 2024 (作为 2025 vs 2024 的分母) - 闰年会自动跳过 02-29 (因为 axis_date 只有 02-28 和 03-01)
    df_2024_aligned = align_to_2025_axis(daily_2024, 2024)
    
    # 2026 (作为 2026 vs 2025 的分子)
    df_2026_aligned = align_to_2025_axis(daily_2026, 2026)
    
    # 4. 计算累计值和同比
    
    # --- Series 1: 2025 累计同比 (2025 vs 2024) ---
    cum_2025 = df_2025_aligned["count"].cumsum()
    cum_2024 = df_2024_aligned["count"].cumsum()
    
    yoy_2025 = (cum_2025 / cum_2024 - 1.0) * 100.0
    yoy_2025 = yoy_2025.replace([np.inf, -np.inf], np.nan)
    
    # --- Series 2: 2026 累计同比 (2026 vs 2025) ---
    cum_2026 = df_2026_aligned["count"].cumsum()
    # 注意：2026 是未来，需要截断到今天
    today = date.today()
    # 找到 2026 对应的 axis_date (即 2025-MM-DD)
    if today.year == 2026:
        cutoff_date = date(2025, today.month, today.day)
        mask_future = df_2026_aligned.index > cutoff_date
        yoy_2026 = (cum_2026 / cum_2025 - 1.0) * 100.0
        yoy_2026 = yoy_2026.replace([np.inf, -np.inf], np.nan)
        yoy_2026[mask_future] = np.nan
        # 对应的 count 和 cum 也设为 nan 以便 tooltip 不显示未来数据
        df_2026_aligned.loc[mask_future, "count"] = np.nan
        cum_2026[mask_future] = np.nan
    else:
        # 如果不是 2026 年 (比如回测)，全量计算或全量 NaN
        yoy_2026 = (cum_2026 / cum_2025 - 1.0) * 100.0
        
    # 5. 整合结果
    result = pd.DataFrame({
        "axis_date": df_2025_aligned.index,
        
        # 2025 曲线数据
        "date_2025": df_2025_aligned["real_date"],
        "daily_2025": df_2025_aligned["count"],
        "cum_2025": cum_2025,
        "yoy_2025": yoy_2025,
        
        # 2026 曲线数据
        "date_2026": df_2026_aligned["real_date"],
        "daily_2026": df_2026_aligned["count"],
        "cum_2026": cum_2026,
        "yoy_2026": yoy_2026
    })
    
    return result

# ── 图 3：LS6 增程占比 ─────────────────────────────────────────

# LS6 家族代际组（与 model_series_mapping.LS6 一致，避免裸 series 字段漏掉 CM3 等新代际）
LS6_GENERATIONS = ("CM0", "CM1", "CM2", "CM3")
LS6_LOCK_START = date(2025, 9, 10)


def compute_ls6_reev_metrics(events: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """LS6 日增程占比（MA7）。分子=增程锁单，分母=LS6 当日全部有效锁单。"""
    today = today or date.today()
    sub = events[(events["series_group_logic"].isin(LS6_GENERATIONS))
                 & (events["lock_date"] >= LS6_LOCK_START)]
    if sub.empty:
        return pd.DataFrame()
    idx = pd.date_range(LS6_LOCK_START, today, freq="D").date
    daily_total = sub.groupby("lock_date")["order_number"].nunique().reindex(idx, fill_value=0)
    daily_reev = (sub[sub["product_type"] == "增程"]
                  .groupby("lock_date")["order_number"].nunique().reindex(idx, fill_value=0))
    return _ratio_frame(idx, daily_total, daily_reev, "daily_reev")


# ── 图 4：LS8 66 Ultra 锁单占比 ────────────────────────────────

def compute_ls8_66_metrics(events: pd.DataFrame, biz_def: dict,
                           today: date | None = None) -> pd.DataFrame:
    """LS8 66 Ultra 锁单占比（MA7）。

    - 分子：product_version == '66 Ultra'（按版本字典精确识别，不再用 "66" 字符串包含）；
    - 分母：LS8 代际组（series_group_logic == 'LS8'）当日全部有效锁单，天然排除 NEO；
    - 起点：time_periods.LS8.end（上市日），不用预售结束日。
    """
    today = today or date.today()
    launch = _launch_date_for_generation(biz_def, "LS8")
    if launch is None:
        return pd.DataFrame()
    sub = events[(events["series_group_logic"] == "LS8") & (events["lock_date"] >= launch)]
    if sub.empty:
        return pd.DataFrame({"axis_date": pd.Series(dtype="object")})
    idx = pd.date_range(launch, today, freq="D").date
    daily_total = sub.groupby("lock_date")["order_number"].nunique().reindex(idx, fill_value=0)
    daily_66 = (sub[sub["product_version"] == "66 Ultra"]
                .groupby("lock_date")["order_number"].nunique().reindex(idx, fill_value=0))
    return _ratio_frame(idx, daily_total, daily_66, "daily_66")


def _launch_date_for_generation(biz_def: dict, gen: str) -> date | None:
    """time_periods.{gen}.end = 上市日。"""
    end = ((biz_def or {}).get("time_periods", {}).get(gen) or {}).get("end")
    if not end:
        return None
    try:
        return datetime.strptime(end, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _ratio_frame(idx, daily_total: pd.Series, daily_part: pd.Series, part_col: str) -> pd.DataFrame:
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (daily_part / daily_total) * 100.0
    ratio = ratio.replace([np.inf, -np.inf], np.nan)
    ratio_ma7 = ratio.rolling(window=7, min_periods=1).mean()
    total = int(daily_total.sum())
    part = int(daily_part.sum())
    avg_ratio = (part / total * 100.0) if total > 0 else 0.0
    return pd.DataFrame({
        "axis_date": idx,
        "daily_total": daily_total.values,
        part_col: daily_part.values,
        "ratio_raw": ratio.values,
        "ratio_ma7": ratio_ma7.values,
        "avg_ratio": [avg_ratio] * len(idx),
    })


# ── 图 5：增程车型配置结构 ────────────────────────────────────

def compute_reev_product_breakdown(events: pd.DataFrame, biz_def: dict,
                                   today: date | None = None) -> dict:
    """各增程 Product Name 在「当日增程总锁单」中的贡献占比（MA7, 2025 vs 2026）。

    指标定义（与计算一致）：
      分子 = 该 product_name 当日增程锁单数（order_number 去重）
      分母 = 当日所有增程车型锁单总数（order_number 去重）
      比值 = 该配置对增程总盘的贡献占比（不是「配置内部份额」）。

    重要语义提醒：各配置贡献占比之和通常 < 100%，因为
      (1) 上市前各配置被置为 NaN（不展示未上市代际）；
      (2) 但仍计入分母——分母是当日全量增程锁单。
    故某天有代际尚未上市时，图上留存曲线之和会低于 100%（如 LS8 上市日 2026-04-16 之前）。
    这是刻意设计，用于体现「新代际尚未贡献」；如需恒等于 100%，
    应改用「当日已上市增程配置」为分母，属口径变更，须单独确认。

    性能：一次 groupby 得到 (year, product_name, date) 计数，再按产品切片，
    不再逐个产品扫描全量数据。
    """
    today = today or date.today()
    reev = events[events["product_type"] == "增程"]
    if reev.empty:
        print("⚠️ 警告: 未找到任何增程车型数据")
        return {}

    reev = reev.dropna(subset=["product_name"])
    if reev.empty:
        return {}

    # 一次分组聚合：(年, 产品, 日) → 去重锁单数
    counts = (reev.groupby(["year", "product_name", "lock_date"])["order_number"]
                  .nunique().rename("n").reset_index())
    # 分母：各年逐日增程总锁单（按订单去重，与分子同口径）
    totals = (reev.groupby(["year", "lock_date"])["order_number"]
                  .nunique().rename("total").reset_index())

    years = [2025, 2026]
    axis_2025 = pd.date_range(date(2025, 1, 1), date(2025, 12, 31), freq="D").date
    by_product: dict[str, dict[int, pd.Series]] = {}
    by_product_total: dict[str, dict[int, pd.Series]] = {}

    for product, grp in counts.groupby("product_name"):
        by_product[product] = {
            y: grp.loc[grp["year"] == y].set_index("lock_date")["n"] for y in years
        }
    totals_by_year = {
        y: totals.loc[totals["year"] == y].set_index("lock_date")["total"] for y in years
    }

    def _cutoff(year: int) -> date:
        if year < today.year:
            return date(year, 12, 31)
        if year == today.year:
            return today
        return date(year, 12, 31)

    results: dict[str, pd.DataFrame] = {}
    line_cache: dict[int, tuple] = {}
    for year in years:
        end = _cutoff(year)
        full_idx = pd.date_range(date(year, 1, 1), end, freq="D").date
        s_total = totals_by_year[year].reindex(full_idx, fill_value=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio_total = (s_total / s_total.sum() * 100.0) if s_total.sum() else s_total * np.nan
        line_cache[year] = (full_idx, s_total, ratio_total)

    for product, per_year in by_product.items():
        cols = {}
        launch = get_launch_date_for_product(product, biz_def)
        for year in years:
            full_idx, s_total, _ = line_cache[year]
            s_prod = per_year[year].reindex(full_idx, fill_value=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                s_ratio = (s_prod / s_total) * 100.0
            s_ratio = s_ratio.replace([np.inf, -np.inf], np.nan)
            s_ma7 = s_ratio.rolling(window=7, min_periods=1).mean()
            aligned_prod = align_to_2025_axis(s_prod, year)["count"]
            aligned_ma7 = align_to_2025_axis(s_ma7, year)["count"]
            aligned_real = align_to_2025_axis(s_prod, year)["real_date"]
            if launch is not None:
                mask_pre = aligned_real.apply(lambda d: d < launch if isinstance(d, date) else False)
                aligned_ma7[mask_pre] = np.nan
                aligned_prod[mask_pre] = np.nan
            if year == today.year:
                mask_future = aligned_ma7.index > date(2025, today.month, today.day)
                aligned_ma7[mask_future] = np.nan
                aligned_prod[mask_future] = np.nan
            mask_missing = aligned_real.isna()
            aligned_ma7[mask_missing] = np.nan
            aligned_prod[mask_missing] = np.nan
            cols[f"date_{year}"] = aligned_real
            cols[f"count_{year}"] = aligned_prod
            cols[f"ratio_{year}"] = aligned_ma7

        results[product] = pd.DataFrame({"axis_date": axis_2025, **cols})

    return results

def build_ma7_figure(df: pd.DataFrame) -> go.Figure:
    """绘制 2025 vs 2026 锁单数 MA7 对比折线。"""
    fig = go.Figure()
    ma7_2025 = df['daily_2025'].rolling(7, min_periods=1).mean()
    ma7_2026 = df['daily_2026'].rolling(7, min_periods=1).mean()
    max_val = max(ma7_2025.max(), ma7_2026.max()) * 1.15

    fig.add_trace(go.Scatter(x=df['axis_date'], y=ma7_2025, mode='lines',
        name='2025 MA7', line=dict(color=ZH['own'], width=2)))
    fig.add_trace(go.Scatter(x=df['axis_date'], y=ma7_2026, mode='lines',
        name='2026 MA7', line=dict(color=ZH['event'], width=2)))

    fig.update_layout(
        title="锁单数 MA7 对比 (2025 vs 2026)",
        width=1300, height=380, hovermode='x unified',
        legend=dict(orientation='h', y=1.05, x=0),
        margin=dict(t=50, b=40, r=40, l=60),
        yaxis=dict(title='MA7 锁单数 (7日滚动平均)', range=[0, max_val]),
        xaxis=dict(title='日期 (对齐到 2025 年)'),
    )
    apply_zh_theme(fig)
    return fig


def build_figure(df: pd.DataFrame) -> go.Figure:
    """绘制累计同比图表。"""
    fig = go.Figure()
    
    # --- Helper: Create end label text array ---
    def create_end_label(series, color):
        text_list = [""] * len(series)
        last_valid_idx = series.last_valid_index()
        if last_valid_idx is not None:
            val = series[last_valid_idx]
            loc = series.index.get_loc(last_valid_idx)
            text_list[loc] = f"<b>{val:+.1f}%</b>"
        return text_list

    # --- Trace 1: 2025 累计同比 (基准) ---
    custom_data_2025 = np.stack((
        df["date_2025"].astype(str),
        df["daily_2025"].fillna(0),
        df["cum_2025"].fillna(0),
        df["yoy_2025"].fillna(0)
    ), axis=-1)
    
    text_2025 = create_end_label(df["yoy_2025"], ZH['own'])
    
    fig.add_trace(go.Scatter(
        x=df["axis_date"],
        y=df["yoy_2025"],
        name="2025 累计同比 (vs 2024)",
        mode="lines+text",
        text=text_2025,
        textposition="middle right",
        textfont=dict(color=ZH['own'], size=12),
        cliponaxis=False,
        line=dict(color=ZH['own'], width=2),
        customdata=custom_data_2025,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>" +
            "累计同比: %{y:.1f}%<br>" +
            "当日锁单: %{customdata[1]:.0f}<br>" +
            "累计锁单: %{customdata[2]:.0f}" +
            "<extra>2025</extra>"
        )
    ))
    
    # --- Trace 2: 2026 累计同比 (当前) ---
    custom_data_2026 = np.stack((
        df["date_2026"].apply(lambda x: str(x) if pd.notnull(x) else ""),
        df["daily_2026"].fillna(0),
        df["cum_2026"].fillna(0),
        df["yoy_2026"].fillna(0)
    ), axis=-1)
    
    text_2026 = create_end_label(df["yoy_2026"], ZH['event'])
    
    fig.add_trace(go.Scatter(
        x=df["axis_date"],
        y=df["yoy_2026"],
        name="2026 累计同比 (vs 2025)",
        mode="lines+text",
        text=text_2026,
        textposition="middle right",
        textfont=dict(color=ZH['event'], size=13),
        cliponaxis=False,
        line=dict(color=ZH['event'], width=3),
        customdata=custom_data_2026,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>" +
            "累计同比: %{y:.1f}%<br>" +
            "当日锁单: %{customdata[1]:.0f}<br>" +
            "累计锁单: %{customdata[2]:.0f}" +
            "<extra>2026</extra>"
        )
    ))
    
    # --- Layout ---
    fig.update_layout(
        title="锁单累计同比趋势对比 (2025 vs 2026)",
        xaxis=dict(
            title="日期 (对齐到 2025 年)",
            dtick="M1",
            tickformat="%m-%d"
        ),
        yaxis=dict(
            title="累计同比 (%)"
        ),
        legend=dict(
            bordercolor=ZH['neutral'],
            borderwidth=1,
            font=dict(color=ZH['neutral']),
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        ),
        hovermode="x unified",
        margin=dict(l=60, r=80, t=80, b=60),
        height=600
    )
    apply_zh_theme(fig)
    fig.add_hline(y=0, line_dash="dash", line_color=ZH['neutral'], opacity=0.5)
    return fig

def build_ls6_reev_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    def create_end_label(series, color):
        text = [""] * len(series)
        last_idx = pd.Series(series).last_valid_index()
        if last_idx is not None:
            val = series[last_idx]
            pos = list(range(len(series)))[-1]
            text[pos] = f"<b>{val:.1f}%</b>"
        return text
    custom_data = np.stack((
        pd.Series(df["daily_total"]).fillna(0),
        pd.Series(df["daily_reev"]).fillna(0),
        pd.Series(df["ratio_ma7"]).fillna(0)
    ), axis=-1)
    text_end = create_end_label(pd.Series(df["ratio_ma7"]), ZH['event'])
    fig.add_trace(go.Scatter(
        x=df["axis_date"],
        y=df["ratio_raw"],
        name="每日占比 (Raw)",
        mode="markers",
        marker=dict(color=COLOR_DARK, size=5, opacity=0.5),
        customdata=np.stack((
            pd.Series(df["daily_total"]).fillna(0),
            pd.Series(df["daily_reev"]).fillna(0),
            pd.Series(df["ratio_raw"]).fillna(0)
        ), axis=-1),
        hovertemplate=(
            "Raw 占比: %{customdata[2]:.1f}%<br>" +
            "当日总量: %{customdata[0]:.0f}<br>" +
            "当日增程: %{customdata[1]:.0f}" +
            "<extra></extra>"
        )
    ))
    fig.add_trace(go.Scatter(
        x=df["axis_date"],
        y=df["ratio_ma7"],
        name="LS6 日增程占比 (MA7)",
        mode="lines+text",
        text=text_end,
        textposition="middle right",
        textfont=dict(color=ZH['event'], size=12),
        cliponaxis=False,
        line=dict(color=ZH['event'], width=3),
        customdata=custom_data,
        hovertemplate=(
            "MA7 占比: %{y:.1f}%<br>" +
            "当日总量: %{customdata[0]:.0f}<br>" +
            "当日增程: %{customdata[1]:.0f}" +
            "<extra></extra>"
        )
    ))
    avg_ratio = float(df["avg_ratio"].iloc[0]) if "avg_ratio" in df.columns else 0.0
    fig.add_trace(go.Scatter(
        x=[df["axis_date"].min(), df["axis_date"].max()],
        y=[avg_ratio, avg_ratio],
        name=f"整体均值 ({avg_ratio:.1f}%)",
        mode="lines",
        line=dict(color=ZH['own'], width=1.5, dash="dash"),
        opacity=0.6,
        hoverinfo="skip"
    ))
    fig.update_layout(
        title="LS6 车型日增程占比趋势 (MA7, 2025-09-10 至今)",
        xaxis=dict(
            title="日期",
            dtick="M1",
            tickformat="%Y-%m-%d"
        ),
        yaxis=dict(
            title="日增程占比 (MA7, %)",
            range=[0, 105]
        ),
        legend=dict(
            bordercolor=ZH['neutral'],
            borderwidth=1,
            font=dict(color=ZH['neutral']),
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        ),
        hovermode="x unified",
        margin=dict(l=60, r=80, t=80, b=60),
        height=600
    )
    apply_zh_theme(fig)
    return fig

def build_ls8_66_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    custom_data = np.stack((
        pd.Series(df["daily_total"]).fillna(0),
        pd.Series(df["daily_66"]).fillna(0),
        pd.Series(df["ratio_ma7"]).fillna(0)
    ), axis=-1)
    def end_label(series):
        text = [""] * len(series)
        last = pd.Series(series).last_valid_index()
        if last is not None:
            text[-1] = f"<b>{series[last]:.1f}%</b>"
        return text
    text_end = end_label(pd.Series(df["ratio_ma7"]))
    fig.add_trace(go.Scatter(
        x=df["axis_date"], y=df["ratio_raw"],
        name="每日占比 (Raw)",
        mode="markers",
        marker=dict(color=COLOR_DARK, size=5, opacity=0.5),
        customdata=custom_data,
        hovertemplate=(
            "Raw 占比: %{y:.1f}%<br>当日总量: %{customdata[0]:.0f}<br>当日 66: %{customdata[1]:.0f}<extra></extra>"
        )
    ))
    fig.add_trace(go.Scatter(
        x=df["axis_date"], y=df["ratio_ma7"],
        name="LS8 66 Ultra 锁单占比 (MA7)",
        mode="lines+text",
        text=text_end, textposition="middle right",
        textfont=dict(color=ZH['event'], size=12), cliponaxis=False,
        line=dict(color=ZH['event'], width=3),
        customdata=custom_data,
        hovertemplate=(
            "MA7 占比: %{y:.1f}%<br>当日总量: %{customdata[0]:.0f}<br>当日 66: %{customdata[1]:.0f}<extra></extra>"
        )
    ))
    avg = float(df["avg_ratio"].iloc[0]) if "avg_ratio" in df.columns else 0.0
    fig.add_trace(go.Scatter(
        x=[df["axis_date"].min(), df["axis_date"].max()],
        y=[avg, avg],
        name=f"整体均值 ({avg:.1f}%)",
        mode="lines",
        line=dict(color=ZH['own'], width=1.5, dash="dash"), opacity=0.6, hoverinfo="skip"
    ))
    fig.update_layout(
        title="LS8 66 Ultra 锁单占比（MA7，上市至今）",
        xaxis=dict(title="日期", dtick="M1", tickformat="%Y-%m-%d"),
        yaxis=dict(title="66 Ultra 锁单占比 (MA7, %)", range=[0, 105]),
        legend=dict(bordercolor=ZH['neutral'], borderwidth=1, font=dict(color=ZH['neutral']),
                    orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        hovermode="x unified", margin=dict(l=60, r=80, t=80, b=60), height=600
    )
    apply_zh_theme(fig)
    return fig

def build_reev_product_breakdown_figure(metrics_dict: dict) -> go.Figure:
    """绘制所有增程车型各配置内部占比趋势图 (MA7 Smoothed, 2025 vs 2026)。"""
    fig = go.Figure()
    
    if not metrics_dict:
        return fig

    # 颜色列表
    colors = [
        "#174A7C", "#D79A36", "#2A9D8F", "#8E6BBE", "#E76F51", 
        "#5B8DEF", "#7ECDEB", "#D95F59", "#6B7280", "#06213D"
    ]
    
    # --- Helper: Create end label ---
    def create_end_label(series, color, opacity):
        text_list = [""] * len(series)
        last_valid_idx = series.last_valid_index()
        if last_valid_idx is not None:
            val = series[last_valid_idx]
            loc = series.index.get_loc(last_valid_idx)
            text_list[loc] = f"<b>{val:.1f}%</b>"
        return text_list

    # 1. 计算当前 (2026) 占比并排序 Top 2
    current_ratios = []
    for product_name, df in metrics_dict.items():
        s = df["ratio_2026"].dropna()
        if not s.empty:
            last_val = s.iloc[-1]
        else:
            last_val = 0.0
        current_ratios.append((product_name, last_val))
    
    # 降序排序，取 Top 2
    current_ratios.sort(key=lambda x: x[1], reverse=True)
    top2_products = {p[0] for p in current_ratios[:2]}
    
    # 获取 Top 1 和 Top 2 的具体名称，用于分配固定颜色
    top1_name = current_ratios[0][0] if len(current_ratios) >= 1 else None
    top2_name = current_ratios[1][0] if len(current_ratios) >= 2 else None
    
    print(f"🔝 Top 2 Products (Based on 2026 Latest Ratio): {top2_products}")

    for i, (product_name, df) in enumerate(metrics_dict.items()):
        # 颜色分配逻辑：
        # Top 1 -> ZH['event'] (Orange, 对应 2026 重点色)
        # Top 2 -> ZH['own'] (Blue, 对应 2025 基准色)
        # Others -> Cycle through colors list
        if product_name == top1_name:
            color = ZH['event']
        elif product_name == top2_name:
            color = ZH['own']
        else:
            color = colors[i % len(colors)]
        
        # 判断是否为 Top 2
        is_top2 = product_name in top2_products
        opacity = 1.0 if is_top2 else 0.2
        width = 3.0 if is_top2 else 1.5
        
        # --- Trace 2025 (Solid, Reduced Opacity) ---
        custom_data_2025 = np.stack((
            df["date_2025"].astype(str),
            df["count_2025"].fillna(0),
            df["ratio_2025"].fillna(0)
        ), axis=-1)
        
        fig.add_trace(go.Scatter(
            x=df["axis_date"],
            y=df["ratio_2025"],
            name=f"{product_name} (2025)",
            mode="lines",
            line=dict(color=color, width=width),  
            opacity=opacity * 0.5,  # 2025 降低透明度以突出 2026
            showlegend=False,  # 不显示 2025 图例
            legendgroup=product_name, # 属于同一图例组
            customdata=custom_data_2025,
            hovertemplate=(
                f"<b>{product_name} (2025)</b><br>" +
                "日期: %{customdata[0]}<br>" +
                "MA7 占比: %{y:.1f}%<br>" +
                "当日销量: %{customdata[1]:.0f}" +
                "<extra></extra>"
            )
        ))
        
        # --- Trace 2026 (Solid, Same Opacity) ---
        custom_data_2026 = np.stack((
            df["date_2026"].apply(lambda x: str(x) if pd.notnull(x) else ""),
            df["count_2026"].fillna(0),
            df["ratio_2026"].fillna(0)
        ), axis=-1)
        
        text_2026 = create_end_label(df["ratio_2026"], color, opacity)
        
        # 非 Top 2 的 text 也可以隐藏或者淡化
        mode_2026 = "lines+text" if is_top2 else "lines"
        
        fig.add_trace(go.Scatter(
            x=df["axis_date"],
            y=df["ratio_2026"],
            name=product_name,  # 图例只显示车型名称，不带年份
            mode=mode_2026,
            text=text_2026,
            textposition="middle right",
            textfont=dict(color=color, size=12),
            cliponaxis=False,
            line=dict(color=color, width=width),
            opacity=opacity,
            legendgroup=product_name, # 属于同一图例组
            customdata=custom_data_2026,
            hovertemplate=(
                f"<b>{product_name} (2026)</b><br>" +
                "日期: %{customdata[0]}<br>" +
                "MA7 占比: %{y:.1f}%<br>" +
                "当日销量: %{customdata[1]:.0f}" +
                "<extra></extra>"
            )
        ))

    # --- Layout ---
    fig.update_layout(
        title="增程车型各配置对增程总锁单的贡献占比 (分母=当日增程总锁单, MA7, Top2 Highlighted)",
        xaxis=dict(
            title="日期 (对齐到 2025 年)",
            dtick="M1",
            tickformat="%m-%d"
        ),
        yaxis=dict(
            title="日销量占比 (MA7, %)",
            range=[0, None]
        ),
        legend=dict(
            bordercolor=ZH['neutral'],
            borderwidth=1,
            font=dict(color=ZH['neutral']),
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        ),
        hovermode="x unified",
        margin=dict(l=60, r=80, t=80, b=60),
        height=600
    )
    apply_zh_theme(fig)
    return fig

CHART_TITLES = {
    1: "锁单数 MA7 对比 (2025 vs 2026)",
    2: "锁单累计同比趋势对比 (2025 vs 2026)",
    3: "LS6 车型日增程占比趋势 (MA7)",
    4: "LS8 66 Ultra 锁单占比（MA7）",
    5: "增程车型各配置对增程总锁单的贡献占比 (MA7, 2025 vs 2026)",
}


def _error_block(chart_no: int, title: str, exc: Exception) -> str:
    """图表失败时的可见错误块：不允许静默缺失。"""
    import html as _html
    import traceback as _tb

    detail = _html.escape("".join(_tb.format_exception_only(type(exc), exc)).strip())
    return (
        "<div style='border:2px solid #C0392B;background:#FDEDEC;padding:16px;margin:24px 0;"
        "border-radius:6px;font-family:-apple-system,sans-serif;'>"
        f"<h3 style='margin:0 0 8px;color:#C0392B;'>❌ 图 {chart_no} 生成失败：{_html.escape(title)}</h3>"
        f"<p style='margin:0 0 6px;color:#333;'>错误摘要：<code>{detail}</code></p>"
        "<p style='margin:0;color:#666;font-size:13px;'>该图表本次未生成，其余图表不受影响。</p>"
        "</div>"
    )


def run_chart(chart_no: int, label: str, fn, charts: dict, errors: dict):
    """执行单张图表；失败时记录错误并继续，不让整体报告中断。"""
    title = CHART_TITLES[chart_no]
    print(f"🔄 计算指标 {chart_no} ({label})...")
    try:
        fig = fn()
    except Exception as e:  # noqa: BLE001
        print(f"❌ 图 {chart_no} ({label}) 失败: {e}")
        import traceback
        traceback.print_exc()
        errors[chart_no] = (title, e)
        return
    if fig is None:
        errors[chart_no] = (title, RuntimeError("无可用数据（返回空结果）"))
        print(f"⚠️ 图 {chart_no} ({label}) 无可用数据")
        return
    charts[chart_no] = fig


def main():
    args = parse_args()
    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.exists():
        print(f"❌ 错误: 输入文件不存在 {input_path}")
        sys.exit(1)

    print(f"🔄 读取数据: {input_path}")
    try:
        df = pd.read_parquet(input_path)
    except Exception as e:
        print(f"❌ 读取 Parquet 失败: {e}")
        sys.exit(1)

    biz_def = load_business_def()
    print("🔄 预计算锁单事件维度 (代际/版本/动力/年份)...")
    try:
        events = prepare_lock_events(df, biz_def)
    except Exception as e:
        print(f"❌ 预计算失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    charts: dict = {}
    errors: dict = {}

    # 图 1/2 共用同一次累计同比计算（口径已统一为 order_number 去重）
    _yoy_cache: dict = {}

    def _yoy():
        if "df" not in _yoy_cache:
            _yoy_cache["df"] = compute_yoy_metrics(df)
        return _yoy_cache["df"]

    run_chart(1, "累计同比 MA7", lambda: build_ma7_figure(_yoy()), charts, errors)
    run_chart(2, "累计同比", lambda: build_figure(_yoy()), charts, errors)
    run_chart(3, "LS6 增程占比",
              lambda: build_ls6_reev_figure(compute_ls6_reev_metrics(events)), charts, errors)
    run_chart(4, "LS8 66 Ultra 锁单占比",
              lambda: build_ls8_66_figure(compute_ls8_66_metrics(events, biz_def)), charts, errors)
    run_chart(5, "增程配置贡献占比",
              lambda: build_reev_product_breakdown_figure(
                  compute_reev_product_breakdown(events, biz_def)), charts, errors)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"💾 保存报告: {out_path}")

    order = [1, 2, 3, 4, 5]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'><title>锁单分析报告</title></head><body>")
        first = True
        for no in order:
            if not first:
                f.write("<br><hr style='border:none;border-top:1px solid #E5EAF0;margin:24px 0;'><br>")
            first = False
            if no in charts:
                # 首个图内联 plotly.js，后续复用
                f.write(charts[no].to_html(full_html=False,
                                           include_plotlyjs="cdn" if no == 1 else False))
            else:
                title, exc = errors.get(no, (CHART_TITLES[no], RuntimeError("未执行")))
                f.write(_error_block(no, title, exc))
        f.write("</body></html>")

    if errors:
        print(f"⚠️ 完成，但有 {len(errors)} 张图失败: {sorted(errors)}（已写入 HTML 错误块）")
    else:
        print("✅ 完成!")


if __name__ == "__main__":
    main()
