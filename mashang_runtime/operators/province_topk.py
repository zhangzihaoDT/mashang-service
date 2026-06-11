import datetime
import re
import pandas as pd

from tools.statistics_tool import StatisticsTool


def _normalize_city(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s == "上海城区":
        return "上海"
    for suffix in ["市", "地区", "自治州", "盟"]:
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)]
            break
    return s


def _parse_top_k(user_query: str) -> int:
    q = (user_query or "").upper().replace(" ", "")
    m = re.search(r"TOP\s*(\d{1,3})", q)
    if not m:
        m = re.search(r"前\s*(\d{1,3})\s*个", q)
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 200:
                return v
        except Exception:
            pass
    return 10


def _default_city_to_province() -> dict[str, str]:
    mapping: dict[str, str] = {
        "北京": "北京",
        "天津": "天津",
        "上海": "上海",
        "重庆": "重庆",
        "广州": "广东",
        "深圳": "广东",
        "佛山": "广东",
        "东莞": "广东",
        "中山": "广东",
        "珠海": "广东",
        "惠州": "广东",
        "江门": "广东",
        "汕头": "广东",
        "湛江": "广东",
        "茂名": "广东",
        "肇庆": "广东",
        "清远": "广东",
        "韶关": "广东",
        "揭阳": "广东",
        "潮州": "广东",
        "梅州": "广东",
        "河源": "广东",
        "阳江": "广东",
        "云浮": "广东",
        "杭州": "浙江",
        "宁波": "浙江",
        "温州": "浙江",
        "绍兴": "浙江",
        "嘉兴": "浙江",
        "金华": "浙江",
        "台州": "浙江",
        "湖州": "浙江",
        "衢州": "浙江",
        "丽水": "浙江",
        "舟山": "浙江",
        "苏州": "江苏",
        "南京": "江苏",
        "无锡": "江苏",
        "常州": "江苏",
        "南通": "江苏",
        "徐州": "江苏",
        "扬州": "江苏",
        "镇江": "江苏",
        "泰州": "江苏",
        "盐城": "江苏",
        "淮安": "江苏",
        "连云港": "江苏",
        "宿迁": "江苏",
        "昆山": "江苏",
        "成都": "四川",
        "绵阳": "四川",
        "德阳": "四川",
        "宜宾": "四川",
        "南充": "四川",
        "泸州": "四川",
        "乐山": "四川",
        "自贡": "四川",
        "攀枝花": "四川",
        "眉山": "四川",
        "遂宁": "四川",
        "广元": "四川",
        "内江": "四川",
        "达州": "四川",
        "资阳": "四川",
        "雅安": "四川",
        "西安": "陕西",
        "咸阳": "陕西",
        "宝鸡": "陕西",
        "渭南": "陕西",
        "汉中": "陕西",
        "榆林": "陕西",
        "延安": "陕西",
        "安康": "陕西",
        "商洛": "陕西",
        "武汉": "湖北",
        "宜昌": "湖北",
        "襄阳": "湖北",
        "荆州": "湖北",
        "黄冈": "湖北",
        "十堰": "湖北",
        "孝感": "湖北",
        "荆门": "湖北",
        "鄂州": "湖北",
        "咸宁": "湖北",
        "随州": "湖北",
        "长沙": "湖南",
        "株洲": "湖南",
        "湘潭": "湖南",
        "衡阳": "湖南",
        "岳阳": "湖南",
        "常德": "湖南",
        "益阳": "湖南",
        "郴州": "湖南",
        "永州": "湖南",
        "怀化": "湖南",
        "娄底": "湖南",
        "邵阳": "湖南",
        "张家界": "湖南",
        "郑州": "河南",
        "洛阳": "河南",
        "新乡": "河南",
        "许昌": "河南",
        "南阳": "河南",
        "商丘": "河南",
        "信阳": "河南",
        "周口": "河南",
        "驻马店": "河南",
        "开封": "河南",
        "焦作": "河南",
        "平顶山": "河南",
        "安阳": "河南",
        "濮阳": "河南",
        "漯河": "河南",
        "鹤壁": "河南",
        "三门峡": "河南",
        "济南": "山东",
        "青岛": "山东",
        "烟台": "山东",
        "潍坊": "山东",
        "临沂": "山东",
        "济宁": "山东",
        "淄博": "山东",
        "威海": "山东",
        "泰安": "山东",
        "德州": "山东",
        "聊城": "山东",
        "滨州": "山东",
        "菏泽": "山东",
        "东营": "山东",
        "日照": "山东",
        "枣庄": "山东",
        "合肥": "安徽",
        "芜湖": "安徽",
        "蚌埠": "安徽",
        "淮南": "安徽",
        "马鞍山": "安徽",
        "铜陵": "安徽",
        "安庆": "安徽",
        "滁州": "安徽",
        "阜阳": "安徽",
        "宿州": "安徽",
        "六安": "安徽",
        "亳州": "安徽",
        "池州": "安徽",
        "宣城": "安徽",
        "厦门": "福建",
        "福州": "福建",
        "泉州": "福建",
        "漳州": "福建",
        "莆田": "福建",
        "宁德": "福建",
        "南平": "福建",
        "三明": "福建",
        "龙岩": "福建",
        "南昌": "江西",
        "赣州": "江西",
        "九江": "江西",
        "上饶": "江西",
        "宜春": "江西",
        "吉安": "江西",
        "抚州": "江西",
        "萍乡": "江西",
        "景德镇": "江西",
        "新余": "江西",
        "鹰潭": "江西",
        "昆明": "云南",
        "曲靖": "云南",
        "玉溪": "云南",
        "大理": "云南",
        "丽江": "云南",
        "红河": "云南",
        "西双版纳": "云南",
        "普洱": "云南",
        "保山": "云南",
        "昭通": "云南",
        "临沧": "云南",
        "贵阳": "贵州",
        "遵义": "贵州",
        "毕节": "贵州",
        "六盘水": "贵州",
        "安顺": "贵州",
        "黔东南": "贵州",
        "黔南": "贵州",
        "黔西南": "贵州",
        "海口": "海南",
        "三亚": "海南",
        "三沙": "海南",
        "儋州": "海南",
        "石家庄": "河北",
        "唐山": "河北",
        "保定": "河北",
        "廊坊": "河北",
        "邯郸": "河北",
        "邢台": "河北",
        "秦皇岛": "河北",
        "沧州": "河北",
        "张家口": "河北",
        "承德": "河北",
        "衡水": "河北",
        "沈阳": "辽宁",
        "大连": "辽宁",
        "鞍山": "辽宁",
        "抚顺": "辽宁",
        "本溪": "辽宁",
        "丹东": "辽宁",
        "锦州": "辽宁",
        "营口": "辽宁",
        "阜新": "辽宁",
        "辽阳": "辽宁",
        "盘锦": "辽宁",
        "铁岭": "辽宁",
        "朝阳": "辽宁",
        "葫芦岛": "辽宁",
        "长春": "吉林",
        "吉林": "吉林",
        "延边": "吉林",
        "四平": "吉林",
        "通化": "吉林",
        "白城": "吉林",
        "白山": "吉林",
        "松原": "吉林",
        "哈尔滨": "黑龙江",
        "大庆": "黑龙江",
        "齐齐哈尔": "黑龙江",
        "牡丹江": "黑龙江",
        "佳木斯": "黑龙江",
        "绥化": "黑龙江",
        "鸡西": "黑龙江",
        "鹤岗": "黑龙江",
        "双鸭山": "黑龙江",
        "伊春": "黑龙江",
        "七台河": "黑龙江",
        "黑河": "黑龙江",
        "肇东": "黑龙江",
        "太原": "山西",
        "大同": "山西",
        "运城": "山西",
        "临汾": "山西",
        "长治": "山西",
        "晋中": "山西",
        "忻州": "山西",
        "吕梁": "山西",
        "晋城": "山西",
        "阳泉": "山西",
        "呼和浩特": "内蒙古",
        "包头": "内蒙古",
        "鄂尔多斯": "内蒙古",
        "赤峰": "内蒙古",
        "通辽": "内蒙古",
        "呼伦贝尔": "内蒙古",
        "乌鲁木齐": "新疆",
        "喀什": "新疆",
        "伊犁": "新疆",
        "昌吉": "新疆",
        "克拉玛依": "新疆",
        "拉萨": "西藏",
        "银川": "宁夏",
        "西宁": "青海",
        "兰州": "甘肃",
        "西安新区": "陕西",
        "南宁": "广西",
        "桂林": "广西",
        "柳州": "广西",
        "北海": "广西",
        "海口市": "海南",
    }
    return mapping


