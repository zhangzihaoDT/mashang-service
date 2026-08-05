"""model_positioning_loader — 车型定位唯一事实源加载器。

读取 shared/schema/model_positioning.yaml，向各分析模块统一提供车型知识：
产品定位 / 目标人群 / 核心场景 / 细分市场(segment) / 品牌使命(priority)。

消费场景：
- 车型对比 / Brandmine 车型分析     → load_model_positioning / get_model_positioning
- 竞品自动归类（同级车型）          → get_models_by_segment / list_segments
- 用户画像分析                      → target_users
- 营销事件标签（家庭/运动/商务）     → selling_points / core_scenario / priority
- AI 自动生成车型介绍               → 全量 dict
- 新车型扩展                        → list_models

唯一事实源原则：各模块不应另维护一套车型定位知识，统一从此文件读取。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def get_service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_model_positioning_path() -> Path:
    return get_service_root() / "shared" / "schema" / "model_positioning.yaml"


@functools.lru_cache(maxsize=1)
def load_model_positioning() -> Dict[str, Any]:
    """加载完整车型定位表（keyed by 车型 code）。"""
    if yaml is None:
        raise ImportError("PyYAML is required to load model positioning")
    path = get_model_positioning_path()
    if not path.exists():
        raise FileNotFoundError(f"model_positioning.yaml not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(data.get("model_positioning", {}))


@functools.lru_cache(maxsize=1)
def load_product_archetypes() -> Dict[str, Any]:
    """加载车型→产品赛道映射（含自研 + 竞品）。"""
    data = _load_raw()
    return dict(data.get("product_archetype", {}))


@functools.lru_cache(maxsize=1)
def load_archetype_definitions() -> Dict[str, Any]:
    """加载产品赛道定义（label / needs）。"""
    data = _load_raw()
    return dict(data.get("product_archetypes", {}))


def _load_raw() -> Dict[str, Any]:
    if yaml is None:
        raise ImportError("PyYAML is required to load model positioning")
    path = get_model_positioning_path()
    if not path.exists():
        raise FileNotFoundError(f"model_positioning.yaml not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_models() -> List[str]:
    """返回全部车型 code。"""
    return list(load_model_positioning().keys())


def get_model_positioning(model: str) -> Optional[Dict[str, Any]]:
    """返回单个车型定位 dict，不存在时返回 None。"""
    return load_model_positioning().get(model)


def get_model_segment(model: str) -> Optional[str]:
    """返回车型的细分市场（segment），如 midsize_suv / fullsize_suv。"""
    info = get_model_positioning(model)
    return info.get("segment") if info else None


def get_model_priority(model: str) -> Optional[str]:
    """返回车型的品牌使命（priority），如 volume / flagship。"""
    info = get_model_positioning(model)
    return info.get("priority") if info else None


def list_segments() -> List[str]:
    """返回全部细分市场。"""
    return sorted(
        {info.get("segment") for info in load_model_positioning().values() if info.get("segment")}
    )


def get_models_by_segment(segment: str) -> List[str]:
    """按细分市场返回车型列表（用于竞品归类）。"""
    return [
        m for m, info in load_model_positioning().items()
        if info.get("segment") == segment
    ]


def get_models_by_priority(priority: str) -> List[str]:
    """按品牌使命返回车型列表。"""
    return [
        m for m, info in load_model_positioning().items()
        if info.get("priority") == priority
    ]


def get_models_by_tag(tag: str) -> List[str]:
    """按卖点/场景标签返回车型列表（如 tag='家庭' / '运动' / '商务'）。"""
    tag_lower = tag.lower()
    result = []
    for m, info in load_model_positioning().items():
        sp = [str(s).lower() for s in info.get("selling_points", [])]
        sc = [str(s).lower() for s in info.get("core_scenario", [])]
        if tag_lower in sp or tag_lower in sc or tag_lower in str(info.get("note", "")).lower():
            result.append(m)
    return result


def get_model_archetype(model: str) -> Optional[str]:
    """返回车型的产品赛道（archetype），优先自研定位表，其次竞品映射。"""
    info = get_model_positioning(model)
    if info and info.get("archetype"):
        return info["archetype"]
    return load_product_archetypes().get(model)


def get_models_by_archetype(archetype: str) -> List[str]:
    """按产品赛道返回车型列表（含自研 + 竞品，用于赛道聚类）。"""
    return [
        m for m, a in load_product_archetypes().items()
        if a == archetype
    ]


def get_archetype_definition(archetype: str) -> Optional[Dict[str, Any]]:
    """返回产品赛道定义（label / needs）。"""
    return load_archetype_definitions().get(archetype)


def get_competitor_models(model: str) -> List[str]:
    """返回同赛道竞品车型列表（不含自身；仅覆盖 product_archetype 中登记的竞品）。"""
    archetype = get_model_archetype(model)
    if not archetype:
        return []
    return [m for m in get_models_by_archetype(archetype) if m != model]


def get_competitors(model: str, tier: Optional[str] = None) -> List[str]:
    """返回车型登记的 tier 化竞品列表。

    - tier=None: 返回 {tier1: [...], tier2: [...]} dict
    - tier='tier1': 返回该层竞品列表
    """
    info = get_model_positioning(model)
    competitors = dict(info.get("competitors", {})) if info else {}
    if tier:
        return list(competitors.get(tier, []))
    return list(competitors.get("tier1", [])) + list(competitors.get("tier2", []))


def get_competitors_by_tier(model: str) -> Dict[str, List[str]]:
    """返回 {tier1: [...], tier2: [...]} 结构（保留层级）。"""
    info = get_model_positioning(model)
    return dict(info.get("competitors", {})) if info else {}
