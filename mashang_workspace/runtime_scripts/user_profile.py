#!/usr/bin/env python
"""
锁单用户画像：性别占比、年龄代际占比、城市线级占比、省份 TOP10

用法:
    python runtime_scripts/user_profile.py --series LS8 --start-date 2026-04-01 --end-date 2026-06-21
    python runtime_scripts/user_profile.py --series LS8 --date 2026-06-01
    python runtime_scripts/user_profile.py --series LS8 --start-date 2026-04-01 --end-date 2026-06-21 --format json
"""

import sys, argparse, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from datetime import datetime, timedelta
from utils.result_contract import build_success_contract, save_contract_json, contract_to_terminal

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"

COHORTS = [
    ("00后", 2000, 2009), ("95后", 1995, 1999), ("90后", 1990, 1994),
    ("85后", 1985, 1989), ("80后", 1980, 1984), ("75后", 1975, 1979),
    ("70后", 1970, 1974), ("65后", 1965, 1969), ("60前", None, 1959),
]

TIER1 = {"北京", "上海", "广州", "深圳"}
NEW_TIER1 = {"成都", "杭州", "重庆", "武汉", "苏州", "西安", "天津", "南京",
             "郑州", "长沙", "东莞", "宁波", "佛山", "青岛", "沈阳", "昆明"}
TIER2 = {"合肥", "无锡", "厦门", "福州", "济南", "大连", "温州", "哈尔滨",
         "长春", "泉州", "南宁", "贵阳", "南昌", "金华", "常州", "嘉兴",
         "惠州", "珠海", "中山", "台州", "烟台", "兰州", "绍兴", "海口",
         "乌鲁木齐", "太原", "石家庄", "徐州", "潍坊", "扬州"}

