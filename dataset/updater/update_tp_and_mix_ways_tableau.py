#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量更新 TP&MIX-ways 数据集（staging 全链路校验 → 跨层事务发布）。

安全契约：
1. Tableau 导出先落在 dataset/TP&MIX-ways/staging/runs/<run_id>/increment/，
   绝不直接写正式 raw_csv。
2. 正式 raw_csv 与增量在 staging 合并：增量包含的月份整月替换（消失的键计入
   removed_rows），未出现在增量中的历史月份保持原值；合并结果先校验列、主键、
   月份和数值。整月删除比例超过阈值默认阻断。
3. 派生层也从 staging merged raw 全量构建到 staging；raw、parquet、registry、
   quality 全部校验通过后才进入发布。
4. 发布是单次跨层事务：先快照全部目标文件到 staging/backups/<run_id>/，再逐文件
   os.replace；任一失败恢复本次事务已修改的全部文件。os.replace 只提供文件级
   原子性，不保证整个数据集的一致可见性；transaction manifest 是恢复依据。
5. 运行锁防止并发更新；启动时自动回滚上次中断留下的 publishing manifest。

用法:
    python dataset/updater/update_tp_and_mix_ways_tableau.py
    python dataset/updater/update_tp_and_mix_ways_tableau.py --mobile
    python dataset/updater/update_tp_and_mix_ways_tableau.py --timeout 300
    python dataset/updater/update_tp_and_mix_ways_tableau.py --dry-run
    python dataset/updater/update_tp_and_mix_ways_tableau.py --skip-export  # 仅从正式 raw 重建
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_tp_and_mix_ways_dataset import (  # noqa: E402
    build_tp_and_mix_ways_dataset,
)
from dataset.updater.tp_and_mix_ways_raw_guard import (  # noqa: E402
    DEFAULT_MAX_MONTH_DELETION_RATIO,
    RawContractError,
    merge_snapshot_to_staging,
    new_run_id,
    publish_update_transaction,
    recover_incomplete_transactions,
    update_lock,
    validate_derived_baseline,
    validate_raw_derived_consistency,
    validate_snapshot,
)

DATASET_ROOT = REPO_ROOT / "dataset" / "TP&MIX-ways"

TABLEAU_VIEWS: list[dict[str, str]] = [
    {"view_path": "-ways/market_monthly", "output": "way1_market_energy_monthly_data.csv"},
    {"view_path": "-ways/brand_monthly", "output": "way2_brand_monthly_data.csv"},
    {"view_path": "-ways/way3_model_monthly", "output": "way3_model_monthly_data.csv"},
    {"view_path": "-ways/way4_geo_monthly", "output": "way4_geo_monthly_data.csv"},
    {"view_path": "-ways/way5_price_segment_monthly", "output": "way5_price_segment_monthly_data.csv"},
    {"view_path": "-ways/way6_product_segment_monthly", "output": "way6_product_segment_monthly_data.csv"},
]


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        return


