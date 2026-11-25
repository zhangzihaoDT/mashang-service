"""每日订单观察的锁单、开票和周期指标。"""

import re
from datetime import datetime, date

import pandas as pd

from shared.operators.product_attributes import resolve_product_attributes
from utils.business import is_corporate_owner, classify_product_names
from utils.business_definition import load_business_definition
from utils.orders.classification import apply_series_group_logic
from utils.orders.filters import flag_test_orders

TARGET_MODELS = ["LS6", "L6", "LS8", "LS9"]


def _fresh_ls9_mask(df):
    """「全新 LS9」记录：按 product_name（去空白）识别，对应代际 LS9M1。

    这些订单的 series 字段仍是 LS9，所以按 series 汇总时需按名称并入 LS9 车系池；
    口径与共享 series_group_logic 的 LS9M1 规则（含「全新」且含「LS9」）一致。
    """
    names = df['product_name'].fillna('').astype(str).str.replace(r'\s+', '', regex=True)
    return names.str.contains('全新', regex=False) & names.str.contains('LS9', regex=False)


def _lock_product_versions(model_df, model, business_definition=None):
    """按共享业务定义汇总版本 → 座位，订单号去重。"""
    keys = ['order_number', 'product_name']
    # LS9 车系池同时含 LS9 / LS9M1 两个代际组，版本规则按代际分表，需先带出代际
    if model == "LS9" and len(model_df):
        model_df = apply_series_group_logic(model_df.copy(), business_definition)
        keys.append('series_group_logic')
    orders = model_df[keys].drop_duplicates('order_number')
    classified = classify_product_names(orders, model, business_definition)
    versions = {}
    for version, seat in classified.itertuples(index=False, name=None):
        seats = versions.setdefault(version, {})
        seats[seat] = seats.get(seat, 0) + 1
    return dict(sorted(versions.items(), key=lambda item: (item[0] == "未分类", item[0])))


