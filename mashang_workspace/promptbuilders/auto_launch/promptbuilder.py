#!/usr/bin/env python
"""
Auto Launch Promptbuilder — 生成新车上市/预售/发布会等市场事件的 AI 搜索 Prompt。

职责边界：
- 不直接爬取网页
- 不调用 LLM
- 只负责把车型、事件类型、时间窗口、竞品列表、信源分层组织成高质量搜索 Prompt
- 该 Prompt 用于交给 DeepSeek / ChatGPT / OpenCode 搜索能力执行信息检索

用法:
  # 手动指定竞品
  python mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
    --brand 智己 --model LS6 --event-type 上市 --event-date 2026-06-25 --window 48h \
    --competitors "小鹏G6,特斯拉Model Y,问界M5" \
    --output outputs/auto_launch/prompts/ls6_search_task.md

  # 从 watchlist 自动推导竞品
  python mashang_workspace/promptbuilders/auto_launch/promptbuilder.py \
    --brand 智己 --model LS8 --event-type 上市 --event-date 2026-06-25 --window 48h \
    --targets-file mashang_workspace/configs/ls8_competitor_watchlist.csv \
    --competitor-limit 5 \
    --include-priority high \
    --output outputs/auto_launch/prompts/ls8_search_task.md
"""

import csv, json, sys, argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
TEMPLATES_DIR = MODULE_DIR / "templates"
CONFIGS_DIR = MODULE_DIR / "configs"


# ─── Watchlist types ─────────────────────────────────────────────


@dataclass
class WatchlistEntry:
    target_id: str
    brand: str
    brand_aliases: list[str] = field(default_factory=list)
    model: str = ""
    model_aliases: list[str] = field(default_factory=list)
    display_name: str = ""
    group: str = ""                    # legacy group field (fallback)
    ecosystem_group: str = ""          # 品牌阵营（如"新势力SUV"）
    battle_field_id: str = ""          # 产品战场（如"large_six_seat_suv"）
    priority: str = "medium"
    active: bool = True


@dataclass
class DerivationResult:
    entries: list[WatchlistEntry] = field(default_factory=list)
    target_group: str = ""
    active_filter_applied: bool = False
    group_filter_applied: bool = False
    derivation_note: str = ""
    watchlist_filter_rule: str = ""


# ─── Helpers ─────────────────────────────────────────────────────


def load_yaml(path: Path) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_text(path: Path) -> str:
    with open(path) as f:
        return f.read()


def parse_window(window_str: str) -> tuple[int, str]:
    unit = window_str[-1]
    amount = int(window_str[:-1])
    return amount, unit


def compute_time_window(
    event_date_str: str | None,
    window_str: str | None,
    start_str: str | None,
    end_str: str | None,
) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)

    if start_str and end_str:
        return start_str, end_str, f"{start_str} 至 {end_str}"

    if event_date_str and window_str:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        amount, unit = parse_window(window_str)
        if unit == "h":
            start = event_date - timedelta(hours=amount // 2)
            end = event_date + timedelta(hours=amount // 2)
        elif unit == "d":
            start = event_date - timedelta(days=amount // 2)
            end = event_date + timedelta(days=amount // 2)
        else:
            raise ValueError(f"不支持的时间窗口单位: {unit}")
        return (
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}（基于 {event_date_str} 前后 {window_str}）",
        )

    if window_str:
        amount, unit = parse_window(window_str)
        if unit == "h":
            start = now - timedelta(hours=amount)
            end = now
        elif unit == "d":
            start = now - timedelta(days=amount)
            end = now
        else:
            raise ValueError(f"不支持的时间窗口单位: {unit}")
        return (
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}（最近 {window_str}）",
        )

    start = now - timedelta(days=7)
    end = now
    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}（默认 7 天）",
    )


def find_event_type(event_types: list[dict], event_type_name: str) -> dict | None:
    for et in event_types:
        if et["name"] == event_type_name or et["id"] == event_type_name:
            return et
    return None


def format_event_type_definition(et: dict) -> str:
    keywords = "、".join(et.get("search_keywords", []))
    return f"{et['name']}（{et['description']}）\n  搜索关键词：{keywords}"