def _http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 60,
) -> tuple[int, bytes]:
    req = Request(url=url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urlopen(req, data=body, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            data = resp.read()
            return status, data
    except HTTPError as e:
        try:
            payload = e.read()
        except Exception:
            payload = str(e).encode("utf-8", errors="ignore")
        return int(getattr(e, "code", 0) or 0), payload
    except URLError as e:
        return 0, str(e).encode("utf-8", errors="ignore")


def _xml_find_first_attr(xml_bytes: bytes, tag_name: str, attr: str) -> str | None:
    root = ET.fromstring(xml_bytes)
    elem = root.find(f".//{{*}}{tag_name}")
    if elem is None:
        return None
    return elem.attrib.get(attr)


def _xml_escape_attr(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def tableau_sign_in(
    *,
    base_url: str,
    token_name: str,
    token_value: str,
    site_content_url: str,
    timeout: int,
) -> tuple[str, str, str]:
    base = base_url.rstrip("/")
    site_part = _xml_escape_attr(site_content_url or "")
    token_name_esc = _xml_escape_attr(token_name)
    token_value_esc = _xml_escape_attr(token_value)
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<tsRequest>"
        f'<credentials personalAccessTokenName="{token_name_esc}" personalAccessTokenSecret="{token_value_esc}">'
        f'<site contentUrl="{site_part}"/>'
        "</credentials>"
        "</tsRequest>"
    ).encode("utf-8")

    versions = ["3.25", "3.24", "3.23", "3.22", "3.21", "3.20", "3.19", "3.18", "3.17", "3.16", "3.15", "3.14"]
    for ver in versions:
        url = f"{base}/api/{ver}/auth/signin"
        status, data = _http_request(
            method="POST",
            url=url,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            body=payload,
            timeout=timeout,
        )
        if status in {200, 201}:
            token = _xml_find_first_attr(data, "credentials", "token")
            site_id = _xml_find_first_attr(data, "site", "id")
            if token and site_id:
                return ver, token, site_id
        if status == 404:
            continue
    msg = data.decode("utf-8", errors="ignore")
    raise RuntimeError(f"Tableau 登录失败 (HTTP {status}): {msg[:3000]}")


def tableau_sign_out(*, base_url: str, api_version: str, auth_token: str, timeout: int) -> None:
    base = base_url.rstrip("/")
    url = f"{base}/api/{api_version}/auth/signout"
    _http_request(method="POST", url=url, headers={"X-Tableau-Auth": auth_token}, body=b"", timeout=timeout)


def tableau_find_view_id(
    *,
    base_url: str,
    api_version: str,
    auth_token: str,
    site_id: str,
    workbook_url_name: str,
    view_url_name: str,
    timeout: int,
) -> str:
    base = base_url.rstrip("/")
    expected = f"{workbook_url_name}/{view_url_name}"

    def _match_view_id_from_xml(xml_bytes: bytes) -> str | None:
        root = ET.fromstring(xml_bytes)
        for v in root.findall(".//{*}view"):
            view_id = (v.attrib.get("id") or "").strip()
            if not view_id:
                continue
            content_url = (v.attrib.get("contentUrl") or "").strip().strip("/")
            view_url = (v.attrib.get("viewUrlName") or "").strip().strip("/")
            name = (v.attrib.get("name") or "").strip()
            if content_url == expected:
                return view_id
            if content_url == view_url_name:
                return view_id
            if content_url.endswith("/" + view_url_name) and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
            if view_url == view_url_name and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
            if name == view_url_name and content_url.split("/", 1)[0] == workbook_url_name:
                return view_id
        return None

    def _query_views(*, filter_expr: str) -> str | None:
        page_number = 1
        page_size = 1000
        while True:
            params = {"pageSize": str(page_size), "pageNumber": str(page_number), "filter": filter_expr}
            url = f"{base}/api/{api_version}/sites/{site_id}/views?{urlencode(params, quote_via=quote)}"
            status, data = _http_request(
                method="GET",
                url=url,
                headers={"X-Tableau-Auth": auth_token, "Accept": "application/xml"},
                timeout=timeout,
            )
            if status != 200:
                msg = data.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Tableau 查询视图失败 (HTTP {status}): {msg[:3000]}")
            vid = _match_view_id_from_xml(data)
            if vid:
                return vid
            root = ET.fromstring(data)
            pagination = root.find(".//{*}pagination")
            if pagination is None:
                break
            total = int(pagination.attrib.get("totalAvailable", "0") or "0")
            if page_number * page_size >= total or page_number >= 20:
                break
            page_number += 1
        return None

    for f in [f"contentUrl:eq:{expected}", f"viewUrlName:eq:{view_url_name}", f"name:eq:{view_url_name}"]:
        vid = _query_views(filter_expr=f)
        if vid:
            return vid

    raise RuntimeError(f"未找到视图: {expected}")


def tableau_download_view_data_csv(
    *,
    base_url: str,
    api_version: str,
    auth_token: str,
    site_id: str,
    view_id: str,
    output_path: Path,
    timeout: int,
) -> None:
    base = base_url.rstrip("/")
    candidates = [
        f"{base}/api/{api_version}/sites/{site_id}/views/{view_id}/data?maxAge=1",
        f"{base}/api/{api_version}/sites/{site_id}/views/{view_id}/crosstab?maxAge=1",
    ]
    last_status = 0
    last_data: bytes = b""
    for url in candidates:
        status, data = _http_request(
            method="GET",
            url=url,
            headers={"X-Tableau-Auth": auth_token, "Accept": "*/*"},
            timeout=timeout,
        )
        last_status, last_data = status, data
        if status == 200 and data:
            payload = data
            if payload[:4] == b"PK\x03\x04":
                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                    names = [n for n in zf.namelist() if not n.endswith("/") and n.strip()]
                    pick = None
                    for n in names:
                        low = n.lower()
                        if low.endswith(".csv") or low.endswith(".tsv") or low.endswith(".txt"):
                            pick = n
                            break
                    if pick is None and names:
                        pick = names[0]
                    if pick is None:
                        raise RuntimeError("Tableau 导出 zip 为空")
                    payload = zf.read(pick)
            tmp_path = output_path.with_name(output_path.name + ".tmp")
            tmp_path.write_bytes(payload)
            if tmp_path.stat().st_size == 0:
                raise RuntimeError("Tableau 导出结果为空文件")
            tmp_path.replace(output_path)
            return
        if status not in {406, 415}:
            break
    msg = (last_data or b"").decode("utf-8", errors="ignore")
    raise RuntimeError(f"Tableau 下载数据失败 (HTTP {last_status}): {msg[:3000]}")


def parse_tableau_view_path(view: str) -> tuple[str, str]:
    raw = (view or "").strip()
    if not raw:
        raise ValueError("empty view")
    s = raw
    if "#/views/" in s:
        s = s.split("#/views/", 1)[1]
    elif "/views/" in s:
        s = s.split("/views/", 1)[1]
    s = s.split("?", 1)[0].strip().strip("/")
    parts = [p for p in s.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"invalid view: {view}")
    return parts[0], parts[1]


# ---- CSV 解析（与 build 脚本一致） ----

def step_export_all_views(
    output_dir: Path, mobile: bool = False, timeout: int = 600
) -> bool:
    print("\n" + "=" * 60)
    print("从 Tableau 导出 TP&MIX-ways 6 个视图到 staging")
    print("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)

    token_name = os.getenv("TABLEAU_TOKEN_NAME")
    token_value = os.getenv("TABLEAU_TOKEN_VALUE")
    if not token_name or not token_value:
        print("❌ 缺少 Tableau PAT：TABLEAU_TOKEN_NAME / TABLEAU_TOKEN_VALUE")
        return False

    if mobile:
        base_url = os.getenv("TABLEAU_SERVER_URL_MOBILE") or "https://mobile-tableau-hs.immotors.com"
    else:
        base_url = os.getenv("TABLEAU_SERVER_URL") or "https://tableau-hs.immotors.com"
    site_content_url = os.getenv("TABLEAU_SITE_CONTENT_URL", "")

    view_defs = list(TABLEAU_VIEWS)
    for v in view_defs:
        try:
            wb, vn = parse_tableau_view_path(v["view_path"])
            v["workbook"] = wb
            v["view_name"] = vn
        except ValueError as e:
            print(f"❌ 解析视图路径失败 {v['view_path']}: {e}")
            return False

    try:
        api_version, auth_token, site_id = tableau_sign_in(
            base_url=base_url,
            token_name=token_name,
            token_value=token_value,
            site_content_url=site_content_url,
            timeout=timeout,
        )
    except Exception as e:
        print(f"❌ Tableau 登录失败: {e}")
        return False

    all_ok = True
    try:
        for v in view_defs:
            output_path = output_dir / v["output"]
            print(f"\n  [{v['output']}] 导出 {v['workbook']}/{v['view_name']} ...")
            try:
                view_id = tableau_find_view_id(
                    base_url=base_url,
                    api_version=api_version,
                    auth_token=auth_token,
                    site_id=site_id,
                    workbook_url_name=v["workbook"],
                    view_url_name=v["view_name"],
                    timeout=timeout,
                )
                tableau_download_view_data_csv(
                    base_url=base_url,
                    api_version=api_version,
                    auth_token=auth_token,
                    site_id=site_id,
                    view_id=view_id,
                    output_path=output_path,
                    timeout=timeout,
                )
                size_kb = output_path.stat().st_size / 1024
                print(f"  ✅ {v['output']} ({size_kb:.1f} KB)")
            except Exception as e:
                print(f"  ❌ {v['output']} 失败: {e}")
                all_ok = False
    finally:
        tableau_sign_out(base_url=base_url, api_version=api_version, auth_token=auth_token, timeout=timeout)

    if all_ok:
        print(f"\n✅ 全部导出成功 ({len(view_defs)}/6) → staging")
    else:
        print("\n⚠️ 部分导出失败，正式 raw_csv 未改动")
    return all_ok


def _rebuild_derived_layers(
    *,
    source_raw_dir: Path,
    run_dir: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    """Rebuild parquet/registry/quality from raw into a staging tree."""
    derived_dir = run_dir / "derived"
    print("\n" + "=" * 60)
    print("从 raw 全量重建 parquet / registry / quality（staging）")
    print("=" * 60)
    try:
        reports = build_tp_and_mix_ways_dataset(
            raw_csv_dir=source_raw_dir,
            parquet_dir=derived_dir / "parquet",
            registry_dir=derived_dir / "registry",
            quality_dir=derived_dir / "quality",
        )
    except SystemExit as exc:
        raise RuntimeError("raw 快照不完整，构建中止（未发布任何派生文件）") from exc

    errors = [r for r in reports if r.get("build_status") != "success"]
    if errors:
        raise RuntimeError(f"构建失败: {[r.get('table_name') for r in errors]}")
    for report in reports:
        print(
            f"  {report['table_name']}: rows={report.get('row_count')} "
            f"months={report.get('date_min')}..{report.get('date_max')} "
            f"duplicate_grain_count={report.get('duplicate_grain_count')}"
        )
    return derived_dir, reports


def _print_merge_audit(plan: dict[str, Any]) -> None:
    for table_name, stats in plan["tables"].items():
        print(
            f"  {table_name}: base={stats['base_rows']} inc={stats['increment_rows']} "
            f"merged={stats['merged_rows']} added={stats['added_rows']} "
            f"restated={stats['restated_rows']} removed={stats['removed_rows']} "
            f"months={stats['base_month_count']}->{stats['merged_month_count']}"
        )
        for item in stats.get("month_audit", []):
            if not item["removed_rows"]:
                continue
            print(
                f"    {item['month']}: old={item['base_rows']} "
                f"new={item['increment_rows']} removed={item['removed_rows']} "
                f"ratio={item['deletion_ratio']:.2%}"
            )


def run_update(
    *,
    dataset_root: Path,
    export: bool,
    mobile: bool,
    timeout: int,
    dry_run: bool,
    max_month_deletion_ratio: float = DEFAULT_MAX_MONTH_DELETION_RATIO,
) -> int:
    dataset_root = Path(dataset_root).resolve()
    raw_dir = dataset_root / "raw_csv"
    staging_root = dataset_root / "staging"
    run_id = new_run_id()
    run_dir = staging_root / "runs" / run_id

    try:
        with update_lock(staging_root, run_id):
            for recovered in recover_incomplete_transactions(staging_root):
                print(
                    f"♻️  已处理未完成事务: {recovered['manifest']} "
                    f"-> {recovered['status']}"
                )

            baseline = validate_derived_baseline(dataset_root)
            required_months = baseline.get("months") or {}

            staged_raw: Path | None = None
            raw_validation = None
            merge_audit = None

            if export:
                increment_dir = run_dir / "increment" / "raw_csv"
                if not step_export_all_views(increment_dir, mobile=mobile, timeout=timeout):
                    print("\n❌ Tableau 导出失败，正式数据未改动。")
                    return 1
                validate_snapshot(increment_dir)
                if not raw_dir.is_dir():
                    raise RawContractError(f"正式 raw 目录不存在: {raw_dir}")

                print("\n按整月替换语义合并增量与正式 raw（历史月份保护）...")
                plan = merge_snapshot_to_staging(
                    raw_dir,
                    increment_dir,
                    run_dir / "merged" / "raw_csv",
                    required_months_by_table=required_months,
                    max_month_deletion_ratio=max_month_deletion_ratio,
                )
                staged_raw = Path(plan["merged_dir"])
                raw_validation = plan["validation"]
                merge_audit = plan["tables"]
                _print_merge_audit(plan)
            else:
                if not raw_dir.is_dir():
                    raise RawContractError(f"正式 raw 目录不存在: {raw_dir}")
                print("\n跳过 Tableau 导出，直接从正式 raw 重建 staging 派生层。")

            # Build and validate every layer from the staged raw before touching
            # any formal file. A failure here leaves the formal dataset unchanged.
            source_raw = staged_raw if staged_raw is not None else raw_dir
            derived_dir, reports = _rebuild_derived_layers(
                source_raw_dir=source_raw, run_dir=run_dir
            )
            consistency = validate_raw_derived_consistency(source_raw, derived_dir)
            derived_validation = {
                report["table_name"]: {
                    "row_count": report.get("row_count"),
                    "date_min": report.get("date_min"),
                    "date_max": report.get("date_max"),
                    "duplicate_grain_count": report.get("duplicate_grain_count"),
                }
                for report in reports
            }

            if dry_run:
                print(
                    f"\n[dry-run] 导出/合并/校验/派生层构建全部通过，未发布。"
                    f"staged: {run_dir}"
                )
                return 0

            manifest = publish_update_transaction(
                dataset_root=dataset_root,
                run_dir=run_dir,
                staging_root=staging_root,
                raw_dir=staged_raw,
                derived_dir=derived_dir,
                validation={
                    "raw": raw_validation,
                    "derived": derived_validation,
                    "cross_layer": consistency,
                },
                audit={"merge": merge_audit},
            )
            print(
                f"\n✅ 跨层事务发布完成: layers={manifest.get('layers')} "
                f"files={len(manifest.get('files', {}))} "
                f"backup={staging_root / 'backups' / run_id}"
            )
            return 0
    except (RawContractError, OSError, RuntimeError) as exc:
        print(f"\n❌ 更新失败（正式数据未改动，或已按快照回滚）: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="增量更新 TP&MIX-ways 数据集（staging 校验 → 跨层事务发布）"
    )
    parser.add_argument("--mobile", action="store_true", help="使用移动端/非办公网络服务器地址导出")
    parser.add_argument("--timeout", type=int, default=600, help="Tableau 导出超时（秒）")
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="跳过 Tableau 导出，仅从正式 raw_csv 重建并发布派生层",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="完成导出/合并/全链路构建与校验到 staging，但不发布正式文件",
    )
    parser.add_argument(
        "--max-month-deletion-ratio",
        type=float,
        default=DEFAULT_MAX_MONTH_DELETION_RATIO,
        help=(
            "整月替换允许的最大删除行比例（默认 "
            f"{DEFAULT_MAX_MONTH_DELETION_RATIO:.2f}）；超过则阻断发布"
        ),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
        help="TP&MIX-ways 数据根目录（默认 dataset/TP&MIX-ways，测试可覆盖）",
    )
    args = parser.parse_args(argv)

    if not 0.0 <= args.max_month_deletion_ratio <= 1.0:
        parser.error("--max-month-deletion-ratio 必须在 [0, 1]")

    load_env_file(REPO_ROOT / ".env")
    try:
        return run_update(
            dataset_root=args.dataset_root,
            export=not args.skip_export,
            mobile=args.mobile,
            timeout=args.timeout,
            dry_run=args.dry_run,
            max_month_deletion_ratio=args.max_month_deletion_ratio,
        )
    except RawContractError as exc:
        print(f"\n❌ 数据契约校验失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