def analyze_daily_lock_orders(df, start_date, end_date, *, business_def=None):
    """
    分析锁单数据 (支持时间范围)
    """

    if business_def is None:
        business_def = load_business_definition()

    def _like(value, pattern):
        if value is None:
            return False
        pattern = pattern[1:-1] if len(pattern) >= 2 and pattern[0] == "'" and pattern[-1] == "'" else pattern
        regex_parts = []
        for ch in pattern:
            if ch == "%":
                regex_parts.append(".*")
            elif ch == "_":
                regex_parts.append(".")
            else:
                regex_parts.append(re.escape(ch))
        regex = "^" + "".join(regex_parts) + "$"
        return re.fullmatch(regex, str(value)) is not None

    def _tokenize(expr):
        tokens = []
        i = 0
        n = len(expr)
        while i < n:
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            if ch in ("(", ")"):
                tokens.append(ch)
                i += 1
                continue
            if ch == "'":
                j = i + 1
                while j < n and expr[j] != "'":
                    j += 1
                tokens.append(expr[i : j + 1] if j < n else expr[i:])
                i = j + 1 if j < n else n
                continue
            j = i
            while j < n and (expr[j].isalnum() or expr[j] in ("_",)):
                j += 1
            tokens.append(expr[i:j])
            i = j
        return [t for t in tokens if t]

    def _parse_logic(expr):
        tokens = _tokenize(expr)
        idx = 0

        def peek():
            return tokens[idx] if idx < len(tokens) else None

        def take():
            nonlocal idx
            tok = tokens[idx] if idx < len(tokens) else None
            idx += 1
            return tok

        def parse_expr():
            node = parse_term()
            while True:
                tok = peek()
                if tok and tok.upper() == "OR":
                    take()
                    rhs = parse_term()
                    node = ("OR", node, rhs)
                else:
                    break
            return node

        def parse_term():
            node = parse_factor()
            while True:
                tok = peek()
                if tok and tok.upper() == "AND":
                    take()
                    rhs = parse_factor()
                    node = ("AND", node, rhs)
                else:
                    break
            return node

        def parse_factor():
            tok = peek()
            if tok and tok.upper() == "NOT":
                take()
                inner = parse_factor()
                return ("NOT", inner)
            return parse_atom()

        def parse_atom():
            tok = peek()
            if tok == "(":
                take()
                inner = parse_expr()
                if peek() == ")":
                    take()
                return inner
            left = take()
            if not left:
                return ("LIT", False)
            not_flag = False
            tok2 = peek()
            if tok2 and tok2.upper() == "NOT":
                take()
                not_flag = True
            tok3 = peek()
            if tok3 and tok3.upper() == "LIKE":
                take()
            pattern = take()
            return ("COND", not_flag, left, pattern)

        return parse_expr()

    def _eval_ast(ast, product_name):
        op = ast[0]
        if op == "OR":
            return _eval_ast(ast[1], product_name) or _eval_ast(ast[2], product_name)
        if op == "AND":
            return _eval_ast(ast[1], product_name) and _eval_ast(ast[2], product_name)
        if op == "NOT":
            return not _eval_ast(ast[1], product_name)
        if op == "COND":
            not_flag, left, pattern = ast[1], ast[2], ast[3]
            if not left or str(left) != "product_name":
                return False
            res = _like(product_name, pattern or "")
            return (not res) if not_flag else res
        if op == "LIT":
            return bool(ast[1])
        return False

    # 确保必要的列存在
    # 更新为新数据集的列名
    required_columns = ['lock_time', 'order_number', 'series', 'product_name', 'order_type']
    for col in required_columns:
        if col not in df.columns:
            print(f"❌ 错误: 数据缺失列 {col}")
            return None

    # 数据预处理
    df_copy = df.copy()
    df_copy['lock_time'] = pd.to_datetime(df_copy['lock_time'], errors='coerce').dt.date

    # 筛选目标日期范围的锁单数据
    daily_orders = df_copy[
        (df_copy['lock_time'] >= start_date) &
        (df_copy['lock_time'] <= end_date)
    ]

    # 剔除测试单（总部主理店 + 假身份号）——与上市/预售监控口径对齐
    test_mask = flag_test_orders(daily_orders, business_def)
    if test_mask.any():
        daily_orders = daily_orders.loc[~test_mask].copy()

    # 1. 计算总锁单数 (基于 order_number 去重)
    total_lock_count = daily_orders['order_number'].nunique()

    # 2. 分车型统计
    model_stats = {}
    for model in TARGET_MODELS:
        if model == "LS9":
            model_df = daily_orders[daily_orders['series'].isin(["LS9", "LS9Hyper"])]
            # 「全新LS9 …」是按 product_name 识别的新代际（LS9M1），没有独立 series 值；
            # 这里按名称把 LS9M1 记录并回 LS9 车系池，与 LS8 池含 LS8Neo 的语义对齐
            fresh = daily_orders[_fresh_ls9_mask(daily_orders)]
            if len(fresh):
                model_df = pd.concat([model_df, fresh]).drop_duplicates('order_number')
        elif model == "LS8":
            model_df = daily_orders[daily_orders['series'].isin(["LS8", "LS8Neo"])]
        else:
            model_df = daily_orders[daily_orders['series'] == model]
        count = model_df['order_number'].nunique()

        stats = {"count": count}
        # LS6 代际区隔（CM3/CM2/CM1/CM0）：复用共享 series_group_logic（与上市监控同源），
        # CM2 再按 product_type_logic 分增程/纯电
        if model == "LS6":
            grouped = apply_series_group_logic(model_df.copy(), business_def)
            gen_counts = {g: 0 for g in ["CM3", "CM2", "CM1", "CM0"]}
            cm2_ptype = {"增程": 0, "纯电": 0}
            pt_logic = (business_def or {}).get("product_type_logic") or {}
            pt_asts = {}
            for pt, cond in pt_logic.items():
                if cond:
                    pt_asts[pt] = _parse_logic(str(cond))

            unique_orders = grouped.reindex(
                columns=['order_number', 'product_name', 'series_group_logic']
            ).drop_duplicates('order_number')
            for _, row in unique_orders.iterrows():
                matched = row['series_group_logic']
                if matched not in gen_counts:
                    continue
                gen_counts[matched] += 1
                if matched == "CM2":
                    p_name = row['product_name']
                    if pd.isna(p_name):
                        continue
                    p_name = str(p_name)
                    for pt, ast in pt_asts.items():
                        if _eval_ast(ast, p_name):
                            cm2_ptype[pt] += 1
                            break
            stats["gen_counts"] = gen_counts
            stats["cm2_ptype"] = cm2_ptype

        if model == "LS8":
            stats["ls8_power_counts"] = {}
            if count:
                names = model_df[['order_number', 'product_name']].dropna(subset=['order_number'])
                names = names.drop_duplicates('order_number').reset_index(drop=True)
                attrs = resolve_product_attributes(names, business_def or {})
                power = attrs.power_type.where(attrs.generation.eq("LS8"))
                power = power.mask(attrs.generation.eq("LS8Neo"), "纯电")
                stats["ls8_power_counts"] = power.value_counts().to_dict()

        if model in ("LS8", "LS9"):
            stats["product_versions"] = _lock_product_versions(model_df, model, business_def)
            stats["show_seats"] = model == "LS8"

        # LS9 代际区隔（LS9M1=全新 LS9 / LS9=老代际）：同样复用共享 series_group_logic，
        # 「全新LS9 …」被 priority 更高的 LS9M1 规则先命中。
        # count 由 series 池口径给出，gen_counts 只拆分类别，剩余量在这里归「其他」保证闭合。
        if model == "LS9":
            grouped = apply_series_group_logic(model_df.copy(), business_def)
            unique_orders = grouped.reindex(
                columns=['order_number', 'product_name', 'series_group_logic']
            ).drop_duplicates('order_number')
            generations = sorted(
                (business_def or {}).get("model_series_mapping", {}).get("LS9") or ["LS9"]
            )
            counts = unique_orders['series_group_logic'].value_counts().to_dict()
            stats["gen_counts"] = {g: int(counts.get(g, 0)) for g in generations}

        model_stats[model] = stats

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total": total_lock_count,
        "total_user_car": daily_orders.loc[daily_orders["order_type"].eq("用户车"), "order_number"].nunique(),
        "models": model_stats
    }

