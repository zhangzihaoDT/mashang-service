"""MIIT 模块 CLI 冒烟测试：验证所有旧入口可用（--help 可执行）。"""
import subprocess
import sys
from pathlib import Path

MIIT = Path(__file__).resolve().parents[2]

ENTRY_POINTS = [
    "scripts/miit_gov_search.py",
    "scripts/01_scan_batch.py",
    "scripts/02_archive_vehicle_details.py",
    "scripts/03_parse_vehicle_tax.py",
    "scripts/04_build_wide_table.py",
    "scripts/05_generate_brand_report.py",
    "scripts/06_generate_category_report.py",
    "scripts/07_build_vehicle_dataset.py",
    "scripts/09_fetch_eidc_batch.py",
    "scripts/10_parse_purchase_tax.py",
    "scripts/eidc_doc_extract.py",
    "scripts/eidc_summary_fresh.py",
]


def test_all_cli_help():
    for ep in ENTRY_POINTS:
        r = subprocess.run(
            [sys.executable, str(MIIT / ep), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"{ep} --help failed:\n{r.stderr}"


def test_vehicle_type_classification():
    """两层分类规则确定性测试（分类不参与 identity，但映射必须稳定）。"""
    import sys as _sys
    _sys.path.insert(0, str(MIIT / "scripts"))
    from vehicle_record_builder import classify_vehicle_type  # noqa: E402

    cases = {
        "轿车": ("passenger_vehicle", "sedan"),
        "多用途乘用车": ("passenger_vehicle", "suv_mpv"),
        "纯电动轿车": ("passenger_vehicle", "sedan"),
        "插电式混合动力多用途乘用车": ("passenger_vehicle", "suv_mpv"),
        "城市客车": ("commercial_vehicle", "bus"),
        "中小学生专用校车": ("commercial_vehicle", "bus"),
        "牵引汽车": ("commercial_vehicle", "tractor"),
        "压缩式垃圾车": ("commercial_vehicle", "sanitation_fire"),
        "泡沫消防车": ("commercial_vehicle", "sanitation_fire"),
        "厢式货车": ("commercial_vehicle", "truck"),
        "载货汽车底盘": ("commercial_vehicle", "truck"),
        "高空作业车": ("commercial_vehicle", "special_vehicle"),
        "电动正三轮摩托车": ("motorcycle", "motorcycle"),
        "电动两轮轻便摩托车": ("motorcycle", "motorcycle"),
        "半挂车": ("trailer", "trailer"),
        "运输类中置轴挂车": ("trailer", "trailer"),
        "": ("other", "other"),
    }
    for src, expected in cases.items():
        got = classify_vehicle_type(src)
        assert got == expected, f"{src!r}: expected {expected}, got {got}"


def test_vehicle_type_classification_official_signal():
    """官方目录序号信号兜底（（X）数字 = 专用车企业）。产品名无强规则时归入 special_vehicle。"""
    import sys as _sys
    _sys.path.insert(0, str(MIIT / "scripts"))
    from vehicle_record_builder import classify_vehicle_type  # noqa: E402

    # 产品名明确 → 产品名优先（即便目录序号带地区前缀）
    assert classify_vehicle_type("电动两轮摩托车", "(一)03") == ("motorcycle", "motorcycle")
    assert classify_vehicle_type("半挂车", "(十五)125") == ("trailer", "trailer")
    assert classify_vehicle_type("纯电动轿车", "(一)03") == ("passenger_vehicle", "sedan")
    # 产品名无强规则 + （X）数字 → 官方信号归入 special_vehicle
    assert classify_vehicle_type("生僻专用车", "(一)03") == ("commercial_vehicle", "special_vehicle")
    assert classify_vehicle_type("生僻专用车", "(十五)125") == ("commercial_vehicle", "special_vehicle")
    # 无官方信号 → other
    assert classify_vehicle_type("生僻专用车", "") == ("other", "other")


def test_canonical_scope_gate():
    """canonical scope gate：仅 passenger_vehicle 进入 canonical。"""
    import sys as _sys
    _sys.path.insert(0, str(MIIT / "scripts"))
    from vehicle_record_builder import is_canonical_in_scope, CANONICAL_VEHICLE_CATEGORY  # noqa: E402

    assert CANONICAL_VEHICLE_CATEGORY == "passenger_vehicle"
    assert is_canonical_in_scope({"vehicle_category": "passenger_vehicle"}) is True
    assert is_canonical_in_scope({"vehicle_category": "commercial_vehicle"}) is False
    assert is_canonical_in_scope({"vehicle_category": "motorcycle"}) is False
    assert is_canonical_in_scope({"vehicle_category": "trailer"}) is False
    assert is_canonical_in_scope({"vehicle_category": "other"}) is False
    assert is_canonical_in_scope({}) is False


def test_408_canonical_all_passenger():
    """408 regression：canonical 中 408 eidc 全部为 passenger，非乘用车 0。"""
    import csv as _csv
    import sys as _sys
    _sys.path.insert(0, str(MIIT / "scripts"))
    from miit_paths import VEHICLE_PARAMETERS_DIR  # noqa: E402

    with open(VEHICLE_PARAMETERS_DIR / "product_master.csv", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    p408 = [r for r in rows if r.get("batch_no") == "408"]
    assert p408, "408 canonical 应为空？"
    assert all(r.get("vehicle_category") == "passenger_vehicle" for r in p408), \
        "408 canonical 中存在非 passenger 记录"
    assert all(r.get("analysis_scope") == "in_scope" for r in p408)


def test_canonical_no_non_passenger():
    """canonical 全表不应存在非 passenger_vehicle 记录。"""
    import csv as _csv
    import sys as _sys
    _sys.path.insert(0, str(MIIT / "scripts"))
    from miit_paths import VEHICLE_PARAMETERS_DIR  # noqa: E402

    with open(VEHICLE_PARAMETERS_DIR / "product_master.csv", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    assert rows, "canonical 为空"
    non_passenger = [r for r in rows if r.get("vehicle_category") != "passenger_vehicle"]
    assert not non_passenger, f"canonical 存在非乘用车 {len(non_passenger)} 条"
