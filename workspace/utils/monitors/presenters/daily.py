"""每日订单观察的终端、飞书卡片和多维表展示。"""

def _format_mom(pct, prev_start=None, prev_end=None):
    if pct is None:
        return ""
    if prev_start is None or prev_end is None:
        return ""
    sign = "+" if pct >= 0 else ""
    base = f"{prev_start.month}/{prev_start.day}~{prev_end.month}/{prev_end.day}"
    return f"（较上月同期 {base} {sign}{pct:.1f}%）"


def _format_cumulative_line(label, cum) -> str:
    """格式化累计行：本月累计锁单 XX (XX) 台｜本年累计锁单 XX (XX) 台"""
    if not cum:
        return ""
    mtd = cum.get("mtd")
    ytd = cum.get("ytd")
    if not mtd or not ytd:
        return ""
    return (
        f"本月累计{label}{mtd['total']} ({mtd['total_user_car']}) 台"
        f"｜本年累计{label}{ytd['total']} ({ytd['total_user_car']}) 台"
    )


def _format_ls9_generations(stats) -> str:
    """LS9 代际拆分文本（含 '｜' 前缀）：M0 = LS9 老代际，M1 = 全新 LS9（LS9M1）。

    例：｜M0：7，M1：150。代际合计与 LS9 车系合计不等时补「其他：N」，保证闭合。
    未登记 LS9 代际映射时返回空串。
    """
    gen = stats.get("gen_counts")
    if not gen:
        return ""
    other = int(stats.get("count", 0)) - sum(gen.values())
    parts = [f"M0：{int(gen.get('LS9', 0))}", f"M1：{int(gen.get('LS9M1', 0))}"]
    if other > 0:
        parts.append(f"其他：{other}")
    return "｜" + "，".join(parts)


def _format_lock_model_detail(stats) -> str:
    """
    构建车型锁单明细文本（含 '｜' 前缀）。
    LS6 按代际展示：CM3/CM2(增程/纯电)/CM1，CM0>0 时追加。
    LS9 直接按代际展示：｜M0：LS9 老代际，M1：全新 LS9（口径同共享 series_group_logic）。
    """
    power = stats.get("ls8_power_counts")
    if power is not None:
        extended = power.get("增程", 0)
        electric = power.get("纯电", 0)
        unknown = stats["count"] - extended - electric
        unknown_text = f"/未知:{unknown}" if unknown else ""
        return f"｜增程:{extended}/纯电:{electric}{unknown_text}"

    versions = stats.get("product_versions")
    if versions is not None:
        if not stats.get("show_seats", True):
            detail = "，".join(f"{version}：{sum(seats.values())}" for version, seats in versions.items())
            gen_text = _format_ls9_generations(stats)
            if gen_text:
                return gen_text
            return "｜" + detail if detail else ""
        parts = []
        for version, seats in versions.items():
            seat_text = " / ".join(
                f"{seat}：{seats[seat]}" for seat in ("五座", "六座", "未标座位") if seats.get(seat)
            )
            parts.append(f"{version}：{sum(seats.values())}（{seat_text}）")
        return "\n  " + "\n  ".join(parts) if parts else ""
    gen = stats.get("gen_counts")
    if gen:
        cm2_ptype = stats.get("cm2_ptype") or {}
        parts = []
        if gen.get("CM3"):
            parts.append(f"CM3：{gen.get('CM3')}")
        if gen.get("CM2"):
            parts.append(
                f"CM2:{gen.get('CM2')}(增程:{cm2_ptype.get('增程', 0)}/纯电:{cm2_ptype.get('纯电', 0)})"
            )
        if gen.get("CM1"):
            parts.append(f"CM1:{gen.get('CM1')}")
        if gen.get("CM0"):
            parts.append(f"CM0:{gen.get('CM0')}")
        detail = ",".join(parts)
    else:
        detail_parts = []
        d = stats.get("details") or {}
        for cap, cap_count in d.items():
            cap_label = str(cap).replace("kwh", "kw")
            detail_parts.append(f"{cap_label}：{cap_count}")
        sd = stats.get("seat_details") or {}
        if "五座" in sd:
            detail_parts.append(f"五座：{sd['五座']}")
        if "六座" in sd:
            detail_parts.append(f"六座：{sd['六座']}")
        vd = stats.get("variant_details") or {}
        for variant, v_count in vd.items():
            detail_parts.append(f"{variant}：{v_count}")
        detail = "，".join(detail_parts)
    out = "｜" + detail if detail else ""
    ls9hyper = stats.get("ls9hyper_count")
    if ls9hyper is not None:
        out += f"｜LS9Hyper: {ls9hyper}"
    return out


