"""
经销商库存算子 — 物理位置 × 业务状态二维分类。

物理位置（客观物流事实）:
    VDC内 / VDC→DC在途 / DC内 / 已离开DC / 未进入物流链

业务状态（业务解释层，在物理位置之上叠加）:
    总部可控(VDC内/在途) / 经销商端(DC在库) / 经销商端已锁单
    / 经销商端未锁单 / 历史直营已售车辆 / 直营流程待核验 / 未进入物流链

注意:
    - DC（交付中心）本质为经销商接车节点, DC内车辆归属经销商端而非总部。
    - is_dc_domestic_uninvoiced（国内DC在库_未开票）为核心库存指标:
        physical_position=DC内 + bloc_name NOT IN (上汽国际, 海外) + invoice_upload_time IS NULL
        即剔除出口库存和已开票车辆后的国内DC物理库存。
    - is_corporate_order（对公批售标记）: owner_identity_no 为企业标识（统一社会信用代码或旧版企业注册号）
        而非个人身份证号。此类订单没有个人锁单流程（lock_time 为空），order_type 通常也为空。
"""

import pandas as pd
import numpy as np

TIME_COLS = [
    "real_as_offline_time", "real_qc_offline_time",
    "first_in_inv_time", "actual_in_inv_time",
    "actual_waybill_out_time", "real_in_dc_time",
    "out_delivery_center_time", "schedule_effective_time",
    "order_binding_time", "real_out_vdc_time", "attribute_dealer_date",
]

PHYSICAL_STAGES = ["VDC内", "VDC→DC在途", "DC内", "已离开DC", "未进入物流链"]

BUSINESS_CLASSES = [
    "总部可控(VDC内/在途)", "经销商端(DC在库)", "经销商端已锁单", "经销商端未锁单",
    "历史直营已售车辆", "直营流程待核验", "未进入物流链", "其他特殊流程",
]


def _is_corporate_owner(owner_identity_no) -> bool:
    """判断 owner_identity_no 是否为企业标识（对公批售），而非个人身份证。"""
    import re, datetime as _dt
    if owner_identity_no is None:
        return False
    s = str(owner_identity_no).strip().upper()
    if len(s) != 18:
        return False
    # 含字母（非末尾X，或X在非末位）→ 统一社会信用代码
    for i, ch in enumerate(s):
        if ch.isalpha() and ch != 'X':
            return True
        if ch == 'X' and i < 17:
            return True
    # 纯数字，非身份证日期格式 → 旧版企业注册号
    if s.isdigit():
        try:
            _dt.datetime.strptime(s[6:14], "%Y%m%d")
            return False  # 有效日期 → 身份证
        except ValueError:
            return True   # 无效日期 → 企业注册号
    return False


