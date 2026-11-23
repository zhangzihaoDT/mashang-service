#!/usr/bin/env python
"""用本地滚动导出及年度配置快照重建 dataset/config_attribute.parquet。

输入位于 dataset/tableau-hs/configuration/，包括
config_attribute_data_update.csv 和 config_attribute_data_YYYY.csv
（2022–2026 及后续快照）。输出包含属性编码 attribute_code 和取值编码
value_code，按 (Order Number, Attribute) 去重，滚动导出及较新年份优先。
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dataset.updater.order_config_to_parquet import (
    CONFIG_SNAPSHOT_SUBDIR,
    DATASET_DIR,
    rebuild_config_parquet,
)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    rebuild_config_parquet(
        DATASET_DIR / CONFIG_SNAPSHOT_SUBDIR,
        DATASET_DIR / "order_data.parquet",
        DATASET_DIR / "config_attribute.parquet",
    )


if __name__ == "__main__":
    main()