def build_output_dir(output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ─── Watchlist Adapter ───────────────────────────────────────────


WATCHLIST_FIELD_CANDIDATES = {
    "target_id": ["target_id", "id", "competitor_id"],
    "brand": ["brand", "brand_name", "make"],
    "brand_aliases": ["brand_aliases", "brand_alias", "brand_variants"],
    "model": ["model", "model_name", "model_code"],
    "model_aliases": ["model_aliases", "model_alias", "model_variants"],
    "display_name": ["display_name", "name", "competitor_name", "full_name"],
    "battle_field_id": ["battle_field_id", "battlefield_id", "battle_field", "product_segment"],
    "ecosystem_group": ["ecosystem_group", "ecosystem", "brand_group", "camp"],
    "group": ["group"],
    "priority": ["priority", "tier", "level"],
    "active": ["active", "enabled", "is_active"],
}


def resolve_field(header: str) -> str | None:
    """Map a CSV header to a canonical field name using candidate mappings."""
    h = header.strip().lower()
    for canonical, candidates in WATCHLIST_FIELD_CANDIDATES.items():
        if h == canonical.lower() or h in [c.lower() for c in candidates]:
            return canonical
    return None


def load_watchlist(targets_file: str | Path) -> tuple[list[WatchlistEntry], dict]:
    """加载 watchlist CSV，返回 (entries, field_meta)。

    field_meta 包含字段检测信息：
      - has_active: CSV 中是否存在 active 字段
      - has_group: CSV 中是否存在 group 字段
      - all_count: 总条目数
      - active_count: active=true 的条目数
    """
    path = Path(targets_file)
    if not path.exists():
        print(f"[ERROR] watchlist 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[ERROR] watchlist 文件为空: {path}", file=sys.stderr)
        sys.exit(1)

    # Build field mapping from actual CSV headers
    field_map = {}
    for h in reader.fieldnames:
        canonical = resolve_field(h)
        if canonical:
            field_map[canonical] = h

    required = ["brand"]
    missing = [r for r in required if r not in field_map]
    if missing:
        print(f"[ERROR] watchlist 缺少必要字段（尝试匹配 {missing}）", file=sys.stderr)
        print(f"  CSV headers: {reader.fieldnames}", file=sys.stderr)
        sys.exit(1)

    has_active = "active" in field_map
    has_group = "group" in field_map
    has_battle_field = "battle_field_id" in field_map
    has_ecosystem_group = "ecosystem_group" in field_map

    entries = []
    all_count = 0
    for r in rows:
        all_count += 1

        # Active filter (if field exists)
        if has_active:
            active_val = r.get(field_map["active"], "").strip().lower()
            if active_val not in ("true", "1", "yes", ""):
                continue

        brand_aliases_raw = r.get(field_map.get("brand_aliases", ""), "")
        model_aliases_raw = r.get(field_map.get("model_aliases", ""), "")

        # Battle field: try battle_field_id first, fallback to group
        bf_raw = r.get(field_map.get("battle_field_id", ""), "").strip() if has_battle_field else ""
        legacy_group_raw = r.get(field_map.get("group", ""), "").strip() if has_group else ""

        entries.append(WatchlistEntry(
            target_id=r.get(field_map.get("target_id", ""), "").strip(),
            brand=r.get(field_map["brand"], "").strip(),
            brand_aliases=[a.strip() for a in brand_aliases_raw.split("|") if a.strip()],
            model=r.get(field_map.get("model", ""), "").strip(),
            model_aliases=[a.strip() for a in model_aliases_raw.split("|") if a.strip()],
            display_name=r.get(field_map.get("display_name", ""), "").strip(),
            group=bf_raw or legacy_group_raw,
            ecosystem_group=r.get(field_map.get("ecosystem_group", ""), "").strip() if has_ecosystem_group else legacy_group_raw,
            battle_field_id=bf_raw,
            priority=r.get(field_map.get("priority", ""), "medium").strip().lower(),
            active=True,
        ))

    field_meta = {
        "has_active": has_active,
        "has_group": has_group,
        "has_battle_field": has_battle_field,
        "has_ecosystem_group": has_ecosystem_group,
        "all_count": all_count,
        "active_count": len(entries),
    }

    if not entries:
        msg = "没有 active=true 的 watchlist 条目"
        if all_count > 0 and not has_active:
            msg = f"watchlist 有 {all_count} 条但全部被排除（可能 CSV 格式问题）"
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)

    return entries, field_meta


def load_target_profiles(profile_file: str | Path) -> list[dict]:
    """加载 target_profiles.yaml 配置文件。"""
    path = Path(profile_file)
    if not path.exists():
        print(f"[WARN] target profile 文件不存在: {path}", file=sys.stderr)
        return []
    try:
        cfg = load_yaml(path)
        return cfg.get("profiles", [])
    except Exception as e:
        print(f"[WARN] target profile 文件解析失败: {e}", file=sys.stderr)
        return []