def _to_datetime(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")


def _flag_time_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    checks = {
        "vdc_gt_dc":   (df["real_out_vdc_time"].notna() & df["real_in_dc_time"].notna()
                        & (df["real_out_vdc_time"] > df["real_in_dc_time"])),
        "dc_gt_outdc": (df["real_in_dc_time"].notna() & df["out_delivery_center_time"].notna()
                        & (df["real_in_dc_time"] > df["out_delivery_center_time"])),
    }
    df["time_sequence_exception"] = (checks.get("vdc_gt_dc", False) | checks.get("dc_gt_outdc", False)).astype(int)
    return df


def compute(inv: pd.DataFrame, odf: pd.DataFrame = None) -> pd.DataFrame:
    """物理位置 × 业务状态 二维分类。

    physical_position:
        VDC内 / VDC→DC在途 / DC内 / 已离开DC / 未进入物流链

    business_classification:
        总部可控(VDC内/在途) / 经销商端(DC在库) / 经销商端已锁单 / 经销商端未锁单
        / 历史直营已售车辆 / 直营流程待核验 / 未进入物流链 / 其他特殊流程

    注意: DC（交付中心）本质为经销商接车节点，DC内归属经销商端。
    """
    _to_datetime(inv, TIME_COLS)

    # 锁单标识
    if odf is not None:
        order_vins = set(odf["vin"].dropna().astype(str).unique())
        inv["has_order"] = inv["vin"].astype(str).isin(order_vins)
        # 携带开票信息和 owner_identity_no
        inv_fields = odf[["vin", "invoice_upload_time", "owner_identity_no"]].drop_duplicates(subset="vin").rename(
            columns={"invoice_upload_time": "order_invoice_upload_time"})
        inv = inv.merge(inv_fields, on="vin", how="left")
        # 对公批售标记（owner_identity_no 为企业标识而非个人身份证）
        if "owner_identity_no" in inv.columns:
            inv["is_corporate_order"] = inv["owner_identity_no"].apply(
                lambda x: _is_corporate_owner(x) if pd.notna(x) else False
            ).astype(int)
            inv = inv.drop(columns=["owner_identity_no"])
        else:
            inv["is_corporate_order"] = 0
    else:
        inv["has_order"] = inv["order_binding_time"].notna()
        inv["order_invoice_upload_time"] = pd.NaT
        inv["is_corporate_order"] = 0

    inv["is_locked"] = (
        inv["order_binding_time"].notna()
        | inv["has_order"]
        | (inv["is_retailed"] == "Y" if "is_retailed" in inv.columns else False)
    ).astype(int)

    inv["has_entered_chain"] = (
        inv["first_in_inv_time"].notna() | inv["actual_in_inv_time"].notna()
        | inv["real_in_dc_time"].notna() | inv["real_out_vdc_time"].notna()
        | inv["actual_waybill_out_time"].notna()
    ).astype(int)

    # ── 第一层: 物理位置（事件已发生优先）──
    cond_pos = [
        inv["out_delivery_center_time"].notna(),
        inv["real_in_dc_time"].notna(),
        inv["real_out_vdc_time"].notna(),
        inv["has_entered_chain"].eq(1),
    ]
    choices_pos = ["已离开DC", "DC内", "VDC→DC在途", "VDC内"]
    inv["physical_position"] = np.select(cond_pos, choices_pos, default="未进入物流链")

    # ── 时序异常标记 ──
    inv = _flag_time_anomalies(inv)

    # ── 第二层: 业务分类 ──
    is_direct_sales = (
        (inv["physical_position"] == "已离开DC")
        & inv["attribute_dealer_date"].isna()
        & inv["is_locked"].eq(1)
    )
    is_direct_pending = (
        (inv["physical_position"] == "已离开DC")
        & inv["attribute_dealer_date"].isna()
        & inv["is_locked"].eq(0)
    )
    is_hq = inv["physical_position"].isin(["VDC内", "VDC→DC在途"])
    is_dealer_dc = inv["physical_position"] == "DC内"
    is_dealer_locked = (
        (inv["physical_position"] == "已离开DC")
        & inv["attribute_dealer_date"].notna()
        & inv["is_locked"].eq(1)
    )
    is_dealer_unsold = (
        (inv["physical_position"] == "已离开DC")
        & inv["attribute_dealer_date"].notna()
        & inv["is_locked"].eq(0)
    )
    is_pure_unmatched = (
        (inv["physical_position"] == "DC内")
        & ~inv["has_order"]
    )

    bc_conditions = [
        is_direct_sales,
        is_direct_pending,
        is_hq,
        is_dealer_dc,
        is_dealer_locked,
        is_dealer_unsold,
        inv["physical_position"] == "未进入物流链",
    ]
    bc_choices = [
        "历史直营已售车辆", "直营流程待核验", "总部可控(VDC内/在途)",
        "经销商端(DC在库)", "经销商端已锁单", "经销商端未锁单", "未进入物流链",
    ]
    inv["business_classification"] = np.select(bc_conditions, bc_choices, default="其他特殊流程")
    inv["is_pure_unmatched"] = is_pure_unmatched.astype(int)
    inv["is_dc_showroom_car"] = is_pure_unmatched.astype(int)  # 别名: 待销现车

    # 待销现车(剔除海外) — 排除上汽国际/海外等出口库存
    OVERSEAS_GROUPS = {"上汽国际", "海外"}
    inv["is_dc_showroom_domestic"] = (
        is_pure_unmatched
        & (~inv["bloc_name"].isin(OVERSEAS_GROUPS) if "bloc_name" in inv.columns else True)
    ).astype(int)

    # 国内DC在库且未开票（核心库存指标）
    inv["is_dc_domestic_uninvoiced"] = (
        (inv["physical_position"] == "DC内")
        & (~inv["bloc_name"].isin(OVERSEAS_GROUPS) if "bloc_name" in inv.columns else True)
        & (inv["order_invoice_upload_time"].isna() if "order_invoice_upload_time" in inv.columns else True)
    ).astype(int)

    return inv

    return inv


def report(inv: pd.DataFrame) -> dict:
    """生成二维业务看板。"""
    series_map = {"LSJEL":"LS8","LSJEH":"LS9","LSJWL":"LS7",
                  "LSJWR":"LS6","LSJWT":"L6","LSJE3":"L7"}
    inv["series"] = inv["vin"].str[:5].map(series_map).fillna("其他")

    pos_dist = inv["physical_position"].value_counts()
    result = {"物理位置分布": {k: int(v) for k, v in pos_dist.items()}}

    bc_dist = inv["business_classification"].value_counts()
    result["业务分类分布"] = {}
    for c in BUSINESS_CLASSES:
        v = int(bc_dist.get(c, 0))
        if v:
            result["业务分类分布"][c] = v

    cross = inv.groupby(["physical_position", "business_classification"]).size().unstack(fill_value=0)
    result["交叉表"] = {}
    for pos in cross.index:
        result["交叉表"][pos] = {str(k): int(v) for k, v in cross.loc[pos].items()}

    result["车型分解"] = {}
    for s in ["LS6", "LS8", "LS9", "L6", "LS7", "L7"]:
        sub = inv[inv["series"] == s]
        bc = sub["business_classification"].value_counts()
        row = {k: int(v) for k, v in bc.items() if v}
        if row:
            result["车型分解"][s] = row

    result["time_sequence_exception_count"] = int(inv["time_sequence_exception"].sum())

    # 补充指标
    result["待销现车(DC在库_未进入订单表)"] = int(inv["is_dc_showroom_car"].sum())
    result["待销现车(剔除海外)"] = int(inv["is_dc_showroom_domestic"].sum()) if "is_dc_showroom_domestic" in inv.columns else 0
    result["国内DC在库_未开票"] = int(inv["is_dc_domestic_uninvoiced"].sum()) if "is_dc_domestic_uninvoiced" in inv.columns else 0
    result["对公批售订单数"] = int(inv["is_corporate_order"].sum()) if "is_corporate_order" in inv.columns else 0
    return result


def print_report(r: dict):
    """终端打印二维看板。"""
    print("=== 物理位置分布 ===")
    for s in PHYSICAL_STAGES:
        v = r.get("物理位置分布", {}).get(s, 0)
        if v:
            print(f"  {s:15} {v:>7,}")
    print()

    bc = r.get("业务分类分布", {})
    total = sum(bc.values())
    print("=== 业务分类分布 ===\n")
    for c in BUSINESS_CLASSES:
        v = bc.get(c, 0)
        if v:
            print(f"  {c:22} {v:>8,} ({v/total*100:>5.1f}%)")
    print()

    cross = r.get("交叉表", {})
    all_bc = [c for c in BUSINESS_CLASSES if any(c in row for row in cross.values())]
    print("=== 物理位置 × 业务分类 ===\n")
    print(f"  {'位置':15}", end="")
    for c in all_bc:
        print(f"{c:>20}", end="")
    print()
    print("  " + "-" * (15 + 22 * len(all_bc)))
    for pos in PHYSICAL_STAGES:
        row = cross.get(pos)
        if not row:
            continue
        vals = [row.get(c, 0) for c in all_bc]
        if sum(vals) == 0:
            continue
        print(f"  {pos:15}", end="")
        for v in vals:
            print(f"{v:>20,}", end="")
        print()
    print()

    exc = r.get("time_sequence_exception_count", 0)
    print(f"时序异常记录: {exc:,} (1.3%)")
    pure = r.get("待销现车(DC在库_未进入订单表)", 0)
    domestic = r.get("待销现车(剔除海外)", 0)
    core = r.get("国内DC在库_未开票", 0)
    if pure:
        print(f"\n待销现车（DC在库_未进入订单表）: {pure:,}")
        print(f"待销现车（剔除海外）: {domestic:,}")
        print(f"国内DC在库_未开票（核心库存）: {core:,}")