CITY_TO_PROVINCE = {
    "北京": "北京", "天津": "天津", "上海": "上海", "重庆": "重庆",
    "广州": "广东", "深圳": "广东", "佛山": "广东", "东莞": "广东", "中山": "广东", "珠海": "广东", "惠州": "广东",
    "杭州": "浙江", "宁波": "浙江", "温州": "浙江", "绍兴": "浙江", "嘉兴": "浙江", "金华": "浙江", "台州": "浙江", "湖州": "浙江", "衢州": "浙江", "丽水": "浙江", "舟山": "浙江",
    "苏州": "江苏", "南京": "江苏", "无锡": "江苏", "常州": "江苏", "南通": "江苏", "徐州": "江苏", "扬州": "江苏", "镇江": "江苏", "泰州": "江苏", "盐城": "江苏", "淮安": "江苏", "连云港": "江苏", "宿迁": "江苏", "昆山": "江苏",
    "成都": "四川", "绵阳": "四川", "德阳": "四川", "宜宾": "四川", "南充": "四川", "泸州": "四川", "乐山": "四川", "自贡": "四川", "攀枝花": "四川", "眉山": "四川", "遂宁": "四川", "广元": "四川", "内江": "四川", "达州": "四川", "资阳": "四川", "雅安": "四川",
    "西安": "陕西", "咸阳": "陕西", "宝鸡": "陕西", "渭南": "陕西", "汉中": "陕西", "榆林": "陕西", "延安": "陕西", "安康": "陕西", "商洛": "陕西",
    "武汉": "湖北", "宜昌": "湖北", "襄阳": "湖北", "荆州": "湖北", "黄冈": "湖北", "十堰": "湖北", "孝感": "湖北", "荆门": "湖北", "鄂州": "湖北", "咸宁": "湖北", "随州": "湖北",
    "长沙": "湖南", "株洲": "湖南", "湘潭": "湖南", "衡阳": "湖南", "岳阳": "湖南", "常德": "湖南", "益阳": "湖南", "郴州": "湖南", "永州": "湖南", "怀化": "湖南", "娄底": "湖南", "邵阳": "湖南", "张家界": "湖南",
    "郑州": "河南", "洛阳": "河南", "新乡": "河南", "许昌": "河南", "南阳": "河南", "商丘": "河南", "信阳": "河南", "周口": "河南", "驻马店": "河南", "开封": "河南", "焦作": "河南", "平顶山": "河南", "安阳": "河南", "濮阳": "河南", "漯河": "河南", "鹤壁": "河南", "三门峡": "河南",
    "济南": "山东", "青岛": "山东", "烟台": "山东", "潍坊": "山东", "临沂": "山东", "济宁": "山东", "淄博": "山东", "威海": "山东", "泰安": "山东", "德州": "山东", "聊城": "山东", "滨州": "山东", "菏泽": "山东", "东营": "山东", "日照": "山东", "枣庄": "山东",
    "江门": "广东", "汕头": "广东", "湛江": "广东", "茂名": "广东", "肇庆": "广东", "清远": "广东", "韶关": "广东", "揭阳": "广东", "潮州": "广东", "梅州": "广东", "河源": "广东", "阳江": "广东", "云浮": "广东",
    "厦门": "福建", "福州": "福建", "泉州": "福建", "漳州": "福建", "莆田": "福建", "宁德": "福建", "南平": "福建", "三明": "福建", "龙岩": "福建",
    "合肥": "安徽", "芜湖": "安徽", "蚌埠": "安徽", "淮南": "安徽", "马鞍山": "安徽", "铜陵": "安徽", "安庆": "安徽", "滁州": "安徽", "阜阳": "安徽", "宿州": "安徽", "六安": "安徽", "亳州": "安徽", "池州": "安徽", "宣城": "安徽",
    "南昌": "江西", "赣州": "江西", "九江": "江西", "上饶": "江西", "宜春": "江西", "吉安": "江西", "抚州": "江西", "萍乡": "江西", "景德镇": "江西", "新余": "江西", "鹰潭": "江西",
    "昆明": "云南", "曲靖": "云南", "玉溪": "云南", "大理": "云南", "丽江": "云南", "红河": "云南", "西双版纳": "云南", "普洱": "云南", "保山": "云南", "昭通": "云南", "临沧": "云南",
    "贵阳": "贵州", "遵义": "贵州", "毕节": "贵州", "六盘水": "贵州", "安顺": "贵州",
    "海口": "海南", "三亚": "海南", "儋州": "海南",
    "石家庄": "河北", "唐山": "河北", "保定": "河北", "廊坊": "河北", "邯郸": "河北", "邢台": "河北", "秦皇岛": "河北", "沧州": "河北", "张家口": "河北", "承德": "河北", "衡水": "河北",
    "沈阳": "辽宁", "大连": "辽宁", "鞍山": "辽宁", "抚顺": "辽宁", "本溪": "辽宁", "丹东": "辽宁", "锦州": "辽宁", "营口": "辽宁", "阜新": "辽宁", "辽阳": "辽宁", "盘锦": "辽宁", "铁岭": "辽宁", "朝阳": "辽宁", "葫芦岛": "辽宁",
    "长春": "吉林", "吉林": "吉林",
    "哈尔滨": "黑龙江", "大庆": "黑龙江", "齐齐哈尔": "黑龙江", "牡丹江": "黑龙江", "佳木斯": "黑龙江", "绥化": "黑龙江",
    "太原": "山西", "大同": "山西", "运城": "山西", "临汾": "山西", "长治": "山西", "晋中": "山西", "忻州": "山西", "吕梁": "山西", "晋城": "山西", "阳泉": "山西",
    "呼和浩特": "内蒙古", "包头": "内蒙古", "鄂尔多斯": "内蒙古", "赤峰": "内蒙古", "通辽": "内蒙古", "呼伦贝尔": "内蒙古",
    "乌鲁木齐": "新疆", "兰州": "甘肃", "银川": "宁夏", "西宁": "青海", "拉萨": "西藏",
    "南宁": "广西", "桂林": "广西", "柳州": "广西", "北海": "广西",
}


def parse_args():
    p = argparse.ArgumentParser(description="锁单用户画像：性别/年龄/城市线级/省份")
    p.add_argument("--date", type=str, help="单日查询 (YYYY-MM-DD)")
    p.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    p.add_argument("--series", type=str, required=True, help="车系过滤")
    p.add_argument("--order-type", type=str, default=None, help="订单类型过滤 (如 用户车、大客户等)")
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--limit", type=int, default=10, help="省份 TOPN (默认 10)")
    return p.parse_args()