def resolve_target_group(
    target_brand: str,
    target_model: str,
    entries: list[WatchlistEntry],
    has_group: bool,
    manual_group: str | None = None,
    profile_file: str | Path | None = None,
    our_brand: str = "",
    our_model: str = "",
) -> tuple[str, str]:
    """解析 target_group，返回 (group, source)。

    target_profiles.yaml 存储的是本品车型画像（our_model），非 event_model。
    因此需要先按 our_brand/our_model 匹配，再按 target_brand/target_model(event) 匹配。

    优先级:
    1. 用户显式传入 --target-group
    2. 从 --target-profile-file 中按 our_brand + our_model 匹配（如有提供）
    3. 从 --target-profile-file 中按 event(target)_brand + event(target)_model 匹配（向后兼容）
    4. 如果 watchlist 中 active 竞品只有一个 dominant group，推断为该 group
    5. 无法解析时为 ""，source=unknown
    """
    # Priority 1: manual
    if manual_group:
        return manual_group, "manual"

    # Priority 2: target profile file → our_model first
    if profile_file:
        profiles = load_target_profiles(profile_file)
        if our_brand and our_model:
            ob_lower = our_brand.strip().lower()
            om_lower = our_model.strip().lower()
            for p in profiles:
                if p.get("brand", "").strip().lower() == ob_lower and \
                   p.get("model", "").strip().lower() == om_lower:
                    return p.get("group", ""), "target_profile"
        # Then try event_model (backward compat)
        target_brand_lower = target_brand.strip().lower()
        target_model_lower = target_model.strip().lower()
        for p in profiles:
            if p.get("brand", "").strip().lower() == target_brand_lower and \
               p.get("model", "").strip().lower() == target_model_lower:
                return p.get("group", ""), "target_profile"

    # Priority 3: dominant group in watchlist
    if has_group and entries:
        from collections import Counter
        active_groups = Counter(e.group for e in entries if e.active and e.group)
        if len(active_groups) == 1:
            single_group, count = active_groups.most_common(1)[0]
            return single_group, f"dominant_watchlist_group"

    return "", "unknown"


def _competitor_match_field(e: WatchlistEntry, target_group: str) -> bool:
    """Check if a competitor matches target_group.

    匹配优先级: battle_field_id > ecosystem_group > group
    """
    if e.battle_field_id and e.battle_field_id == target_group:
        return True
    if e.ecosystem_group and e.ecosystem_group == target_group:
        return True
    if e.group and e.group == target_group:
        return True
    return False