def run_province_topk_share_operator(
    df: pd.DataFrame,
    user_query: str,
    start: str,
    end: str,
    series: str | None,
    city_field: str = "license_city",
    time_field: str = "lock_time",
) -> dict:
    if df is None or df.empty:
        return {"type": "province_topk_share", "error": "no_data", "message": "无可用数据。"}
    if time_field not in df.columns:
        return {"type": "province_topk_share", "error": "missing_time_field", "message": f"缺少时间字段: {time_field}"}
    if city_field not in df.columns:
        return {"type": "province_topk_share", "error": "missing_city_field", "message": f"缺少城市字段: {city_field}"}

    try:
        start_day = datetime.date.fromisoformat(str(start)[:10])
        end_day = datetime.date.fromisoformat(str(end)[:10])
    except Exception:
        return {"type": "province_topk_share", "error": "invalid_time_window", "message": "时间窗口格式错误。"}
    if end_day <= start_day:
        return {"type": "province_topk_share", "error": "invalid_time_window", "message": "时间窗口不合法。"}

    work = df.copy()
    work[time_field] = pd.to_datetime(work[time_field], errors="coerce")
    work = work[work[time_field].notna()]
    if series and "series" in work.columns:
        work = work[work["series"] == series]
    if work.empty:
        return {"type": "province_topk_share", "error": "no_data", "message": "筛选后无数据。"}

    start_ts = pd.Timestamp(start_day)
    end_ts = pd.Timestamp(end_day)
    work = work[(work[time_field] >= start_ts) & (work[time_field] < end_ts)]
    if work.empty:
        return {"type": "province_topk_share", "error": "no_data", "message": "时间窗口内无数据。"}

    top_k = _parse_top_k(user_query)
    city_to_province = _default_city_to_province()
    city_norm = work[city_field].apply(_normalize_city)
    province = city_norm.map(city_to_province)
    province = province.fillna("未知")

    counts = province.value_counts().reset_index()
    counts.columns = ["province", "count"]
    counts_df = counts.copy()

    stat = StatisticsTool().perform_statistics(
        {
            "type": "category_share",
            "category_field": "province",
            "value_field": "count",
            "top_k": top_k,
        },
        counts_df,
    )
    if isinstance(stat, str):
        return {"type": "province_topk_share", "error": "statistics_failed", "message": stat}

    stat["type"] = "province_topk_share"
    stat["series"] = series
    stat["city_field"] = city_field
    stat["time_field"] = time_field
    stat["date_start"] = start_day.isoformat()
    stat["date_end"] = end_day.isoformat()
    stat["mapping_unknown_count"] = int((province == "未知").sum())
    stat["mapping_unknown_ratio"] = 0.0 if len(province) <= 0 else float((province == "未知").mean())
    return stat
