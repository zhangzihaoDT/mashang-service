"""CPCA 简报出口读取适配层。

数据源是 ``mashang-data`` 平台发布的只读契约::

    exports/cpca/briefing.v1.json

本 loader 只负责路径解析、契约版本检查和常用查询，不改写数据，
也不重新计算指标。完整字段与口径见 ``mashang-data/docs/cpca-briefing.md``。

路径解析顺序：

1. 调用参数 ``path``
2. 环境变量 ``MASHANG_DATA_CPCA_BRIEFING``
3. 默认平级仓库 ``../mashang-data/exports/cpca/briefing.v1.json``

典型用法::

    from shared.loaders.cpca_briefing_loader import (
        latest_cpca_briefing,
        get_cpca_briefing_section,
    )

    edition = latest_cpca_briefing()
    week = get_cpca_briefing_section(edition, "week")
    value = week["metrics"]["passenger_retail"]["value"]

注意：``week`` 段在非首周是相邻两期累计反推值，``estimated`` 为 ``True``；
首周和累计段是原文发布值。展示时不要抹掉这个区别。

本模块不做缓存；高频读取的服务应自行按文件 mtime 或
``standard_dataset_sha256`` 做一层缓存。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONTRACT = "mashang-data.cpca.briefing"
SCHEMA_MAJOR = "1"
ENV_VAR = "MASHANG_DATA_CPCA_BRIEFING"
DEFAULT_RELATIVE_PATH = Path("mashang-data/exports/cpca/briefing.v1.json")
SECTION_KEYS = ("week", "month_to_date", "year_to_date")
METRIC_KEYS = ("passenger_retail", "nev_retail")


class CpcaBriefingError(RuntimeError):
    """CPCA 简报出口读取失败。"""


class CpcaBriefingNotFound(CpcaBriefingError):
    """出口文件不存在。"""


class CpcaBriefingInvalid(CpcaBriefingError):
    """出口文件存在，但不符合 v1 契约。"""


def get_service_root() -> Path:
    """返回 mashang-service 仓库根目录。"""
    return Path(__file__).resolve().parents[2]


def get_default_briefing_path() -> Path:
    """返回默认的平级 mashang-data 出口路径。"""
    return get_service_root().parent / DEFAULT_RELATIVE_PATH


def get_briefing_path(path: str | Path | None = None) -> Path:
    """解析出口路径；参数优先于环境变量，再回退到默认平级路径。"""
    raw: str | Path | None = path
    if raw is None:
        raw = os.getenv(ENV_VAR)
    if raw is None or str(raw).strip() == "":
        raw = get_default_briefing_path()
    resolved = Path(raw).expanduser()
    if not resolved.is_absolute():
        resolved = get_service_root() / resolved
    return resolved.resolve()


def load_cpca_briefing(path: str | Path | None = None) -> dict[str, Any]:
    """读取并校验 CPCA 简报出口，返回完整契约对象。

    Raises:
        CpcaBriefingNotFound: 文件不存在。
        CpcaBriefingInvalid: JSON 无法解析，或 schema/contract 不兼容。
    """
    briefing_path = get_briefing_path(path)
    if not briefing_path.is_file():
        raise CpcaBriefingNotFound(
            f"CPCA 简报出口不存在: {briefing_path}\n"
            f"请在 mashang-data 根目录运行 make export-cpca-briefing，"
            f"或设置 {ENV_VAR} 指向导出文件。"
        )
    try:
        data = json.loads(briefing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CpcaBriefingInvalid(
            f"CPCA 简报出口无法读取: {briefing_path}: {exc}"
        ) from exc
    return _validate(data, briefing_path)


def _validate(data: object, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CpcaBriefingInvalid(f"{path}: 顶层必须是对象")

    version = data.get("schema_version")
    if not isinstance(version, str) or version.split(".", 1)[0] != SCHEMA_MAJOR:
        raise CpcaBriefingInvalid(
            f"{path}: 不支持的 schema_version={version!r}，期望主版本 {SCHEMA_MAJOR}"
        )
    if data.get("contract") != CONTRACT:
        raise CpcaBriefingInvalid(
            f"{path}: contract={data.get('contract')!r}，期望 {CONTRACT}"
        )

    editions = data.get("editions")
    if not isinstance(editions, list) or not editions:
        raise CpcaBriefingInvalid(f"{path}: editions 必须是非空数组")
    latest = data.get("latest_edition")
    if not isinstance(latest, str) or not latest:
        raise CpcaBriefingInvalid(f"{path}: latest_edition 必须是非空字符串")
    first = editions[0]
    if not isinstance(first, dict) or first.get("edition") != latest:
        raise CpcaBriefingInvalid(
            f"{path}: latest_edition={latest!r} 与 editions[0] 不一致"
        )
    if not isinstance(first.get("sections"), list):
        raise CpcaBriefingInvalid(f"{path}: editions[0].sections 必须是数组")
    return data


def latest_cpca_briefing(path: str | Path | None = None) -> dict[str, Any]:
    """返回最新一期（``editions[0]``）。"""
    data = load_cpca_briefing(path)
    return data["editions"][0]


def get_cpca_briefing_edition(
    edition: str,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    """按统计截止日查找一期；不存在时返回 ``None``。"""
    data = load_cpca_briefing(path)
    for item in data["editions"]:
        if isinstance(item, dict) and item.get("edition") == edition:
            return item
    return None


def get_cpca_briefing_section(
    edition: dict[str, Any],
    key: str,
) -> dict[str, Any] | None:
    """按稳定 key 查找一段（week / month_to_date / year_to_date）。"""
    sections = edition.get("sections")
    if not isinstance(sections, list):
        return None
    for section in sections:
        if isinstance(section, dict) and section.get("key") == key:
            return section
    return None


def get_cpca_briefing_metric(
    edition: dict[str, Any],
    section_key: str,
    metric_key: str,
) -> dict[str, Any] | None:
    """按 section key 和指标 key 查找指标对象。"""
    section = get_cpca_briefing_section(edition, section_key)
    if section is None:
        return None
    metrics = section.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get(metric_key)
    return metric if isinstance(metric, dict) else None
