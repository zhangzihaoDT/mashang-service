#!/usr/bin/env python3
"""
MIIT 模块统一路径与批次配置入口（唯一 I/O 基座）。

按 5 类资产组织：reports / data / scripts / runs / workflow。
data/ 二级目录按内容直白命名；所有脚本平铺在 scripts/，只从这里解析路径与批次配置。
"""

import functools
from pathlib import Path

import yaml

# ── 根目录 ────────────────────────────────────────────────────────
MIIT_ROOT = Path(__file__).resolve().parents[1]

# ⑤ 规则/规划/配置（workflow/，配置文件直接平铺于此）
WORKFLOW_DIR = MIIT_ROOT / "workflow"
SCHEMAS_DIR = WORKFLOW_DIR / "schemas"
WORKFLOW_DOCS_DIR = WORKFLOW_DIR / "docs"

# ② 事实与中间数据（data/，二级目录按内容命名）
DATA_DIR = MIIT_ROOT / "data"
SEARCH_RESULTS_DIR = DATA_DIR / "search_results"        # P1 品牌/车型搜索结果（scan 快照）
VEHICLE_DETAILS_DIR = DATA_DIR / "vehicle_details"      # P2 车型完整参数归档（{型号}-{产品名}.md）
VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"        # P2 公告照片（{型号}/ 下）
RAW_HTML_DIR = DATA_DIR / "raw_html"                    # P2 原始详情页缓存
VEHICLE_TAX_DIR = DATA_DIR / "vehicle_tax"              # P3 车船税 doc/txt/json/md
VEHICLE_PARAMETERS_DIR = DATA_DIR / "vehicle_parameters"  # 结构化车型参数（canonical 目标层）
WIDE_TABLES_DIR = DATA_DIR / "wide_tables"              # P4 参数宽表 csv/md
FETCH_STATUS_DIR = DATA_DIR / "fetch_status"            # P2 checkpoint / 抓取状态
EIDC_DIR = DATA_DIR / "eidc"                            # EIDC 历史批次归档（401-408, confirmed 层）

# ① 最终报告（reports/）
REPORTS_DIR = MIIT_ROOT / "reports"
# ④ 运行记录（runs/）
RUNS_DIR = MIIT_ROOT / "runs"
# ③ 执行能力（scripts/）
SCRIPTS_DIR = MIIT_ROOT / "scripts"

# 配置文件（workflow/ 平铺）
WATCHLIST_PATH = WORKFLOW_DIR / "brand_watchlist.yaml"
NAME_MAP_PATH = WORKFLOW_DIR / "model_name_map.json"
BATCHES_PATH = WORKFLOW_DIR / "batches.yaml"

# 批次索引文档（01_scan_batch 管线会更新它）
BATCH_INDEX_DOC = WORKFLOW_DOCS_DIR / "公告批次.md"

DEFAULT_BATCH = "409"


# ── 车型身份（canonical key）─────────────────────────────────────

def vehicle_record_id(batch: str, model_code: str) -> str:
    """车型记录唯一身份：`{batch_no}:{model_code}`。

    不假设 model_code 全局唯一——同一型号未来可能在不同批次再次申报
    （参数变更/扩展/重新申报），必须用批次号区分版本。
    """
    return f"{batch}:{model_code}"


# ── 按批次的目录/文件解析 ─────────────────────────────────────────

def batch_reports_dir(batch: str) -> Path:
    """reports/batch_{batch}/ —— 该批最终给人看的报告"""
    return REPORTS_DIR / f"batch_{batch}"


def batch_runs_path(batch: str) -> Path:
    """runs/batch_{batch}.md —— 该批运行记录/经验沉淀（单文件）"""
    return RUNS_DIR / f"batch_{batch}.md"


def scan_path(batch: str) -> Path:
    """P1 扫描快照（含 JSON 块，可重放）。"""
    return SEARCH_RESULTS_DIR / get_batch_config(batch).get(
        "scan_file", f"scan_batch_{batch}.md")


def tax_json_path(batch: str) -> Path:
    """P3 车船税结构化 JSON。"""
    return VEHICLE_TAX_DIR / get_batch_config(batch).get(
        "tax_file", f"车型清单_第{batch}批车船税.json")


def wide_table_path(batch: str, suffix: str) -> Path:
    """P4 参数宽表文件（csv/md），按批号区分文件名。"""
    return WIDE_TABLES_DIR / f"wide_table_{batch}{suffix}"


def detail_md_path(batch: str, model_code: str, product_name: str) -> Path:
    """P2 车型参数归档 .md：`{batch}_{model_code}-{产品名}.md`。"""
    return VEHICLE_DETAILS_DIR / f"{batch}_{model_code}-{product_name}.md"


def photo_dir(batch: str, model_code: str) -> Path:
    """P2 车型公告照片目录：`{batch}_{model_code}/`。"""
    return VEHICLE_PHOTOS_DIR / f"{batch}_{model_code}"


def raw_html_path(batch: str, model_code: str) -> Path:
    """P2 原始详情页缓存：`{batch}_{model_code}.html`。"""
    return RAW_HTML_DIR / f"{batch}_{model_code}.html"


def fetch_status_path(batch: str) -> Path:
    """P2 抓取 checkpoint 文件。"""
    return FETCH_STATUS_DIR / f"fetch_status_{batch}.json"


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 批次配置（唯一来源 workflow/batches.yaml）──────────────────────

@functools.lru_cache(maxsize=None)
def load_batches() -> dict:
    """读取 workflow/batches.yaml 全部批次配置（批次号统一为字符串键）。"""
    with open(BATCHES_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {str(k): v for k, v in raw.items()}


def get_batch_config(batch: str) -> dict:
    """返回批次配置；未登记批次回退到默认批（保持旧行为）。"""
    cfg = load_batches().get(str(batch))
    if cfg is None:
        return load_batches()[DEFAULT_BATCH]
    return cfg