def analyze_daily_invoice_orders(df, start_date, end_date):
    """
    分析开票数据 (基于 Invoice_Upload_Time)
    定义：有 Invoice_Upload_Time 且有 Lock_Time 的 Order Number 数
    """

    # 确保必要的列存在
    # 更新为新数据集的列名
    required_columns = ['invoice_upload_time', 'lock_time', 'order_number', 'series', 'invoice_amount', 'order_type']
    for col in required_columns:
        if col not in df.columns:
            print(f"❌ 错误: 数据缺失列 {col}")
            return None

    # 数据预处理
    df_copy = df.copy()
    df_copy['invoice_upload_time'] = pd.to_datetime(df_copy['invoice_upload_time'], errors='coerce').dt.date

    # 第一步：全部开票记录（不锁 lock_time 过滤），用于对公批售等补充标注
    raw_invoice_all = df_copy[
        (df_copy['invoice_upload_time'] >= start_date) &
        (df_copy['invoice_upload_time'] <= end_date)
    ]
    total_raw_invoice = raw_invoice_all['order_number'].nunique()

    # 从全量开票记录中检测对公批售订单（owner_identity_no 为统一社会信用代码的企业订单）
    total_corporate_count = 0
    corporate_model_count = {}
    if len(raw_invoice_all) > 0 and 'owner_identity_no' in raw_invoice_all.columns:
        corporate_mask = raw_invoice_all['owner_identity_no'].apply(is_corporate_owner)
        total_corporate_count = raw_invoice_all[corporate_mask]['order_number'].nunique()
        # 分解到车型
        for model in TARGET_MODELS:
            if model == "LS9":
                m = raw_invoice_all[corporate_mask & raw_invoice_all['series'].isin(["LS9", "LS9Hyper"])]
                fresh = raw_invoice_all[corporate_mask & _fresh_ls9_mask(raw_invoice_all)]
                if len(fresh):
                    m = pd.concat([m, fresh]).drop_duplicates('order_number')
            else:
                m = raw_invoice_all[corporate_mask & (raw_invoice_all['series'] == model)]
            cnt = m['order_number'].nunique()
            if cnt > 0:
                corporate_model_count[model] = cnt

    # 第二步：标准口径 — 有 lock_time 的开票
    invoice_orders = raw_invoice_all[raw_invoice_all['lock_time'].notna()]

    # 1. 计算总开票数 (基于 order_number 去重)
    total_invoice_count = invoice_orders['order_number'].nunique()

    # 计算用户车开票数
    user_car_orders = invoice_orders[invoice_orders['order_type'] == '用户车']
    total_user_car_count = user_car_orders['order_number'].nunique()

    # 2. 分车型统计
    model_invoice_stats = {}
    for model in TARGET_MODELS:
        if model == "LS9":
            model_df = invoice_orders[invoice_orders['series'].isin(["LS9", "LS9Hyper"])]
            # 与锁单侧同源：按 product_name 把新代际（LS9M1）记录并回 LS9 车系池
            fresh = invoice_orders[_fresh_ls9_mask(invoice_orders)]
            if len(fresh):
                model_df = pd.concat([model_df, fresh]).drop_duplicates('order_number')
        else:
            model_df = invoice_orders[invoice_orders['series'] == model]
        count = model_df['order_number'].nunique()

        # 用户车数量
        model_user_car_df = model_df[model_df['order_type'] == '用户车']
        user_car_count = model_user_car_df['order_number'].nunique()

        # 计算该车型的平均开票价格 (仅计算用户车)
        model_valid_prices = model_user_car_df[
            (model_user_car_df['invoice_amount'].notna()) &
            (model_user_car_df['invoice_amount'] > 0)
        ]['invoice_amount']
        avg_price = model_valid_prices.mean() if not model_valid_prices.empty else 0

        model_invoice_stats[model] = {
            "count": count,
            "user_car_count": user_car_count,
            "avg_price": avg_price
        }

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total": total_invoice_count,
        "total_raw": total_raw_invoice,
        "total_user_car": total_user_car_count,
        "total_corporate": total_corporate_count,
        "corporate_models": corporate_model_count,
        "models": model_invoice_stats
    }