def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date)
        return d, d + timedelta(days=1), args.date, "date"
    if args.start_date and args.end_date:
        s = pd.Timestamp(args.start_date)
        e = pd.Timestamp(args.end_date) + timedelta(days=1)
        return s, e, f"{args.start_date}~{args.end_date}", "range"
    yesterday = datetime.now() - timedelta(days=1)
    d = pd.Timestamp(yesterday.date())
    return d, d + timedelta(days=1), yesterday.strftime("%Y-%m-%d"), "date"


def norm_city(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    for sfx in ["市", "地区", "自治州", "盟"]:
        if s.endswith(sfx) and len(s) > len(sfx):
            s = s[:-len(sfx)]
            break
    return s


def city_to_tier_label(c):
    if c in TIER1:
        return "一线"
    if c in NEW_TIER1:
        return "新一线"
    if c in TIER2:
        return "二线"
    return "三线及以下"


def age_cohort_distribution(age_series, lock_year=2026):
    valid = age_series.notna()
    n_known = int(valid.sum())
    birth = lock_year - age_series[valid]
    rows = []
    for label, lo, hi in COHORTS:
        if lo is None:
            m = birth <= hi
        else:
            m = (birth >= lo) & (birth <= hi)
        cnt = int(m.sum())
        share_known = cnt / n_known if n_known else 0
        rows.append({"cohort": label, "count": cnt, "share_known": round(share_known, 4)})
    return rows, n_known


def main():
    args = parse_args()
    t_start, t_end, t_label, tw_type = resolve_time_range(args)

    df = pd.read_parquet(str(ORDER_PARQUET))
    df["lock_time"] = pd.to_datetime(df["lock_time"], errors="coerce")
    df = df[df["lock_time"].notna()].copy()
    mask = (df["lock_time"] >= t_start) & (df["lock_time"] < t_end)
    df_f = df[mask]
    if args.series:
        df_f = df_f[df_f["series"] == args.series]
    if args.order_type:
        df_f = df_f[df_f["order_type"] == args.order_type]

    total = len(df_f)

    # 1. Gender
    g = df_f["owner_gender"].value_counts()
    male = int(g.get("男", 0))
    female = int(g.get("女", 0))
    unknown_g = total - male - female

    # 2. Age (owner_age 优先)
    age_rows, n_age_known = age_cohort_distribution(df_f["owner_age"])
    age_unknown = total - n_age_known

    # 3. City tier
    cities = df_f["license_city"].apply(norm_city)
    tiers = cities.apply(city_to_tier_label)
    tc = tiers.value_counts()
    tier_order = ["一线", "新一线", "二线", "三线及以下"]

    # 4. Province top K
    prov_series = cities.map(CITY_TO_PROVINCE).fillna("未知")
    pc = prov_series.value_counts()
    real_prov = pc[pc.index != "未知"].head(args.limit)
    unknown_prov = int(pc.get("未知", 0))

    cmd = "python " + " ".join(sys.argv)
    time_window = {"type": tw_type}
    if tw_type == "date":
        time_window["date"] = t_label
        time_window["start_date"] = t_label
        time_window["end_date"] = t_label
    else:
        time_window["start_date"] = args.start_date
        time_window["end_date"] = args.end_date

    filters = {"series": args.series}
    if args.order_type:
        filters["order_type"] = args.order_type

    scope = {
        "data_source": str(ORDER_PARQUET),
        "time_window": time_window,
        "filters": filters,
        "metric_definition": "gender=owner_gender, age=owner_age(2026-owner_age), city_tier/province=license_city映射",
    }

    gender_items = [
        {"value": "男", "metrics": {"count": male, "share": round(male / total, 4)}},
        {"value": "女", "metrics": {"count": female, "share": round(female / total, 4)}},
    ]
    if unknown_g:
        gender_items.append({"value": "默认未知", "metrics": {"count": unknown_g, "share": round(unknown_g / total, 4)}})

    age_items = [{"value": r["cohort"], "metrics": {"count": r["count"], "share_known": r["share_known"], "share_total": round(r["count"] / total, 4)}} for r in age_rows]
    if age_unknown:
        age_items.append({"value": "未知年龄", "metrics": {"count": age_unknown, "share_known": -1, "share_total": round(age_unknown / total, 4)}})

    tier_items = [{"value": t, "metrics": {"count": int(tc.get(t, 0)), "share": round(int(tc.get(t, 0)) / total, 4)}} for t in tier_order]

    prov_items = []
    for i, (p, cnt) in enumerate(real_prov.items(), 1):
        prov_items.append({"value": p, "metrics": {"rank": i, "count": int(cnt), "share": round(cnt / total, 4)}})
    if unknown_prov:
        prov_items.append({"value": "（城市映射未知）", "metrics": {"count": unknown_prov, "share": round(unknown_prov / total, 4)}})

    result = {
        "summary": f"{t_label} {args.series} 锁单用户 {total} 人。男性 {male/total*100:.1f}%，主力 {age_rows[3]['cohort']}~{age_rows[2]['cohort']}（{(age_rows[2]['count']+age_rows[3]['count'])/n_age_known*100:.1f}%），新一线~一线 {(tc.get('新一线',0)+tc.get('一线',0))/total*100:.1f}%",
        "metrics": {
            "total_users": total,
            "male_pct": round(male / total, 4),
            "female_pct": round(female / total, 4),
            "age_known_pct": round(n_age_known / total, 4),
            "tier1_newtier1_pct": round((tc.get("一线", 0) + tc.get("新一线", 0)) / total, 4),
        },
        "dimensions": [
            {"name": "owner_gender", "label": "性别", "items": gender_items},
            {"name": "age_cohort", "label": "年龄代际", "items": age_items},
            {"name": "city_tier", "label": "城市线级", "items": tier_items},
            {"name": "province", "label": "省份", "items": prov_items},
        ],
        "tables": [
            {
                "title": f"{args.series} 锁单用户性别占比",
                "columns": ["性别", "人数", "占比"],
                "rows": [{"性别": i["value"], "人数": i["metrics"]["count"], "占比": f"{i['metrics']['share']*100:.1f}%"} for i in gender_items],
            },
            {
                "title": f"{args.series} 锁单用户年龄代际占比（owner_age）",
                "columns": ["代际", "人数", "占已知年龄", "占总量"],
                "rows": [{"代际": i["value"], "人数": i["metrics"]["count"],
                          "占已知年龄": f"{i['metrics']['share_known']*100:.1f}%" if i["value"] != "未知年龄" else "-",
                          "占总量": f"{i['metrics']['share_total']*100:.1f}%"} for i in age_items],
            },
            {
                "title": f"{args.series} 锁单用户城市线级占比",
                "columns": ["城市线级", "人数", "占比"],
                "rows": [{"城市线级": i["value"], "人数": i["metrics"]["count"], "占比": f"{i['metrics']['share']*100:.1f}%"} for i in tier_items],
            },
            {
                "title": f"{args.series} 锁单销量 TOP{args.limit} 省份",
                "columns": ["排名", "省份", "人数", "占比"],
                "rows": [{"排名": str(i["metrics"]["rank"]), "省份": i["value"], "人数": str(i["metrics"]["count"]), "占比": f"{i['metrics']['share']*100:.1f}%"} for i in prov_items if "rank" in i["metrics"]]
                        + ([{"排名": "-", "省份": i["value"], "人数": str(i["metrics"]["count"]), "占比": f"{i['metrics']['share']*100:.1f}%"} for i in prov_items if "rank" not in i["metrics"]]),
            },
        ],
    }

    top_entities = [{"field": "province", "value": str(v), "metrics": {"count": int(c)}}
                    for v, c in real_prov.head(5).items()]

    ctx = {
        "metric": "user_profile", "series": args.series,
        "order_type": args.order_type,
        "available_dimensions": ["owner_gender", "age_cohort", "city_tier", "province"],
        "top_entities": top_entities,
        "age_field": "owner_age",
    }
    if tw_type == "date":
        ctx["date"] = t_label
    else:
        ctx.update({"start_date": args.start_date, "end_date": args.end_date})

    contract = build_success_contract(
        script="runtime_scripts/user_profile.py", command=cmd, scope=scope,
        result=result, followup_context=ctx,
    )

    if args.format == "json":
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            save_contract_json(contract, out_dir / f"{t_label}_{args.series}_user_profile.json")
        else:
            print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(contract_to_terminal(contract))


if __name__ == "__main__":
    main()
