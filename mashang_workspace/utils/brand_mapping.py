"""brand_watchlist 品牌名 → TP&MIX-ways 数据集品牌值 映射工具。

research_apps/MIIT/workflow/brand_watchlist.yaml 中的品牌名为业务显示名（如"问界"/"爱咖"），
与数据集品牌维度实际取值（如 AITO/iCAR）不一致。在数据集上按品牌匹配
（销量/份额等）时，先用本模块归一化。brand_watchlist.yaml 本身保持不变，
MIIT 公告搜索仍使用其中的显示名做关键词。
"""

from pathlib import Path
from typing import Dict, List, Tuple

import yaml

ALIAS_MAP_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "brand_alias_map.yaml"
)


def load_brand_alias_map() -> Dict[str, str]:
    """加载 watchlist 品牌名 → 数据集品牌值 映射。"""
    if not ALIAS_MAP_PATH.exists():
        return {}
    data = yaml.safe_load(ALIAS_MAP_PATH.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def resolve_dataset_brand(watchlist_brand: str) -> str:
    """把 watchlist 品牌名映射为数据集品牌值；无映射时原样返回。"""
    return load_brand_alias_map().get(watchlist_brand, watchlist_brand)


def normalize_watchlist_brands(watchlist: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """对 watchlist 各分组的品牌列表做数据集品牌值归一化。

    返回 {分组名: [数据集品牌值, ...]}。未建立映射的品牌透传原值，
    消费方需自行处理"数据集无此品牌"的情况。
    """
    alias_map = load_brand_alias_map()
    return {
        group: [alias_map.get(b, b) for b in brands]
        for group, brands in watchlist.items()
    }


def watchlist_brand_coverage(watchlist: Dict[str, List[str]]) -> List[Tuple[str, str, bool]]:
    """返回 [(分组, 品牌, 数据集中是否可匹配)] 清单，便于核对覆盖情况。"""
    alias_map = load_brand_alias_map()
    return [
        (group, brand, brand in alias_map or brand == alias_map.get(brand, brand))
        for group, brands in watchlist.items()
        for brand in brands
    ]