def derive_competitors(
    entries: list[WatchlistEntry],
    target_brand: str,
    target_model: str,
    limit: int = 5,
    priority_filter: str | None = None,
    has_group: bool = True,
    has_battle_field: bool = False,
    target_group: str = "",
    target_group_source: str = "unknown",
) -> DerivationResult:
    """从 watchlist 中推导目标车型的竞品列表。

    规则:
    1. 排除目标车型自身（brand+model 匹配）
    2. 通过 battle_field_id 做同战场匹配（优先），fallback 到 ecosystem_group，再 fallback 到 group
    3. 同 group 内按 priority 排序：high > medium > low
    4. 如果同 group 竞品数量不足 limit，再从其他 group 的 high priority 中补充
    5. 最终按 limit 截断
    """
    target_brand_lower = target_brand.strip().lower()
    target_model_lower = target_model.strip().lower()
    result = DerivationResult()
    result.target_group = target_group

    # ── Step 1: Exclude self ────────────────────────────────────
    candidates = []
    for e in entries:
        bl = e.brand.strip().lower()
        ml = e.model.strip().lower()
        if bl == target_brand_lower and ml == target_model_lower:
            continue
        if e.target_id.lower() in (f"{target_brand_lower}_{target_model_lower}",
                                    f"{target_model_lower}_{target_brand_lower}"):
            continue
        candidates.append(e)

    if not candidates:
        result.derivation_note = f"watchlist 中无目标品牌 {target_brand} 的竞品记录"
        return result

    # ── Step 2: Priority filter ──────────────────────────────────
    priority_order = {"high": 0, "medium": 1, "low": 2}
    if priority_filter and priority_filter != "all":
        filtered = [c for c in candidates if c.priority == priority_filter.lower()]
        if filtered:
            candidates = filtered

    # ── Step 3: Determine competitor_match_field ────────────────
    # Priority: use battle_field_id for matching (even if target_group is canonical id)
    # Fallback: ecosystem_group → group
    match_using_bf = has_battle_field and bool(target_group)
    match_using_group = has_group and bool(target_group) and not match_using_bf

    # ── Step 4: Split into same_group and other_group ────────────
    group_available = match_using_bf or match_using_group

    if group_available:
        same_group = [c for c in candidates if _competitor_match_field(c, target_group)]
        other_group = [c for c in candidates if not _competitor_match_field(c, target_group) and (c.group or c.ecosystem_group or c.battle_field_id)]
    else:
        same_group = []
        other_group = candidates

    # Sort same_group by priority
    same_group.sort(key=lambda c: (priority_order.get(c.priority, 99), c.display_name))

    # Sort other_group: high priority first
    other_group.sort(key=lambda c: (priority_order.get(c.priority, 99), c.display_name))

    # ── Step 4: Fill from same_group first, then other_group ─────
    derived = same_group[:limit]
    if len(derived) < limit:
        remaining = limit - len(derived)
        other_high = [c for c in other_group if c.priority == "high"]
        derived.extend(other_high[:remaining])

    result.entries = derived[:limit]

    # ── Step 5: Build derivation note ────────────────────────────
    notes = []
    rule_parts = []
    match_field_name = "none"

    if group_available:
        result.group_filter_applied = True
        if match_using_bf:
            match_field_name = "battle_field_id"
        elif has_battle_field:
            match_field_name = "ecosystem_group"
        else:
            match_field_name = "group"

        same_count = len(same_group)
        other_used = len(derived) - min(same_count, limit)
        if other_used > 0:
            notes.append(f"同战场（{target_group}）竞品 {min(same_count, limit)} 个不足 {limit} 个，从其他战场补充 {other_used} 个 high priority 竞品")
        else:
            notes.append(f"全部 {len(derived)} 个竞品均来自同战场（{target_group}）")
        rule_parts.append(f"优先选择同战场（匹配字段={match_field_name}）")
    else:
        if not has_group and not has_battle_field:
            notes.append("watchlist 缺少 battle_field_id 和 group 字段，退化为按 priority 排序")
            rule_parts.append("因字段缺失，退化为按 priority 排序")
        elif not target_group:
            notes.append(f"target_group 未解析（来源={target_group_source}），退化为按 priority 排序")
            rule_parts.append(f"target_group 未解析，退化为按 priority 排序")
        else:
            notes.append("退化为按 priority 排序")
            rule_parts.append("退化为按 priority 排序")

    if priority_filter and priority_filter != "all":
        rule_parts.append(f"仅保留 priority={priority_filter} 的竞品")
    else:
        rule_parts.append("保留全部 priority 等级的竞品")

    if result.target_group:
        notes.insert(0, f"target_group={target_group}（来源={target_group_source}）")

    result.derivation_note = "；".join(notes) if notes else "无额外过滤条件"
    result.watchlist_filter_rule = "；".join(rule_parts)

    return result


def format_competitor_detail(entries: list[WatchlistEntry], show_ecosystem: bool = False) -> str:
    """Format competitor list into a markdown table."""
    if not entries:
        return "（无，需用户手动指定）"
    if show_ecosystem:
        lines = ["| # | 品牌 | 车型 | battle_field_id | ecosystem_group | 优先级 |",
                 "|---|------|------|----------------|----------------|--------|"]
        for i, e in enumerate(entries, 1):
            bf = e.battle_field_id or e.group or "-"
            eco = e.ecosystem_group or "-"
            lines.append(f"| {i} | {e.brand} | {e.display_name or e.model} | {bf} | {eco} | {e.priority} |")
    else:
        lines = ["| # | 品牌 | 车型 | 竞争分组 | 优先级 |",
                 "|---|------|------|---------|--------|"]
        for i, e in enumerate(entries, 1):
            bf = e.battle_field_id or e.group or "-"
            lines.append(f"| {i} | {e.brand} | {e.display_name or e.model} | {bf} | {e.priority} |")
    return "\n".join(lines)


# ─── Battle Fields / Group Taxonomy ─────────────────────────────


def load_battle_fields(battle_fields_file: str | Path | None) -> list[dict]:
    """加载 battle_fields.yaml，返回活跃战场列表。"""
    if not battle_fields_file:
        return []
    path = Path(battle_fields_file)
    if not path.exists():
        print(f"[WARN] battle fields 文件不存在: {path}", file=sys.stderr)
        return []
    try:
        cfg = load_yaml(path)
        return cfg.get("battle_fields", [])
    except Exception as e:
        print(f"[WARN] battle fields 文件解析失败: {e}", file=sys.stderr)
        return []