def compute_mtd_mom(df, lock_stats, invoice_stats, is_mtd=False, *, lock_analyzer=None):
    """
    仅 MTD 模式（用户显式 --mtd）下计算上月同周期累计的锁单/开票环比。
    返回 dict：lock_pct / invoice_pct（百分比数值，无基期时为 None）、
    基期 prev_start / prev_end、以及 lock_prev / invoice_prev（供日志/debug 或双值文案）；
    非 MTD 模式返回 None。
    """
    if not is_mtd:
        return None
    start_date = lock_stats["start_date"]
    end_date = lock_stats["end_date"]

    import calendar
    prev_year = start_date.year if start_date.month > 1 else start_date.year - 1
    prev_month = start_date.month - 1 if start_date.month > 1 else 12
    last_day = calendar.monthrange(prev_year, prev_month)[1]
    prev_start = datetime(prev_year, prev_month, 1).date()
    prev_end = datetime(prev_year, prev_month, min(end_date.day, last_day)).date()

    lock_analyzer = lock_analyzer or analyze_daily_lock_orders
    prev_lock = lock_analyzer(df, prev_start, prev_end)
    prev_invoice = analyze_daily_invoice_orders(df, prev_start, prev_end)
    if not prev_lock or not prev_invoice:
        return None

    def _pct(cur, prev):
        if prev is None or prev <= 0:
            return None
        return (float(cur) - float(prev)) / float(prev) * 100.0

    return {
        "lock_pct": _pct(lock_stats["total"], prev_lock["total"]),
        "invoice_pct": _pct(invoice_stats["total"], prev_invoice["total"]),
        "prev_start": prev_start,
        "prev_end": prev_end,
        "lock_prev": prev_lock["total"],
        "invoice_prev": prev_invoice["total"],
    }


def compute_cumulative_stats(df, end_date, analyzer):
    """
    计算截至 end_date 的本月累计/本年累计（自然月/自然年，起点为月/年首日）。

    analyzer: analyze_daily_lock_orders / analyze_daily_invoice_orders
    返回 {"mtd": {total, total_user_car}, "ytd": {total, total_user_car}}；
    某口径计算失败时对应值为 None（不影响其余口径）。
    各累计口径与单日口径同源（同 analyzer、同去重/剔测试单规则），仅时间窗不同。
    """
    def _one(start_date):
        stats = analyzer(df, start_date, end_date)
        if not stats:
            return None
        return {
            "total": stats.get("total", 0),
            "total_user_car": stats.get("total_user_car", 0),
        }

    return {
        "mtd": _one(end_date.replace(day=1)),
        "ytd": _one(date(end_date.year, 1, 1)),
    }