def build_card(lock_stats, invoice_stats, pred_lock, mom, is_mtd,
               lock_cumulative, invoice_cumulative, *, generated_at):
    lock_mom_note = _format_mom((mom or {}).get("lock_pct"), (mom or {}).get("prev_start"), (mom or {}).get("prev_end"))
    invoice_mom_note = _format_mom((mom or {}).get("invoice_pct"), (mom or {}).get("prev_start"), (mom or {}).get("prev_end"))

    # 构建标题日期字符串（语义来源为用户运行的 --mtd 模式，而非日期形状反推）
    start_date = lock_stats['start_date']
    end_date = lock_stats['end_date']
    if is_mtd:
        date_str = f"{start_date} ~ {end_date}"
        title_prefix = "本月累计"
        lock_label = "本月累计锁单"
        invoice_label = "本月累计开票"
        show_cumulative = False
    elif start_date == end_date:
        date_str = str(start_date)
        title_prefix = "每日"
        lock_label = "昨日锁单数"
        invoice_label = "昨日开票数"
        show_cumulative = True
    else:
        date_str = f"{start_date} ~ {end_date}"
        title_prefix = "阶段性"
        lock_label = "期间锁单数"
        invoice_label = "期间开票数"
        show_cumulative = False

    lock_cumulative_line = _format_cumulative_line("锁单", lock_cumulative) if show_cumulative else ""
    invoice_cumulative_line = _format_cumulative_line("开票", invoice_cumulative) if show_cumulative else ""

    # 构建锁单明细文本
    lock_model_details = []
    for model, stats in lock_stats['models'].items():
        count = stats["count"]
        detail_str = _format_lock_model_detail(stats)
        lock_model_details.append(f"- {model}: {count} 单{detail_str}")
    lock_model_text = "\n".join(lock_model_details)

    # 构建开票明细文本
    invoice_model_details = []
    for model, info in invoice_stats['models'].items():
        price_str = f"{info['avg_price']/10000:.1f}w" if info['avg_price'] > 0 else "N/A"
        # 格式：- Model: Total (User) 台｜平均开票价格：XXw
        invoice_model_details.append(f"- {model}: {info['count']} ({info['user_car_count']}) 台｜平均开票价格：{price_str}")
    invoice_model_text = "\n".join(invoice_model_details)

    # 构建预测锁单与达成率
    pred_line = ""
    warn_line = ""
    is_warning = False
    if pred_lock is not None and pred_lock > 0:
        actual = lock_stats['total']
        rate = actual / pred_lock
        pred_line = f"预测锁单数：{pred_lock:.0f}"
        if rate < 0.8:
            is_warning = True
            warn_line = (
                f"\n\n⚠️ **达成率预警**\n"
                f"达成率：{rate:.1%} < 80%\n"
                f"实际锁单({actual}) 低于预测({pred_lock:.0f})，"
                f"建议排查转化链路是否存在异常。"
            )
        else:
            warn_line = f"\n达成率：{rate:.1%}（正常）"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 {title_prefix}业务数据观察 ({date_str})"
                },
                "template": "red" if is_warning else "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{lock_label}：** {lock_stats['total']} ({lock_stats['total_user_car']}) 台{lock_mom_note}\n{lock_model_text}\n{pred_line}{warn_line}" + (f"\n{lock_cumulative_line}" if lock_cumulative_line else "")
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{invoice_label}：** {invoice_stats['total']} ({invoice_stats['total_user_car']}) 台{invoice_mom_note}"
                            + (f"（不含对公批售 {invoice_stats.get('total_corporate', 0)} 台）" if invoice_stats.get('total_corporate', 0) > 0 else "")
                            + f"\n{invoice_model_text}"
                            + (f"\n{invoice_cumulative_line}" if invoice_cumulative_line else "")
                        )
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"统计时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }
    }