def build_group_alias_map(battle_fields: list[dict]) -> dict[str, str]:
    """构建别名 → group_id 的映射表。

    输入: battle_fields = [{"id": "large_six_seat_suv", "label": "大六座新能源 SUV", "aliases": [...]}]
    输出: {"大六座新能源 SUV": "large_six_seat_suv", "大六座新能源SUV": "large_six_seat_suv", ...}
    """
    alias_map = {}
    for bf in battle_fields:
        gid = bf["id"]
        # label 本身作为别名
        alias_map[bf["label"]] = gid
        # 所有 aliases
        for alias in bf.get("aliases", []):
            alias_map[alias] = gid
    return alias_map


def normalize_group(raw_group: str, alias_map: dict[str, str]) -> tuple[str, str, bool]:
    """归一化原始 group 字符串为 canonical group_id。

    返回: (group_id, label, matched)
      - 如果匹配到别名: (canonical_id, label, True)
      - 如果未匹配: (raw_group, raw_group, False)
    """
    raw = raw_group.strip()
    if not raw:
        return "", "", False
    gid = alias_map.get(raw)
    if gid:
        # Find label for this gid
        return gid, raw, True
    return raw, raw, False


def _build_impact_module(event_brand: str, event_model: str, our_brand: str, our_model: str) -> str:
    """Build the impact assessment module section based on whether our_model is specified."""
    has_our = bool(our_brand and our_model) and our_brand != "（未指定）" and our_model != "（未指定）"

    if has_our:
        return f"""### 模块6：对我方车型影响判断

**目标**：判断 **event_model（{event_brand} {event_model}）** 本次事件对 **our_model（{our_brand} {our_model}）** 的潜在影响，并结合 competitor_context 判断战场压力。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 目标用户重叠 | event_model 与 our_model 的用户画像重叠度 | 综合判断 |
| 价格带重叠 | event_model 与 our_model 的价格区间重叠 | 综合判断 |
| 产品形态重叠 | 车身形式/级别/能源形式重叠 | 综合判断 |
| 战场压力 | 结合 competitor_context 判断 event_model 加入后战场竞争强度变化 | 综合判断 |
| 威胁评估 | 高/中/低威胁判断 | 综合判断 |
| 建议应对 | 是否需要调整我方产品/营销策略 | 综合判断 |"""
    else:
        return f"""### 模块6：市场事件影响分析

**目标**：分析 **{event_brand} {event_model}** 本次事件的市场影响，收集价格、权益、配置、舆论、竞品对标等信息，评估其市场定位和竞争力。

| 检索项 | 说明 | 预期来源 |
|--------|------|----------|
| 市场定位 | 该车型的细分市场和目标用户 | 综合判断 |
| 价格竞争力 | 与同价位车型的性价比对比 | 综合判断 |
| 产品差异化 | 相比同级别车型的核心差异化卖点 | 综合判断 |
| 舆论热度 | 媒体和用户对该事件的关注度 | 综合判断 |
| 竞争格局影响 | 该事件对该细分市场竞争格局的可能影响 | 综合判断 |"""


