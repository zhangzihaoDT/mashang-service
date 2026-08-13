"""EIDC pipeline 回归测试 — 通用批次验收（替代 batch-specific benchmark）。

从 eidc_benchmark_407/408 抽取的稳定验收断言：
  1. product_list.json 是 fresh 数组 contract（含 source_section）
  2. model_code valid rate
  3. canonical observation_id 唯一 + 全部 passenger
  4. tax/purchase attachment 已解析
  5. passenger 参数 coverage（NEV 命中后 battery/range 应有值）
  6. 07 rebuild 幂等
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

MIIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MIIT / "scripts"))

from miit_paths import EIDC_DIR, VEHICLE_PARAMETERS_DIR, VEHICLE_TAX_DIR  # noqa: E402
from eidc_parser import parse_road_products  # noqa: E402
from vehicle_record_builder import classify_source_record  # noqa: E402

RE_MODEL = re.compile(r'^[A-Z]{2,4}\d{2,}[A-Z0-9]{0,6}$')

BATCHES = [f"{i:03d}" for i in range(401, 409)]


def _road_text(batch: str):
    bdir = EIDC_DIR / f"batch_{batch}"
    manifest = json.loads((bdir / "import_manifest.json").read_text())
    for att in manifest.get("attachments", []):
        if "道路机动车辆" in att.get("title", ""):
            txt = bdir / "attachment_text_src" / att["filename"].replace(".doc", ".txt")
            if txt.exists():
                return txt, manifest
    return None, manifest


def _canonical_rows():
    with open(VEHICLE_PARAMETERS_DIR / "product_master.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_product_list_is_fresh_contract():
    """所有批次 product_list 是 fresh 数组 contract（含 source_section），非 legacy dict。"""
    for batch in BATCHES:
        pl = json.loads((EIDC_DIR / f"batch_{batch}" / "product_list.json").read_text())
        assert isinstance(pl, list), f"{batch}: product_list 非数组（legacy dict 残留？）"
        assert pl, f"{batch}: product_list 为空"
        assert "source_section" in pl[0], f"{batch}: 缺 source_section（非 fresh contract）"


def test_model_code_valid_rate():
    """每批 model_code valid rate > 95%。"""
    for batch in BATCHES:
        road_txt, _ = _road_text(batch)
        assert road_txt, f"{batch}: road txt 缺失"
        recs = parse_road_products(road_txt.read_text(), batch)
        valid = sum(1 for r in recs if RE_MODEL.match(r["model_code_raw"]))
        rate = valid / len(recs) * 100 if recs else 0
        assert rate > 95, f"{batch}: valid_rate={rate:.1f}% < 95%"


def test_canonical_identity_unique_and_passenger():
    """canonical 每批 observation_id 唯一 + 全部 passenger_vehicle。"""
    rows = _canonical_rows()
    for batch in BATCHES:
        batch_rows = [r for r in rows if r.get("batch_no") == batch]
        assert batch_rows, f"{batch}: canonical 无该批记录"
        obs = [r["observation_id"] for r in batch_rows]
        assert len(set(obs)) == len(obs), f"{batch}: observation_id 重复"
        assert all(r["vehicle_category"] == "passenger_vehicle" for r in batch_rows), \
            f"{batch}: 存在非 passenger 记录"


def test_canonical_no_non_passenger():
    """canonical 全表无非 passenger。"""
    rows = _canonical_rows()
    non_passenger = [r for r in rows if r.get("vehicle_category") != "passenger_vehicle"]
    assert not non_passenger, f"canonical 存在非乘用车 {len(non_passenger)} 条"


def test_passenger_param_coverage():
    """NEV passenger 命中目录后参数覆盖 sanity：至少存在有 battery/range 的记录。

    join hit（vehicle_tax/purchase_tax_match_flag）与字段 coverage 独立——
    目录命中但该车型无容量/续航字段是正常口径，故不断言"所有命中都有值"。
    本测试读 vehicle_parameter.csv（含参数列），非 product_master。
    """
    with open(VEHICLE_PARAMETERS_DIR / "vehicle_parameter.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total_nev = 0
    total_with_param = 0
    for batch in BATCHES:
        batch_rows = [r for r in rows if r.get("batch_no") == batch]
        nev = [r for r in batch_rows
               if r.get("vehicle_tax_match_flag") == "1" or r.get("purchase_tax_match_flag") == "1"]
        if nev:
            bc = sum(1 for r in nev if r.get("battery_capacity_kwh"))
            rg = sum(1 for r in nev if r.get("ev_range_km"))
            total_nev += len(nev)
            total_with_param += max(bc, rg)
    # 全 401-408 至少存在参数覆盖的 NEV 记录（sanity，不是全量要求）
    assert total_nev > 0, "401-408 无任何 NEV join 命中记录"
    assert total_with_param > 0, "401-408 NEV passenger 全部无 battery/range 参数"


def test_07_rebuild_idempotent():
    """07 重建后 product_master byte-identical。"""
    pm_path = VEHICLE_PARAMETERS_DIR / "product_master.csv"
    before = pm_path.read_text(encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(MIIT / "scripts" / "06_build_vehicle_dataset.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"07 rebuild failed:\n{r.stderr[:300]}"
    after = pm_path.read_text(encoding="utf-8")
    assert before == after, "product_master byte 不一致（非幂等）"


def test_tax_purchase_parsed():
    """每批 manifest 声明的 tax/purchase 附件已解析为 JSON。"""
    for batch in BATCHES:
        bdir = EIDC_DIR / f"batch_{batch}"
        manifest = json.loads((bdir / "import_manifest.json").read_text())
        for key, suffix in (("vehicle_tax_batch", "车船税"), ("purchase_tax_batch", "购置税")):
            batches = manifest.get(key, "").replace("，", ",").split(",")
            for nb in [x for x in batches if x.strip()]:
                path = VEHICLE_TAX_DIR / f"车型清单_第{nb}批{suffix}.json"
                assert path.exists(), f"{batch}: {key}={nb} 未解析（{path.name} 缺失）"
