import pandas as pd


class StatisticsTool:
    def perform_statistics(self, request: dict, input_df: pd.DataFrame) -> dict | str:
        stat_type = (request or {}).get("type")
        if stat_type == "weekly_decline_ratio":
            return self._weekly_decline_ratio(request, input_df)
        if stat_type == "daily_threshold_count":
            return self._daily_threshold_count(request, input_df)
        if stat_type == "monthly_mean":
            return self._monthly_mean(request, input_df)
        if stat_type == "daily_mean":
            return self._daily_mean(request, input_df)
        if stat_type == "daily_mean_median":
            return self._daily_mean_median(request, input_df)
        if stat_type == "trend_summary":
            return self._trend_summary(request, input_df)
        if stat_type == "contribution_summary":
            return self._contribution_summary(request, input_df)
        if stat_type == "category_share":
            return self._category_share(request, input_df)
        if stat_type == "daily_percentile_rank":
            return self._daily_percentile_rank(request, input_df)
        if stat_type == "weekend_percentile_rank":
            return self._weekend_percentile_rank(request, input_df)
        if stat_type == "weekday_percentile_rank":
            return self._weekday_percentile_rank(request, input_df)
        return f"不支持的统计类型: {stat_type}"

    @staticmethod
    def _weekly_decline_ratio(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        weekdays = StatisticsTool._normalize_weekdays(request.get("weekdays"))
        window_weeks = request.get("window_weeks")
        if isinstance(window_weeks, str) and window_weeks.isdigit():
            window_weeks = int(window_weeks)
        if not isinstance(window_weeks, int) or window_weeks <= 0:
            window_weeks = 10

        series_cols = {"week_start", "numerator", "denominator", "lock_rate", "delta", "is_decline"}
        if bool(request.get("series_input")):
            if not series_cols.issubset(set(input_df.columns)):
                return f"统计分析缺少必要列: {', '.join(sorted(series_cols))}"
            grouped = input_df.copy()
        else:
            time_field = request.get("time_field") or "Assign Time 年/月/日"
            numerator_alias = request.get("numerator_alias") or "门店当日锁单数"
            denominator_alias = request.get("denominator_alias") or "门店线索数"
            grouped = StatisticsTool.build_weekly_wow_series(
                input_df=input_df,
                time_field=time_field,
                numerator_alias=numerator_alias,
                denominator_alias=denominator_alias,
                weekdays=weekdays,
                window_weeks=window_weeks,
            )
            if isinstance(grouped, str):
                return grouped

        grouped = grouped.tail(window_weeks).reset_index(drop=True)
        grouped["is_decline"] = grouped["is_decline"].astype(bool)
        decline_count = int(grouped["is_decline"].sum())
        total_weeks = int(len(grouped))
        ratio = 0.0 if total_weeks == 0 else (decline_count / total_weeks)
        weekly_rows: list[dict] = []
        for _, row in grouped.iterrows():
            lock_rate = row.get("lock_rate")
            delta = row.get("delta")
            weekly_rows.append(
                {
                    "week_start": row["week_start"].strftime("%Y-%m-%d"),
                    "numerator": float(row["numerator"]),
                    "denominator": float(row["denominator"]),
                    "lock_rate": None if pd.isna(lock_rate) else float(lock_rate),
                    "delta": None if pd.isna(delta) else float(delta),
                    "is_decline": bool(row["is_decline"]),
                }
            )

        return {
            "type": "weekly_decline_ratio",
            "window_weeks": int(window_weeks),
            "weekdays": weekdays,
            "decline_weeks": decline_count,
            "total_weeks": total_weeks,
            "decline_ratio": ratio,
            "weekly_rows": weekly_rows,
        }

    @staticmethod
    def _normalize_weekdays(weekdays: list[int] | None) -> list[int]:
        if not isinstance(weekdays, list) or not weekdays:
            weekdays = [4, 5]
        normalized = [int(w) for w in weekdays if isinstance(w, (int, float, str)) and str(w).isdigit()]
        normalized = [w for w in normalized if 1 <= int(w) <= 7]
        normalized = sorted(list(dict.fromkeys(int(w) for w in normalized)))
        if not normalized:
            return [4, 5]
        return normalized

    @staticmethod
    def _coerce_positive_int(value: object, default: int) -> int:
        try:
            coerced = int(value)
        except Exception:
            return default
        return coerced if coerced > 0 else default

    @staticmethod
    def _serialize_number(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _prepare_daily_series(
        input_df: pd.DataFrame,
        time_field: str,
        metric_alias: str,
        window_days: int,
        date_start_raw: str | None = None,
        date_end_raw: str | None = None,
    ) -> pd.DataFrame | str:
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .tail(int(window_days))
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用日期数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))
        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        series = grouped.set_index("date")["value"].reindex(date_index, fill_value=0.0)
        series_df = series.reset_index()
        series_df.columns = ["date", "value"]
        return series_df

    @staticmethod
    def _calculate_linear_slope(values: list[float]) -> float:
        count = len(values)
        if count <= 1:
            return 0.0
        x_mean = (count - 1) / 2.0
        y_mean = sum(values) / float(count)
        numerator = sum((idx - x_mean) * (value - y_mean) for idx, value in enumerate(values))
        denominator = sum((idx - x_mean) ** 2 for idx in range(count))
        if denominator == 0:
            return 0.0
        return float(numerator / denominator)

    @staticmethod
    def _current_streak(changes: list[float | None]) -> tuple[str, int]:
        streak_direction = "flat"
        streak_length = 0
        for change in reversed(changes):
            if change is None or pd.isna(change) or change == 0:
                if streak_length == 0:
                    streak_direction = "flat"
                    streak_length = 1
                break
            direction = "up" if change > 0 else "down"
            if streak_length == 0:
                streak_direction = direction
                streak_length = 1
                continue
            if direction != streak_direction:
                break
            streak_length += 1
        return streak_direction, streak_length

    @staticmethod
    def build_weekly_wow_series(
        input_df: pd.DataFrame,
        time_field: str,
        numerator_alias: str,
        denominator_alias: str,
        weekdays: list[int],
        window_weeks: int,
    ) -> pd.DataFrame | str:
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if numerator_alias not in input_df.columns or denominator_alias not in input_df.columns:
            return f"统计分析缺少必要列: {numerator_alias} / {denominator_alias}"

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        normalized_weekdays = StatisticsTool._normalize_weekdays(weekdays)
        df["_weekday"] = df[time_field].dt.dayofweek + 1
        df = df[df["_weekday"].isin(normalized_weekdays)]
        if df.empty:
            return "筛选周内日后无数据。"

        df["week_start"] = (df[time_field] - pd.to_timedelta(df[time_field].dt.dayofweek, unit="D")).dt.normalize()
        grouped = (
            df.groupby("week_start", as_index=False)
            .agg({numerator_alias: "sum", denominator_alias: "sum"})
            .sort_values("week_start")
            .tail(int(window_weeks))
            .reset_index(drop=True)
        )
        grouped = grouped.rename(columns={numerator_alias: "numerator", denominator_alias: "denominator"})
        grouped["lock_rate"] = grouped.apply(
            lambda r: None if float(r["denominator"]) == 0.0 else float(r["numerator"]) / float(r["denominator"]),
            axis=1,
        )
        grouped["delta"] = grouped["lock_rate"] - grouped["lock_rate"].shift(1)
        grouped["is_decline"] = grouped["delta"].apply(lambda x: bool(pd.notna(x) and x < 0))
        return grouped[["week_start", "numerator", "denominator", "lock_rate", "delta", "is_decline"]]

    @staticmethod
    def _daily_threshold_count(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        op = request.get("op")
        if op not in {">", ">=", "<", "<=", "==", "!="}:
            op = ">"

        threshold = request.get("threshold")
        try:
            threshold = float(threshold)
        except Exception:
            threshold = 0.0

        window_days = request.get("window_days")
        if isinstance(window_days, str) and window_days.isdigit():
            window_days = int(window_days)
        if not isinstance(window_days, int) or window_days <= 0:
            window_days = 30

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .tail(window_days)
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用日期数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))
        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        series = grouped.set_index("date")["value"].reindex(date_index, fill_value=0.0)

        def _match(v: float) -> bool:
            if op == ">":
                return v > threshold
            if op == ">=":
                return v >= threshold
            if op == "<":
                return v < threshold
            if op == "<=":
                return v <= threshold
            if op == "==":
                return v == threshold
            return v != threshold

        matched = series.apply(_match)
        matched_days = int(matched.sum())
        total_days = int(len(series))
        matched_ratio = 0.0 if total_days == 0 else (matched_days / total_days)

        daily_rows: list[dict] = []
        for date, value in series.items():
            daily_rows.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "value": float(value),
                    "matched": bool(_match(float(value))),
                }
            )

        return {
            "type": "daily_threshold_count",
            "window_days": int(window_days),
            "op": op,
            "threshold": float(threshold),
            "metric_alias": metric_alias,
            "matched_days": matched_days,
            "total_days": total_days,
            "matched_ratio": matched_ratio,
            "daily_rows": daily_rows,
        }

    @staticmethod
    def _monthly_mean(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["month"] = df[time_field].dt.to_period("M").astype(str)
        monthly = (
            df.groupby("month", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("month")
            .reset_index(drop=True)
        )
        if monthly.empty:
            return "统计分析在窗口内无可用月数据。"

        monthly["value"] = monthly[metric_alias].astype(float)
        month_count = len(monthly)
        monthly_mean = float(monthly["value"].mean()) if month_count else 0.0
        total = float(monthly["value"].sum()) if month_count else 0.0

        monthly_rows: list[dict] = []
        for _, row in monthly.iterrows():
            monthly_rows.append({
                "month": str(row["month"]),
                "value": float(row["value"]),
            })

        return {
            "type": "monthly_mean",
            "metric_alias": metric_alias,
            "monthly_mean": monthly_mean,
            "total": total,
            "month_count": month_count,
            "monthly_rows": monthly_rows,
        }

    @staticmethod
    def _daily_mean(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_days = request.get("window_days")
        if isinstance(window_days, str) and window_days.isdigit():
            window_days = int(window_days)
        if not isinstance(window_days, int) or window_days <= 0:
            window_days = 30

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .tail(window_days)
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用日期数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))
        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        series = grouped.set_index("date")["value"].reindex(date_index, fill_value=0.0)
        total_days = int(len(series))
        daily_mean = float(series.mean()) if total_days else 0.0
        daily_rows: list[dict] = []
        for date, value in series.items():
            daily_rows.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "value": float(value),
                }
            )

        return {
            "type": "daily_mean",
            "window_days": int(window_days),
            "metric_alias": metric_alias,
            "daily_mean": daily_mean,
            "total_days": total_days,
            "daily_rows": daily_rows,
        }

    @staticmethod
    def _daily_mean_median(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_days = request.get("window_days")
        if isinstance(window_days, str) and window_days.isdigit():
            window_days = int(window_days)
        if not isinstance(window_days, int) or window_days <= 0:
            window_days = 30

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .tail(window_days)
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用日期数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))
        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        series = grouped.set_index("date")["value"].reindex(date_index, fill_value=0.0)
        total_days = int(len(series))
        daily_mean = float(series.mean()) if total_days else 0.0
        daily_median = float(series.median()) if total_days else 0.0

        daily_rows: list[dict] = []
        for date, value in series.items():
            daily_rows.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "value": float(value),
                }
            )

        return {
            "type": "daily_mean_median",
            "window_days": int(window_days),
            "metric_alias": metric_alias,
            "daily_mean": daily_mean,
            "daily_median": daily_median,
            "total_days": total_days,
            "daily_rows": daily_rows,
        }

    @staticmethod
    def _trend_summary(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field") or request.get("date_col")
        metric_alias = request.get("metric_alias") or request.get("value_col")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"

        window_days = StatisticsTool._coerce_positive_int(
            request.get("window_days") or request.get("window"),
            10,
        )
        series_df = StatisticsTool._prepare_daily_series(
            input_df=input_df,
            time_field=time_field,
            metric_alias=metric_alias,
            window_days=window_days,
            date_start_raw=request.get("date_start"),
            date_end_raw=request.get("date_end"),
        )
        if isinstance(series_df, str):
            return series_df

        series_df = series_df.tail(window_days).reset_index(drop=True)
        series_df["pct_change"] = series_df["value"].pct_change()
        series_df["pct_change"] = series_df["pct_change"].replace([float("inf"), float("-inf")], pd.NA)
        series_df["delta"] = series_df["value"].diff()

        values = series_df["value"].astype(float)
        first = float(values.iloc[0])
        latest = float(values.iloc[-1])
        mean_value = float(values.mean())
        median_value = float(values.median())
        std_value = float(values.std()) if len(values) > 1 else 0.0
        cv = None if mean_value == 0 else float(std_value / mean_value)
        total_change = None if first == 0 else float((latest - first) / first)
        latest_vs_mean = None if mean_value == 0 else float((latest - mean_value) / mean_value)
        avg_daily_change = float(series_df["delta"].dropna().mean()) if len(series_df) > 1 else 0.0
        slope = StatisticsTool._calculate_linear_slope(values.tolist())
        direction = "flat"
        if slope > 0:
            direction = "up"
        elif slope < 0:
            direction = "down"

        valid_pct = pd.to_numeric(series_df["pct_change"], errors="coerce").dropna()
        change_volatility = float(valid_pct.std()) if len(valid_pct) > 1 else 0.0
        latest_rank = int((values <= latest).sum())
        latest_percentile_rank = float(latest_rank / len(values)) if len(values) else 0.0
        if latest_percentile_rank >= 2.0 / 3.0:
            latest_position = "high"
        elif latest_percentile_rank <= 1.0 / 3.0:
            latest_position = "low"
        else:
            latest_position = "mid"

        change_labels: list[str] = []
        for change in series_df["pct_change"].tail(3).tolist():
            if change is None or pd.isna(change):
                change_labels.append("flat")
            elif change > 0:
                change_labels.append("up")
            elif change < 0:
                change_labels.append("down")
            else:
                change_labels.append("flat")
        streak_direction, streak_length = StatisticsTool._current_streak(series_df["delta"].tolist())

        max_idx = values.idxmax()
        min_idx = values.idxmin()
        max_row = series_df.loc[max_idx]
        min_row = series_df.loc[min_idx]

        daily_rows: list[dict] = []
        for _, row in series_df.iterrows():
            daily_rows.append(
                {
                    "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                    "value": float(row["value"]),
                    "delta": StatisticsTool._serialize_number(row["delta"]),
                    "pct_change": StatisticsTool._serialize_number(row["pct_change"]),
                }
            )

        return {
            "type": "trend_summary",
            "window_days": int(window_days),
            "metric_alias": metric_alias,
            "direction": direction,
            "slope": slope,
            "first": first,
            "latest": latest,
            "mean": mean_value,
            "median": median_value,
            "std": std_value,
            "cv": cv,
            "total_change": total_change,
            "latest_vs_mean": latest_vs_mean,
            "avg_daily_change": avg_daily_change,
            "change_volatility": change_volatility,
            "latest_percentile_rank": latest_percentile_rank,
            "latest_position": latest_position,
            "streak_direction": streak_direction,
            "streak_length": streak_length,
            "recent_direction": change_labels,
            "max_value": float(max_row["value"]),
            "max_date": pd.Timestamp(max_row["date"]).strftime("%Y-%m-%d"),
            "min_value": float(min_row["value"]),
            "min_date": pd.Timestamp(min_row["date"]).strftime("%Y-%m-%d"),
            "daily_rows": daily_rows,
        }

    @staticmethod
    def _contribution_summary(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field") or request.get("date_col")
        dimension_field = request.get("dimension_field")
        metric_alias = request.get("metric_alias") or request.get("value_col")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(dimension_field, str) or not dimension_field:
            return "统计分析缺少必要参数: dimension_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if dimension_field not in input_df.columns:
            return f"统计分析缺少维度列: {dimension_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_days = StatisticsTool._coerce_positive_int(request.get("window_days") or request.get("window"), 10)
        top_k = request.get("top_k")
        if top_k is None or top_k == "":
            top_k = 10
        try:
            top_k = int(top_k)
        except Exception:
            top_k = 10
        if top_k <= 0:
            top_k = 10

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        df[metric_alias] = pd.to_numeric(df[metric_alias], errors="coerce").fillna(0.0)
        grouped = (
            df.groupby(["date", dimension_field], as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values(["date", dimension_field])
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用数据。"

        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))

        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        pivot = (
            grouped.pivot_table(index="date", columns=dimension_field, values=metric_alias, aggfunc="sum")
            .reindex(date_index)
            .fillna(0.0)
        )
        if pivot.empty:
            return "统计分析在窗口内无可用数据。"

        first_date = pd.Timestamp(date_index.min()).normalize()
        last_date = pd.Timestamp(date_index.max()).normalize()
        baseline_period = {"start": first_date.strftime("%Y-%m-%d"), "end": (first_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")}
        target_period = {"start": last_date.strftime("%Y-%m-%d"), "end": (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")}
        first_series = pivot.loc[first_date]
        last_series = pivot.loc[last_date]
        delta_series = last_series - first_series
        total_delta = float(delta_series.sum())
        first_total = float(first_series.sum())
        last_total = float(last_series.sum())

        rows: list[dict] = []
        for dim_value, delta in delta_series.items():
            first_v = float(first_series.get(dim_value, 0.0))
            last_v = float(last_series.get(dim_value, 0.0))
            d = float(delta)
            contribution_share = None if total_delta == 0.0 else float(d / total_delta)
            rows.append(
                {
                    "dimension": str(dim_value),
                    "first": first_v,
                    "last": last_v,
                    "delta": d,
                    "contribution_share": contribution_share,
                }
            )

        if total_delta < 0:
            rows = sorted(rows, key=lambda r: float(r.get("delta") or 0.0))
        else:
            rows = sorted(rows, key=lambda r: float(r.get("delta") or 0.0), reverse=True)

        top_rows = rows[: int(top_k)]
        others = rows[int(top_k) :]
        others_delta = float(sum(float(r.get("delta") or 0.0) for r in others))
        others_share = None if total_delta == 0.0 else float(others_delta / total_delta)

        return {
            "type": "contribution_summary",
            "window_days": int(window_days),
            "time_field": time_field,
            "dimension_field": dimension_field,
            "metric_alias": metric_alias,
            "comparison_method": "first_vs_last",
            "baseline_period": baseline_period,
            "target_period": target_period,
            "start": first_date.strftime("%Y-%m-%d"),
            "end": (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "first_date": first_date.strftime("%Y-%m-%d"),
            "last_date": last_date.strftime("%Y-%m-%d"),
            "first_total": first_total,
            "last_total": last_total,
            "total_delta": total_delta,
            "top_k": int(top_k),
            "rows": top_rows,
            "others": {"delta": others_delta, "contribution_share": others_share, "count": int(len(others))},
        }

    @staticmethod
    def _category_share(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"
        category_field = request.get("category_field")
        value_field = request.get("value_field")
        if not isinstance(category_field, str) or not category_field:
            return "统计分析缺少必要参数: category_field"
        if not isinstance(value_field, str) or not value_field:
            return "统计分析缺少必要参数: value_field"
        if category_field not in input_df.columns:
            return f"统计分析缺少必要列: {category_field}"
        if value_field not in input_df.columns:
            return f"统计分析缺少必要列: {value_field}"

        top_k = request.get("top_k")
        if top_k is None or top_k == "":
            top_k = None
        else:
            try:
                top_k = int(top_k)
            except Exception:
                top_k = None
            if isinstance(top_k, int) and top_k <= 0:
                top_k = None

        df = input_df[[category_field, value_field]].copy()
        df[value_field] = pd.to_numeric(df[value_field], errors="coerce").fillna(0.0)
        grouped = df.groupby(category_field, as_index=False).agg({value_field: "sum"})
        grouped = grouped.sort_values(value_field, ascending=False).reset_index(drop=True)
        total = float(grouped[value_field].sum())
        if total <= 0:
            rows: list[dict] = []
            for _, r in grouped.iterrows():
                rows.append({"category": str(r[category_field]), "count": float(r[value_field]), "share": 0.0})
            return {"type": "category_share", "total": 0.0, "rows": rows}

        grouped["share"] = grouped[value_field] / total
        rows: list[dict] = []
        if isinstance(top_k, int):
            top = grouped.head(top_k)
            for _, r in top.iterrows():
                rows.append({"category": str(r[category_field]), "count": float(r[value_field]), "share": float(r["share"])})
            others_count = float(grouped.iloc[top_k:][value_field].sum()) if len(grouped) > top_k else 0.0
            others_share = float(others_count / total) if total > 0 else 0.0
            return {
                "type": "category_share",
                "top_k": int(top_k),
                "total": float(total),
                "rows": rows,
                "others": {"count": others_count, "share": others_share},
            }

        for _, r in grouped.iterrows():
            rows.append({"category": str(r[category_field]), "count": float(r[value_field]), "share": float(r["share"])})
        return {"type": "category_share", "total": float(total), "rows": rows}

    @staticmethod
    def _daily_percentile_rank(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_days = request.get("window_days")
        if isinstance(window_days, str) and window_days.isdigit():
            window_days = int(window_days)
        if not isinstance(window_days, int) or window_days <= 0:
            window_days = 30

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .tail(window_days)
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用日期数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
            start = end - pd.Timedelta(days=int(window_days))
        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        series = grouped.set_index("date")["value"].reindex(date_index, fill_value=0.0)
        total_days = int(len(series))
        reference_date: pd.Timestamp | None = None
        ref_value_raw = request.get("reference_value")
        if ref_value_raw is not None:
            try:
                reference_value = float(ref_value_raw)
            except Exception:
                reference_value = None
        if ref_value_raw is None or reference_value is None:
            ref_raw = request.get("reference_date")
            reference_date = pd.to_datetime(ref_raw, errors="coerce") if isinstance(ref_raw, str) else pd.NaT
            if pd.isna(reference_date):
                reference_date = date_index.max()
            reference_date = pd.Timestamp(reference_date).normalize()
            if reference_date not in set(pd.Timestamp(d).normalize() for d in date_index):
                reference_date = date_index.max()
            reference_value = float(series.get(reference_date, 0.0))
            # 如果参考日没有实际数据（值为0），则回退到窗口中最后一个有数据的日期
            if reference_value == 0.0 and len(grouped) > 0:
                actual_last = grouped["date"].max()
                if pd.notna(actual_last) and actual_last != reference_date:
                    reference_date = pd.Timestamp(actual_last).normalize()
                    reference_value = float(series.get(reference_date, 0.0))

        less_count = int((series < reference_value).sum())
        le_count = int((series <= reference_value).sum())
        percentile_rank = 0.0 if total_days == 0 else (le_count / total_days)

        daily_rows: list[dict] = []
        for date, value in series.items():
            daily_rows.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "value": float(value),
                }
            )

        return {
            "type": "daily_percentile_rank",
            "window_days": int(window_days),
            "metric_alias": metric_alias,
            "reference_date": reference_date.strftime("%Y-%m-%d") if reference_date is not None else None,
            "reference_value": reference_value,
            "less_count": less_count,
            "le_count": le_count,
            "total_days": total_days,
            "percentile_rank": percentile_rank,
            "percentile_pct": percentile_rank * 100.0,
            "daily_rows": daily_rows,
        }

    @staticmethod
    def _weekend_percentile_rank(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_weekends = request.get("window_weekends")
        if isinstance(window_weekends, str) and window_weekends.isdigit():
            window_weekends = int(window_weekends)
        if not isinstance(window_weekends, int) or window_weekends <= 0:
            window_weekends = 10

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        df["weekday"] = df["date"].dt.dayofweek
        df = df[df["weekday"].isin([5, 6, 0])]
        if df.empty:
            return "统计分析窗口内无周末日数据。"

        adjusted_weekday = df["weekday"].replace({0: 7})
        df["weekend_start"] = df["date"] - pd.to_timedelta(adjusted_weekday - 5, unit="D")
        grouped = (
            df.groupby("weekend_start", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("weekend_start")
            .tail(window_weekends)
            .reset_index(drop=True)
        )
        if grouped.empty:
            return "统计分析在窗口内无可用周末数据。"

        grouped["value"] = grouped[metric_alias].astype(float)
        total_weekends = int(len(grouped))
        ref_raw = request.get("reference_date")
        reference_date = pd.to_datetime(ref_raw, errors="coerce") if isinstance(ref_raw, str) else pd.NaT
        if pd.isna(reference_date):
            reference_date = grouped["weekend_start"].max()
        reference_date = pd.Timestamp(reference_date).normalize()
        ref_weekend_start = reference_date - pd.Timedelta(days=((reference_date.dayofweek - 5) % 7))
        ref_rows = grouped[grouped["weekend_start"] == ref_weekend_start]
        if ref_rows.empty:
            ref_row = grouped.tail(1).iloc[0]
            ref_weekend_start = pd.Timestamp(ref_row["weekend_start"]).normalize()
            reference_value = float(ref_row["value"])
        else:
            reference_value = float(ref_rows.iloc[0]["value"])

        less_count = int((grouped["value"] < reference_value).sum())
        le_count = int((grouped["value"] <= reference_value).sum())
        percentile_rank = 0.0 if total_weekends == 0 else (le_count / total_weekends)

        weekend_rows: list[dict] = []
        for _, row in grouped.iterrows():
            weekend_start = pd.Timestamp(row["weekend_start"]).normalize()
            weekend_end = weekend_start + pd.Timedelta(days=2)
            weekend_rows.append(
                {
                    "weekend_start": weekend_start.strftime("%Y-%m-%d"),
                    "weekend_end": weekend_end.strftime("%Y-%m-%d"),
                    "value": float(row["value"]),
                }
            )

        return {
            "type": "weekend_percentile_rank",
            "window_weekends": int(window_weekends),
            "metric_alias": metric_alias,
            "reference_weekend_start": ref_weekend_start.strftime("%Y-%m-%d"),
            "reference_value": reference_value,
            "less_count": less_count,
            "le_count": le_count,
            "total_weekends": total_weekends,
            "percentile_rank": percentile_rank,
            "percentile_pct": percentile_rank * 100.0,
            "weekend_rows": weekend_rows,
        }

    @staticmethod
    def _weekday_percentile_rank(request: dict, input_df: pd.DataFrame) -> dict | str:
        if input_df is None or input_df.empty:
            return "统计分析无可用数据。"

        time_field = request.get("time_field")
        metric_alias = request.get("metric_alias")
        if not isinstance(time_field, str) or not time_field:
            return "统计分析缺少必要参数: time_field"
        if not isinstance(metric_alias, str) or not metric_alias:
            return "统计分析缺少必要参数: metric_alias"
        if time_field not in input_df.columns:
            return f"统计分析缺少时间列: {time_field}"
        if metric_alias not in input_df.columns:
            return f"统计分析缺少指标列: {metric_alias}"

        window_weeks = request.get("window_weeks")
        if isinstance(window_weeks, str) and str(window_weeks).isdigit():
            window_weeks = int(window_weeks)
        if not isinstance(window_weeks, int) or window_weeks <= 0:
            window_weeks = 10

        weekdays = request.get("weekdays")
        if not isinstance(weekdays, list) or not weekdays:
            weekdays = [7]
        weekdays = [int(w) for w in weekdays if isinstance(w, (int, float, str)) and str(w).isdigit()]
        weekdays = [w for w in weekdays if 1 <= int(w) <= 7]
        weekdays = sorted(list(dict.fromkeys(weekdays)))
        if not weekdays:
            weekdays = [7]

        df = input_df.copy()
        raw_time = df[time_field].astype(str).str.strip()
        parsed_cn = pd.to_datetime(raw_time, errors="coerce", format="%Y年%m月%d日")
        if float(parsed_cn.notna().mean()) >= 0.8:
            df[time_field] = parsed_cn
        else:
            df[time_field] = pd.to_datetime(raw_time, errors="coerce")
        df = df[df[time_field].notna()]
        if df.empty:
            return "统计分析时间列无法解析为日期。"

        df["date"] = df[time_field].dt.normalize()
        df["_weekday"] = df["date"].dt.dayofweek + 1
        df = df[df["_weekday"].isin(weekdays)]

        grouped = (
            df.groupby("date", as_index=False)
            .agg({metric_alias: "sum"})
            .sort_values("date")
            .reset_index(drop=True)
        )

        date_start_raw = request.get("date_start")
        date_end_raw = request.get("date_end")
        date_start = pd.to_datetime(date_start_raw, errors="coerce") if isinstance(date_start_raw, str) else pd.NaT
        date_end = pd.to_datetime(date_end_raw, errors="coerce") if isinstance(date_end_raw, str) else pd.NaT
        if pd.notna(date_start) and pd.notna(date_end) and pd.Timestamp(date_end) > pd.Timestamp(date_start):
            start = pd.Timestamp(date_start).normalize()
            end = pd.Timestamp(date_end).normalize()
        else:
            end = (
                pd.Timestamp(grouped["date"].max()).normalize() + pd.Timedelta(days=1)
                if not grouped.empty
                else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
            )
            start = end - pd.Timedelta(days=int(window_weeks) * 7)

        date_index = pd.date_range(start=start, end=end - pd.Timedelta(days=1), freq="D")
        weekday_index = pd.DatetimeIndex([d for d in date_index if (pd.Timestamp(d).dayofweek + 1) in set(weekdays)])
        if weekday_index.empty:
            return "统计分析窗口内无指定周内日数据。"

        series = (
            grouped.set_index("date")[metric_alias]
            .astype(float)
            .reindex(weekday_index, fill_value=0.0)
            .tail(int(window_weeks))
        )
        total = int(len(series))

        ref_raw = request.get("reference_date")
        reference_date = pd.to_datetime(ref_raw, errors="coerce") if isinstance(ref_raw, str) else pd.NaT
        if pd.isna(reference_date):
            reference_date = series.index.max()
        reference_date = pd.Timestamp(reference_date).normalize()
        if reference_date not in set(pd.Timestamp(d).normalize() for d in series.index):
            reference_date = series.index.max()
        reference_value = float(series.get(reference_date, 0.0))

        less_count = int((series < reference_value).sum())
        le_count = int((series <= reference_value).sum())
        percentile_rank = 0.0 if total == 0 else (le_count / total)

        daily_rows: list[dict] = []
        for date, value in series.items():
            daily_rows.append({"date": pd.Timestamp(date).strftime("%Y-%m-%d"), "value": float(value)})

        return {
            "type": "weekday_percentile_rank",
            "weekdays": weekdays,
            "window_weeks": int(window_weeks),
            "metric_alias": metric_alias,
            "reference_date": reference_date.strftime("%Y-%m-%d"),
            "reference_value": reference_value,
            "less_count": less_count,
            "le_count": le_count,
            "total_days": total,
            "percentile_rank": percentile_rank,
            "percentile_pct": percentile_rank * 100.0,
            "daily_rows": daily_rows,
        }


STATISTICS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "perform_statistics",
        "description": "执行单窗口统计后处理（周环比序列统计、下降占比统计、日阈值计数）。",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "weekly_decline_ratio",
                        "daily_threshold_count",
                        "monthly_mean",
                        "daily_mean",
                        "daily_mean_median",
                        "trend_summary",
                        "contribution_summary",
                        "category_share",
                        "daily_percentile_rank",
                        "weekend_percentile_rank",
                        "weekday_percentile_rank",
                    ],
                },
                "time_field": {"type": "string"},
                "window_weeks": {"type": "integer"},
                "window_days": {"type": "integer"},
                "window_weekends": {"type": "integer"},
                "date_start": {"type": "string"},
                "date_end": {"type": "string"},
                "reference_date": {"type": "string"},
                "weekdays": {"type": "array", "items": {"type": "integer"}},
                "op": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!="]},
                "threshold": {"type": "number"},
                "metric_alias": {"type": "string"},
                "category_field": {"type": "string"},
                "value_field": {"type": "string"},
                "dimension_field": {"type": "string"},
                "top_k": {"type": "integer"},
                "numerator_alias": {"type": "string"},
                "denominator_alias": {"type": "string"},
            },
            "required": ["type"],
        },
    },
}
