"""Layer: Inbox Core — raw 输入 → keep/discard → facts 库"""
"""
inbox_parser.py — 将 ChatGPT daily run / 原始文本解析为结构化 raw items。

输入格式支持:
1. 结构化 Markdown：## 标题 + key: value 列表
2. 自由文本：按空行分割，每段作为一个 item
3. 简单列表：- 开头的条目

输出: list[dict]，每个 dict 包含 extract 出的品牌、车型、事件类型等字段。
"""

import re
from typing import Optional


def _try_extract_kv(text: str, key: str) -> Optional[str]:
    """从文本中提取 key: value。逐行扫描，不用 DOTALL 避免跨行吞噬。"""
    for line in text.split("\n"):
        line = line.strip()
        # Match: - key: value 或 key: value
        m = re.match(rf"^\s*(?:-\s+)?{key}\s*[:：]\s*(.+)$", line)
        if m:
            val = m.group(1).strip().rstrip("。，,.")
            if val:
                return val
    return None


def _try_extract_category(text: str) -> Optional[str]:
    """从 ## 标题行提取分类信息"""
    m = re.search(r"^##\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def _normalize_source_tier(tier: str) -> str:
    if not tier:
        return "tier_5_unverified"
    tier_map = {
        "官方": "tier_1_official",
        "官方源": "tier_1_official",
        "tier_1": "tier_1_official",
        "tier1": "tier_1_official",
        "媒体": "tier_3_industry_media",
        "垂媒": "tier_3_industry_media",
        "行业媒体": "tier_3_industry_media",
        "tier_3": "tier_3_industry_media",
        "tier3": "tier_3_industry_media",
        "社交": "tier_4_social_signal",
        "社媒": "tier_4_social_signal",
        "tier_4": "tier_4_social_signal",
        "tier4": "tier_4_social_signal",
        "未验证": "tier_5_unverified",
        "未知": "tier_5_unverified",
    }
    for kw, mapped in tier_map.items():
        if kw in tier:
            return mapped
    return "tier_5_unverified"


def _split_items(raw_text: str) -> list[str]:
    """将原始文本分割为独立 items。## 标题及其后续内容作为一个整体处理。"""
    lines = raw_text.strip().split("\n")
    items = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # ## 标题开始一个新的 item，先把上一个收掉
        if stripped.startswith("## "):
            if current:
                items.append("\n".join(current))
            current = [stripped]
        else:
            if not current:
                current = []
            current.append(stripped)
    if current:
        items.append("\n".join(current))
    return [it for it in items if len(it) > 10]


def parse_text(raw_text: str, default_date: str = None) -> list[dict]:
    """
    解析原始文本为 raw items。
    返回 list[dict]，每个 dict:
      { raw_text, brand, model, event_type, event_date, title, claim,
        source_name, source_url, source_tier, category }
    所有字段均为 str | None。
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return []

    blocks = _split_items(raw_text)
    items = []

    for block in blocks:
        category = _try_extract_category(block)
        brand = _try_extract_kv(block, "品牌") or _try_extract_kv(block, "Brand")
        model = _try_extract_kv(block, "车型") or _try_extract_kv(block, "Model")
        event_type = _try_extract_kv(block, "事件类型") or _try_extract_kv(block, "Event Type") or _try_extract_kv(block, "类型")
        event_date = _try_extract_kv(block, "时间") or _try_extract_kv(block, "日期") or _try_extract_kv(block, "Date") or default_date
        title = _try_extract_kv(block, "标题") or _try_extract_kv(block, "Title") or _try_extract_kv(block, "事件")
        claim = _try_extract_kv(block, "摘要") or _try_extract_kv(block, "Summary") or _try_extract_kv(block, "描述")
        source_name = _try_extract_kv(block, "来源") or _try_extract_kv(block, "Source")
        source_url = _try_extract_kv(block, "链接") or _try_extract_kv(block, "URL") or _try_extract_kv(block, "url")
        source_tier_raw = _try_extract_kv(block, "信源等级") or _try_extract_kv(block, "Source Tier")
        source_tier = _normalize_source_tier(source_tier_raw) if source_tier_raw else None

        if not brand:
            brand = _try_extract_brand_from_text(block)
        if not title:
            title = category

        items.append({
            "raw_text": block[:1000],
            "brand": brand or None,
            "model": model or None,
            "event_type": event_type or None,
            "event_date": event_date or None,
            "title": title or block[:80],
            "claim": claim or None,
            "source_name": source_name or None,
            "source_url": source_url or None,
            "source_tier": source_tier or None,
            "category": category or None,
        })

    return items


def _try_extract_brand_from_text(text: str) -> Optional[str]:
    """从自由文本中尝试提取品牌名"""
    known_brands = [
        "智己", "极氪", "领克", "问界", "智界", "享界", "尊界", "尚界",
        "鸿蒙智行", "理想", "小米", "蔚来", "乐道", "萤火虫", "小鹏",
        "阿维塔", "深蓝", "零跑", "腾势", "方程豹", "比亚迪", "特斯拉",
        "埃安", "岚图", "大众", "宝马", "奔驰", "奥迪", "吉利", "长城",
    ]
    for b in known_brands:
        if b in text:
            return b
    return None