# ─── Main ────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(
        description="Auto Launch Promptbuilder — 生成新车上市/预售/发布会等市场事件的 AI 搜索 Prompt"
    )
    # Core role params
    p.add_argument("--event-brand", help="事件车型品牌（与 --event-model 搭配）")
    p.add_argument("--event-model", help="事件车型（本次发生上市/预售/发布等事件的车型）")
    p.add_argument("--our-brand", default="", help="我方本品品牌（被影响车型）")
    p.add_argument("--our-model", default="", help="我方本品车型（被影响车型）")
    # Deprecated aliases
    p.add_argument("--brand", help="[DEPRECATED] 请改用 --event-brand")
    p.add_argument("--model", help="[DEPRECATED] 请改用 --event-model")
    p.add_argument("--target-group", help="手动指定目标竞争分组（最高优先级）")
    # Other params
    p.add_argument("--event-type", required=True, help="事件类型（必填）：上市/预售/发布会/首发亮相/配置公布/价格公布/开启交付/改款上市/限时权益调整/官方调价")
    p.add_argument("--event-date", help="事件日期（与 --window 搭配使用，格式 YYYY-MM-DD）")
    p.add_argument("--window", default="7d", choices=["48h", "72h", "7d", "14d"], help="时间窗口（默认 7d）")
    p.add_argument("--start", help="自定义开始日期（优先级高于 event-date，格式 YYYY-MM-DD）")
    p.add_argument("--end", help="自定义结束日期（格式 YYYY-MM-DD）")
    p.add_argument("--competitors", help="手动指定竞品列表（逗号分隔，优先级高于 watchlist 推导）")
    p.add_argument("--targets-file", help="watchlist CSV 文件路径（如 mashang_workspace/configs/ls8_competitor_watchlist.csv）")
    p.add_argument("--target-profile-file", help="model profile YAML 文件路径（如 promptbuilders/auto_launch/configs/target_profiles.yaml）")
    p.add_argument("--battle-fields-file", help="battle fields YAML 文件路径（如 promptbuilders/auto_launch/configs/battle_fields.yaml）")
    p.add_argument("--competitor-limit", type=int, default=5, help="从 watchlist 推导竞品的最大数量（默认 5）")
    p.add_argument("--include-priority", default="all", choices=["high", "medium", "all"], help="从 watchlist 推导竞品时按优先级筛选（默认 all）")
    p.add_argument("--output", default=None, help="输出文件路径")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    # Resolve role params with deprecation warnings
    event_brand = args.event_brand or args.brand or ""
    event_model = args.event_model or args.model or ""
    our_brand = args.our_brand or ""
    our_model = args.our_model or ""

    if args.brand or args.model:
        print("[DEPRECATED] --brand / --model 已弃用，请改用 --event-brand / --event-model", file=sys.stderr)

    if not event_brand or not event_model:
        p.error("请提供 --event-brand 和 --event-model（或使用已弃用的 --brand / --model）")

    if not TEMPLATES_DIR.exists():
        print(f"[ERROR] templates 目录不存在: {TEMPLATES_DIR}", file=sys.stderr)
        sys.exit(1)

    # Load configs
    try:
        event_types_cfg = load_yaml(CONFIGS_DIR / "event_types.yaml")
        event_types = event_types_cfg["event_types"]
    except FileNotFoundError as e:
        print(f"[ERROR] 配置文件缺失: {e}", file=sys.stderr)
        sys.exit(1)

    # Find event type
    et = find_event_type(event_types, args.event_type)
    if not et:
        print(f"[ERROR] 不支持的事件类型: {args.event_type}", file=sys.stderr)
        print(f"  支持的类型: {', '.join(e['name'] for e in event_types)}", file=sys.stderr)
        sys.exit(1)

    # Compute time window
    time_start, time_end, time_desc = compute_time_window(
        args.event_date, args.window, args.start, args.end,
    )

    # ── Battle Fields / Group Taxonomy Normalization ──────────
    battle_fields = load_battle_fields(args.battle_fields_file)
    alias_map = build_group_alias_map(battle_fields)
    group_normalization_applied = bool(alias_map)
    if group_normalization_applied:
        print(f"[INFO] Group taxonomy loaded: {len(battle_fields)} battle fields, {len(alias_map)} aliases", file=sys.stderr)

    # ── Target Profile / Battle Field Resolver ────────────────
    manual_group = args.target_group
    profile_file_path = args.target_profile_file

    # Resolve target_group before watchlist operations (used by derive_competitors)
    entries_all: list[WatchlistEntry] = []
    watchlist_field_meta: dict = {}
    if args.targets_file and not args.competitors:
        entries_all, watchlist_field_meta = load_watchlist(args.targets_file)

        # Apply group normalization to watchlist entries if alias map is available
        if group_normalization_applied:
            for e in entries_all:
                # Normalize battle_field_id first (if field exists)
                if e.battle_field_id:
                    gid, label, matched = normalize_group(e.battle_field_id, alias_map)
                    if matched:
                        e.battle_field_id = gid
                # Normalize ecosystem_group
                if e.ecosystem_group:
                    gid, label, matched = normalize_group(e.ecosystem_group, alias_map)
                    if matched:
                        e.ecosystem_group = gid
                # Normalize legacy group
                if e.group:
                    gid, label, matched = normalize_group(e.group, alias_map)
                    if matched:
                        e.group = gid

    resolved_group, resolved_group_source = resolve_target_group(
        target_brand=event_brand,
        target_model=event_model,
        entries=entries_all,
        has_group=watchlist_field_meta.get("has_group", False),
        manual_group=manual_group,
        profile_file=profile_file_path,
        our_brand=our_brand,
        our_model=our_model,
    )

    # Normalize resolved target_group if alias map available
    if group_normalization_applied and resolved_group:
        gid, label, matched = normalize_group(resolved_group, alias_map)
        if matched:
            resolved_group = gid  # Use canonical group_id for matching

    # ── Watchlist Adapter ──────────────────────────────────────
    competitor_source = "user_provided_required"
    competitor_detail_text = ""
    competitor_list_str = args.competitors or ""
    targets_file_path = str(args.targets_file) if args.targets_file else ""
    dr = DerivationResult()
    field_meta = watchlist_field_meta

    if args.competitors:
        competitor_source = "manual"
        competitor_list_str = args.competitors
    elif args.targets_file:
        dr = derive_competitors(
            entries_all,
            target_brand=event_brand,
            target_model=event_model,
            limit=args.competitor_limit,
            priority_filter=args.include_priority,
            has_group=field_meta.get("has_group", False),
            has_battle_field=field_meta.get("has_battle_field", False),
            target_group=resolved_group,
            target_group_source=resolved_group_source,
        )
        if dr.entries:
            competitor_source = "watchlist"
            competitor_list_str = ", ".join(e.display_name or f"{e.brand} {e.model}" for e in dr.entries)
            has_eco = field_meta.get("has_ecosystem_group", False)
            competitor_detail_text = format_competitor_detail(dr.entries, show_ecosystem=has_eco)
        else:
            competitor_source = "watchlist_empty"
            competitor_list_str = "未从 watchlist 中推导出竞品（可能目标车型不在 watchlist 中）"
    else:
        competitor_source = "user_provided_required"
        competitor_list_str = "未指定（需用户手动补充）"

    # Build derivation metadata
    using_watchlist = args.targets_file and not args.competitors
    target_group = resolved_group
    target_group_source = resolved_group_source
    group_field_available = "是" if field_meta.get("has_group", False) else "否"
    target_group_resolved = "是" if resolved_group else "否"
    gn_applied = "是" if group_normalization_applied else "否"

    has_bf = field_meta.get("has_battle_field", False)

    if using_watchlist:
        derivation_note = dr.derivation_note
        watchlist_filter_rule = dr.watchlist_filter_rule
        active_filter_applied = "是" if field_meta.get("has_active", False) else "否（字段缺失）"
        group_filter_applied = "是" if dr.group_filter_applied else "否"
        competitor_match_field = "battle_field_id" if has_bf else ("ecosystem_group" if field_meta.get("has_ecosystem_group", False) else "group")
        battle_field_field_available = "是" if has_bf else "否"
        ecosystem_group_available = "是" if field_meta.get("has_ecosystem_group", False) else "否"

        # Compute same_group_competitor_count using _competitor_match_field
        if dr.group_filter_applied and resolved_group:
            same_count = sum(1 for e in dr.entries if _competitor_match_field(e, resolved_group))
            supplemented = len(dr.entries) - same_count
        else:
            same_count = 0
            supplemented = len(dr.entries)

        # Group taxonomy warning (only when same_count == 0 despite having battle_field_id)
        group_taxonomy_warning = ""
        if same_count == 0 and supplemented > 0 and has_bf and resolved_group:
            # Show which battle_field_ids exist in the watchlist
            all_bfs = set(e.battle_field_id for e in entries_all if e.battle_field_id)
            group_taxonomy_warning = (
                f"target_group_id={resolved_group}，但 watchlist 中无同战场竞品。"
                f"watchlist 中实际 battle_field_id 分布：{', '.join(sorted(all_bfs))}。"
                f"建议：更新 watchlist CSV 中相关竞品的 battle_field_id 字段。"
            )

        if not dr.group_filter_applied and field_meta.get("has_group", False) and not resolved_group:
            fallback_rule = "priority_only（target_group 未解析）"
        elif not dr.group_filter_applied and not field_meta.get("has_group", False) and not has_bf:
            fallback_rule = "priority_only（battle_field_id 和 group 字段均缺失）"
        else:
            fallback_rule = "无"
    else:
        derivation_note = ""
        watchlist_filter_rule = ""
        active_filter_applied = ""
        group_filter_applied = ""
        fallback_rule = ""
        same_count = 0
        supplemented = 0
        group_taxonomy_warning = ""
        gn_applied = ""
        competitor_match_field = ""
        battle_field_field_available = ""
        ecosystem_group_available = ""

    # Build rendering context
    context = {
        "event_brand": event_brand,
        "event_model": event_model,
        "our_brand": our_brand or "（未指定）",
        "our_model": our_model or "（未指定）",
        "event_type_name": et["name"],
        "event_type_id": et["id"],
        "event_type_definition": format_event_type_definition(et),
        "time_window_start": time_start,
        "time_window_end": time_end,
        "time_window_desc": time_desc,
        "competitors": competitor_list_str,
        "competitor_source": competitor_source,
        "competitor_detail": competitor_detail_text,
        "brand": event_brand,
        "model": event_model,
        "target_brand": event_brand,
        "target_model": event_model,
        "target_group": target_group,
        "target_group_source": target_group_source,
        "include_priority": args.include_priority,
        "targets_file_path": targets_file_path,
        "group_field_available": group_field_available,
        "target_group_resolved": target_group_resolved,
        "group_normalization_applied": gn_applied,
        "same_group_competitor_count": str(same_count),
        "supplemented_from_other_groups": str(supplemented),
        "group_taxonomy_warning": group_taxonomy_warning,
        "battle_field_field_available": battle_field_field_available,
        "ecosystem_group_available": ecosystem_group_available,
        "competitor_match_field": competitor_match_field,
        "same_battle_field_competitor_count": str(same_count),
        "watchlist_filter_rule": watchlist_filter_rule,
        "competitor_derivation_note": derivation_note,
        "active_filter_applied": active_filter_applied,
        "group_filter_applied": group_filter_applied,
        "fallback_rule": fallback_rule,
        "impact_module_section": _build_impact_module(event_brand, event_model, our_brand, our_model),
    }

    # Load template
    template_text = load_text(TEMPLATES_DIR / "search_task_prompt.md")

    # Render placeholders
    rendered = template_text
    placeholder_map = {
        "{{ event_brand }}": context["event_brand"],
        "{{ event_model }}": context["event_model"],
        "{{ our_brand }}": context["our_brand"],
        "{{ our_model }}": context["our_model"],
        "{{ brand }}": context["brand"],
        "{{ model }}": context["model"],
        "{{ event_type_name }}": context["event_type_name"],
        "{{ event_type_id }}": context["event_type_id"],
        "{{ event_type_definition }}": context["event_type_definition"],
        "{{ time_window_start }}": context["time_window_start"],
        "{{ time_window_end }}": context["time_window_end"],
        "{{ time_window_desc }}": context["time_window_desc"],
        "{{ competitors }}": context["competitors"],
        "{{ competitor_source }}": context["competitor_source"],
        "{{ competitor_detail }}": context["competitor_detail"],
        "{{ target_brand }}": context["target_brand"],
        "{{ target_model }}": context["target_model"],
        "{{ include_priority }}": context["include_priority"],
        "{{ targets_file_path }}": context["targets_file_path"],
        "{{ target_group }}": context["target_group"],
        "{{ watchlist_filter_rule }}": context["watchlist_filter_rule"],
        "{{ competitor_derivation_note }}": context["competitor_derivation_note"],
        "{{ active_filter_applied }}": context["active_filter_applied"],
        "{{ group_filter_applied }}": context["group_filter_applied"],
        "{{ target_group_source }}": context["target_group_source"],
        "{{ group_field_available }}": context["group_field_available"],
        "{{ target_group_resolved }}": context["target_group_resolved"],
        "{{ group_normalization_applied }}": context["group_normalization_applied"],
        "{{ same_group_competitor_count }}": context["same_group_competitor_count"],
        "{{ supplemented_from_other_groups }}": context["supplemented_from_other_groups"],
        "{{ group_taxonomy_warning }}": context["group_taxonomy_warning"],
        "{{ battle_field_field_available }}": context["battle_field_field_available"],
        "{{ ecosystem_group_available }}": context["ecosystem_group_available"],
        "{{ competitor_match_field }}": context["competitor_match_field"],
        "{{ same_battle_field_competitor_count }}": context["same_battle_field_competitor_count"],
        "{{ fallback_rule }}": context["fallback_rule"],
        "{{ impact_module_section }}": context["impact_module_section"],
    }
    for placeholder, value in placeholder_map.items():
        rendered = rendered.replace(placeholder, value)

    # Load evidence schema for summary insertion
    evidence_schema = load_json(TEMPLATES_DIR / "evidence_schema.json")
    schema_summary = json.dumps(evidence_schema, ensure_ascii=False, indent=2)[:2000]
    rendered = rendered.replace("{{ evidence_schema_summary }}", schema_summary)

    # Output
    if args.output:
        out_path = build_output_dir(args.output)
        out_path.write_text(rendered, encoding="utf-8")
        if args.format != "json":
            print(f"[OK] 搜索 Prompt 已生成: {out_path}")
    else:
        if args.format == "json":
            print(json.dumps({
                "status": "success",
                "prompt": rendered,
                "context": context,
            }, ensure_ascii=False, indent=2))
        else:
            print(rendered)

    if args.format == "json" and args.output:
        print(json.dumps({
            "status": "success",
            "output_path": str(out_path),
            "context": context,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
