"""
inbox_parser.py — 将 Planner 日报解析为结构化 parse contract。

输入: 24 品牌每日营销事件监控 (## 章节标题 + Markdown 表格)
输出: parse contract { source_type, sections[], items[] }

章节类型:
  - 可入库确认事件 / 品牌新事件 / confirmed / 🔴       → brand_events
  - 高优先级弱信号 / 待复核 / review / 🟡              → review_signals
  - 未发现新增动作的品牌 / 品牌状态 / ⚪                → brand_status
  - 品牌声量观察 / 声量 / 📊                          → brand_volume
"""

import re
from typing import Optional

_SECTION_TYPE_PATTERNS = [
    (r"(品牌新事件|品牌动态|确认事件|可入库确认|确认事实|今日重点(营销)?事件|confirmed|🔴)", "brand_events"),
    (r"(待审查信号|待确认信号|审查中|弱信号|待复核|review|🟡)", "review_signals"),
    (r"(品牌状态总览|品牌状态|未发现.*新增动作|无新增动作|⚪)", "brand_status"),
    (r"(品牌声量观察|声量观察|声量|📊)", "brand_volume"),
]

_KNOWN_BRANDS = [
    "智己", "极氪", "领克", "问界", "智界", "享界", "尊界", "尚界",
    "鸿蒙智行", "理想", "小米", "蔚来", "乐道", "萤火虫", "小鹏",
    "阿维塔", "深蓝", "零跑", "腾势", "方程豹", "比亚迪", "特斯拉",
    "埃安", "岚图", "大众", "宝马", "奔驰", "奥迪", "吉利", "长城",
]

_COLUMN_MAP = {
        "品牌": "brand",
        "车型": "model",
        "车型/对象": "model",
        "事件类型": "event_type",
        "可能事件类型": "event_type",
        "event_type": "event_type",
        "action_type": "event_type",
        "摘要": "claim",
        "事件": "title",
        "事件摘要": "claim",
        "信号描述": "claim",
        "信号": "claim",
        "signal": "claim",
        "动态": "claim",
        "action_summary": "claim",
        "来源": "source_name",
        "信源等级": "source_tier",
        "source_tier": "source_tier",
        "当前阶段": "status_phase",
        "status": "status_phase",
        "状态": "status_phase",
        "最近事件": "last_event",
        "上次更新": "last_updated",
        "备注": "note",
        "判断": "note",
        "signal_date": "event_date",
        "reason_not_confirmed": "note",
        "continue_tracking": "continue_tracking",
    }


def _detect_section_type(header: str) -> str:
    for pat, stype in _SECTION_TYPE_PATTERNS:
        if re.search(pat, header):
            return stype
    return "other"


def _parse_table_rows(table_lines: list[str]) -> list[dict]:
    if not table_lines:
        return []
    header_line = None
    data_lines = []
    for line in table_lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        if header_line is None:
            header_line = s
        elif "-" in s and all(c in "| -:" for c in s):
            continue
        else:
            data_lines.append(s)
    if not header_line or not data_lines:
        return []
    headers = [h.strip() for h in header_line.strip().strip("|").split("|")]
    rows = []
    for dl in data_lines:
        cells = [c.strip() for c in dl.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        row = {}
        for i, h in enumerate(headers):
            row[h] = cells[i] if i < len(cells) else ""
        rows.append(row)
    return rows


def _map_columns(item: dict, section_type: str) -> dict:
    result = {}
    for raw_key, val in item.items():
        std_key = _COLUMN_MAP.get(raw_key, raw_key)
        result[std_key] = val
    result["section_type"] = section_type
    brand = result.get("brand", "") or ""
    model = result.get("model", "") or ""
    claim = result.get("claim", "") or ""
    event_type = result.get("event_type", "") or ""
    if not result.get("title"):
        parts = [p for p in [brand, model, event_type, claim[:30]] if p]
        result["title"] = " — ".join(parts) if parts else ""
    return result


def _try_extract_brand_from_text(text: str) -> Optional[str]:
    for b in _KNOWN_BRANDS:
        if b in text:
            return b
    return None


def parse_text(raw_text: str, default_date: str = None) -> list[dict]:
    """解析 Planner 日报为 items。"""
    contract = parse_contract(raw_text, default_date=default_date)
    return contract["items"]


def parse_contract(raw_text: str, default_date: str = None) -> dict:
    """
    解析 Planner 日报为完整 parse contract。

    Contract 格式:
    {
        "source_type": "planner_daily_report",
        "date": str | None,
        "items": [ ... ],
        "sections": [
            { "section_type": str, "section_title": str,
              "row_count": int, "rows": [ ... ] }
        ]
    }
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return {"source_type": "planner_daily_report", "date": default_date,
                "items": [], "sections": []}

    lines = raw_text.split("\n")
    sections = []
    current_section_type = None
    current_section_title = None
    current_table_lines = None
    items = []

    for line in lines:
        stripped = line.strip()
        hm = re.match(r"^##\s+(.+)$", stripped)
        if hm:
            if current_section_type and current_table_lines:
                rows = _parse_table_rows(current_table_lines)
                mapped = [_map_columns(r, current_section_type) for r in rows]
                sections.append({
                    "section_type": current_section_type,
                    "section_title": current_section_title,
                    "row_count": len(mapped),
                    "rows": mapped,
                })
                for mr in mapped:
                    mr["source_type"] = "planner_daily_report"
                    mr["event_date"] = mr.get("event_date") or default_date
                    if not mr.get("brand"):
                        mr["brand"] = _try_extract_brand_from_text(str(mr))
                    items.append(mr)

            current_section_type = _detect_section_type(hm.group(1))
            current_section_title = hm.group(1)
            current_table_lines = None
            continue

        if stripped.startswith("|") and "---" not in stripped:
            if current_table_lines is None:
                current_table_lines = []
            current_table_lines.append(stripped)

    if current_section_type and current_table_lines:
        rows = _parse_table_rows(current_table_lines)
        mapped = [_map_columns(r, current_section_type) for r in rows]
        sections.append({
            "section_type": current_section_type,
            "section_title": current_section_title,
            "row_count": len(mapped),
            "rows": mapped,
        })
        for mr in mapped:
            mr["source_type"] = "planner_daily_report"
            mr["event_date"] = mr.get("event_date") or default_date
            if not mr.get("brand"):
                mr["brand"] = _try_extract_brand_from_text(str(mr))
            items.append(mr)

    return {
        "source_type": "planner_daily_report",
        "date": default_date,
        "items": items,
        "sections": sections,
    }