def build_bitable_values(lock_stats, invoice_stats, pred_lock, *, generated_at):
    start_date = lock_stats["start_date"]
    end_date = lock_stats["end_date"]
    date_key = str(start_date) if start_date == end_date else f"{start_date}~{end_date}"

    lock_model_details = []
    for model, stats in (lock_stats.get("models") or {}).items():
        count = stats.get("count", 0)
        detail_str = _format_lock_model_detail(stats)
        lock_model_details.append(f"- {model}: {count} 单{detail_str}")
    lock_model_text = "\n".join(lock_model_details)

    invoice_model_details = []
    for model, info in (invoice_stats.get("models") or {}).items():
        avg_price = float(info.get("avg_price") or 0)
        price_str = f"{avg_price/10000:.1f}w" if avg_price > 0 else "N/A"
        invoice_model_details.append(
            f"- {model}: {info.get('count', 0)} ({info.get('user_car_count', 0)}) 台｜平均开票价格：{price_str}"
        )
    invoice_model_text = "\n".join(invoice_model_details)

    corp = invoice_stats.get("total_corporate", 0)
    if corp > 0:
        invoice_model_text += f"\n对公批售：{corp} 台"

    attainment_rate = None
    is_warning = False
    if pred_lock is not None and pred_lock > 0:
        attainment_rate = float(lock_stats.get("total", 0)) / float(pred_lock)
        is_warning = attainment_rate < 0.8

    return {
        'date': date_key,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'lock_total': int(lock_stats.get("total", 0)),
        'invoice_total': int(invoice_stats.get("total", 0)),
        'invoice_user_total': int(invoice_stats.get("total_user_car", 0)),
        'pred_lock': (None if pred_lock is None else float(pred_lock)),
        'attainment_rate': attainment_rate,
        'is_warning': bool(is_warning),
        'lock_detail': lock_model_text,
        'invoice_detail': invoice_model_text,
        'generated_at': generated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def print_summary(lock_stats, invoice_stats, pred_lock, mom, is_mtd,
                  lock_cumulative, invoice_cumulative):
    start_date = lock_stats["start_date"]
    end_date = lock_stats["end_date"]
    lock_mom_note = _format_mom((mom or {}).get("lock_pct"), (mom or {}).get("prev_start"), (mom or {}).get("prev_end"))
    invoice_mom_note = _format_mom((mom or {}).get("invoice_pct"), (mom or {}).get("prev_start"), (mom or {}).get("prev_end"))

    lock_cumulative_line = _format_cumulative_line("锁单", lock_cumulative)
    invoice_cumulative_line = _format_cumulative_line("开票", invoice_cumulative)
    # 打印结果到控制台
    print("\n" + "="*30)
    if is_mtd:
        print(f"📅 本月累计: {start_date} ~ {end_date}")
    elif start_date == end_date:
        print(f"📅 日期: {start_date}")
    else:
        print(f"📅 日期范围: {start_date} ~ {end_date}")

    lock_print_label = "本月累计锁单" if is_mtd else "总锁单数"
    print(f" {lock_print_label}: {lock_stats['total']} ({lock_stats['total_user_car']}) 台{lock_mom_note}")
    print("   车型分布:")
    for model, stats in lock_stats['models'].items():
        count = stats["count"]
        detail_str = _format_lock_model_detail(stats)
        print(f"   - {model}: {count} 单{detail_str}")
    if pred_lock is not None and pred_lock > 0:
        rate = lock_stats['total'] / pred_lock
        warn = " ⚠️ 低于80%" if rate < 0.8 else ""
        print(f" 预测锁单数: {pred_lock:.0f}")
        print(f" 达成率: {rate:.1%}{warn}")
    if lock_cumulative_line:
        print(f" {lock_cumulative_line}")

    print("-" * 30)

    total_corp = invoice_stats.get('total_corporate', 0)
    corp_parts = []
    if total_corp > 0:
        cm = invoice_stats.get('corporate_models', {})
        for m in ['LS6', 'LS8', 'LS9', 'L6', 'LS7', 'L7']:
            if m in cm:
                corp_parts.append(f"{m}：{cm[m]}")
        corp_detail = "，".join(corp_parts) if corp_parts else ""
        corp_note = f"，不含对公批售 {total_corp} 台" + (f"（{corp_detail}）" if corp_detail else "")
    else:
        corp_note = ""
    invoice_print_label = "本月累计开票" if is_mtd else "总开票数"
    print(f"🚚 {invoice_print_label}: {invoice_stats['total']} ({invoice_stats['total_user_car']}) 台{invoice_mom_note}{corp_note}")
    print("   车型分布 (开票):")
    for model, info in invoice_stats['models'].items():
        price_display = f"{info['avg_price']/10000:.1f}w" if info['avg_price'] > 0 else "N/A"
        print(f"   - {model}: {info['count']} ({info['user_car_count']}) 台｜平均开票价格：{price_display}")
    if invoice_cumulative_line:
        print(f" {invoice_cumulative_line}")
    print("="*30 + "\n")
