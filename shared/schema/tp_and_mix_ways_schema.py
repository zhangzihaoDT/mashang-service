from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class TpAndMixWaysTableDef:
    table_name: str
    source_csv: str
    parquet_path: str
    grain: List[str]
    dimensions: List[str]
    metrics: List[str]
    purpose: str
    recommended_questions: List[str] = field(default_factory=list)


TP_AND_MIX_WAYS_TABLES: List[TpAndMixWaysTableDef] = [
    TpAndMixWaysTableDef(
        table_name="market_energy_monthly",
        source_csv="way1_market_energy_monthly_data.csv",
        parquet_path="market_energy_monthly.parquet",
        grain=["date_month", "fuel_type_group", "fuel_type"],
        dimensions=["date_month", "fuel_type_group", "fuel_type"],
        metrics=["sales", "weighted_tp"],
        purpose="市场总量、能源结构、新能源/燃油/纯电/插混/增程走势、价格重心",
        recommended_questions=[
            "月度乘用车市场总量趋势",
            "新能源渗透率走势",
            "纯电/插混/增程销量结构",
            "各燃料类型价格重心变化",
        ],
    ),
    TpAndMixWaysTableDef(
        table_name="brand_monthly",
        source_csv="way2_brand_monthly_data.csv",
        parquet_path="brand_monthly.parquet",
        grain=["date_month", "brand"],
        dimensions=[
            "date_month", "brand", "brand_group", "brand_luxury_group",
            "oem_group", "oem", "brand_country", "ownership_type", "domestic_import",
        ],
        metrics=["sales", "weighted_tp"],
        purpose="品牌排名、品牌份额、品牌价格重心、品牌分组竞争",
        recommended_questions=[
            "月度品牌销量排名 Top20",
            "豪华品牌市场份额变化",
            "新势力品牌价格重心",
            "自主/合资/豪华品牌分组对比",
        ],
    ),
    TpAndMixWaysTableDef(
        table_name="model_monthly",
        source_csv="way3_model_monthly_data.csv",
        parquet_path="model_monthly.parquet",
        grain=["date_month", "brand", "model", "sub_model", "sub_model_id"],
        dimensions=[
            "date_month", "brand", "brand_series", "model", "sub_model",
            "sub_model_id", "fuel_type", "fuel_type_group", "body_type",
            "vehicle_level", "vehicle_level_group", "saic_segment",
            "drive_type", "drive_type_group",
        ],
        metrics=["sales", "weighted_tp"],
        purpose="车型排名、车型趋势、品牌内部车型结构、车型级别/燃料/驱动结构",
        recommended_questions=[
            "月度车型销量排名 Top20",
            "品牌内部车型销量结构",
            "各车型价格重心对比",
            "车型级别 × 燃料类型的销量分布",
        ],
    ),
    TpAndMixWaysTableDef(
        table_name="geo_monthly",
        source_csv="way4_geo_monthly_data.csv",
        parquet_path="geo_monthly.parquet",
        grain=["date_month", "province", "city", "city_tier_group", "fuel_type_group"],
        dimensions=[
            "date_month", "province", "city", "region_group",
            "city_tier_2025", "city_tier_group", "fuel_type_group",
        ],
        metrics=["sales", "weighted_tp"],
        purpose="省市市场、城市线级结构、区域市场、新能源区域渗透",
        recommended_questions=[
            "省份月度销量排名 Top10",
            "城市线级销量结构",
            "华东/华南区域新能源渗透率",
            "各城市价格重心差异",
        ],
    ),
    TpAndMixWaysTableDef(
        table_name="price_segment_monthly",
        source_csv="way5_price_segment_monthly_data.csv",
        parquet_path="price_segment_monthly.parquet",
        grain=["date_month", "tp_bucket_5w", "tp_bucket_10w", "fuel_type_group", "body_type", "vehicle_level_group"],
        dimensions=[
            "date_month", "tp_bucket_5w", "tp_bucket_10w",
            "fuel_type_group", "body_type", "vehicle_level_group",
        ],
        metrics=["sales", "weighted_tp"],
        purpose="价格带市场、20-30 万市场容量、价格结构、价格带 × 能源 × 车身 × 级别",
        recommended_questions=[
            "各价格带月度销量分布",
            "20-30万价格带市场容量",
            "价格带 × 燃料类型交叉分析",
            "价格重心在价格带间的差异",
        ],
    ),
    TpAndMixWaysTableDef(
        table_name="product_segment_monthly",
        source_csv="way6_product_segment_monthly_data.csv",
        parquet_path="product_segment_monthly.parquet",
        grain=["date_month", "saic_segment", "body_type", "vehicle_level", "vehicle_level_group", "fuel_type_group", "drive_type_group"],
        dimensions=[
            "date_month", "saic_segment", "body_type", "vehicle_level",
            "vehicle_level_group", "fuel_type_group", "drive_type_group",
        ],
        metrics=[
            "sales", "weighted_tp", "weighted_length_mm",
            "weighted_width_mm", "weighted_height_mm", "weighted_wheelbase_mm",
        ],
        purpose="细分市场、车身结构、级别结构、驱动结构、大车化趋势、产品尺寸重心",
        recommended_questions=[
            "上汽细分市场销量结构",
            "SUV/轿车/MPV 车身结构趋势",
            "各级别车型平均尺寸变化",
            "驱动形式(两驱/四驱)销量占比",
        ],
    ),
]


def get_table_def(table_name: str) -> TpAndMixWaysTableDef | None:
    for t in TP_AND_MIX_WAYS_TABLES:
        if t.table_name == table_name:
            return t
    return None


def list_table_names() -> List[str]:
    return [t.table_name for t in TP_AND_MIX_WAYS_TABLES]
