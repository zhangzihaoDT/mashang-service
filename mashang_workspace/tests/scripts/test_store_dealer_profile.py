"""store_dealer_profile.py smoke test — 门店 → 经销商主体画像。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[3]
_WS_DIR = _PRJ / "mashang_workspace"
SCRIPT = _WS_DIR / "runtime_scripts" / "store_dealer_profile.py"

sys.path.insert(0, str(_PRJ))
from shared.loaders import store_info_loader as sl  # noqa: E402

COLUMNS = ["门店", "经销商主体 (Bloc)", "大区", "该主体门店数(在营)", "城市分布"]


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


def test_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "--store" in r.stdout and "--status" in r.stdout


def test_no_store_returns_error():
    r = _run()
    assert r.returncode == 2


@pytest.mark.skipif(sl.get_store_info_csv_path() is None, reason="本机 external store_info.csv 不存在")
def test_json_smoke():
    r = _run("遵义吾悦广场城市展厅", "重庆万州万达城市展厅", "--format", "json")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    assert data["status"] == "success"
    table = data["result"]["tables"][0]
    assert table["columns"] == COLUMNS
    rows = {row["门店"]: row for row in table["rows"]}
    assert rows["遵义吾悦广场城市展厅"]["经销商主体 (Bloc)"] == "成都新双立"
    assert rows["重庆万州万达城市展厅"]["经销商主体 (Bloc)"] == "重庆昕悦欣"
    for row in rows.values():
        assert row["该主体门店数(在营)"] >= 1
        assert row["城市分布"]


@pytest.mark.skipif(sl.get_store_info_csv_path() is None, reason="本机 external store_info.csv 不存在")
def test_unmatched_store():
    r = _run("__不存在的门店__", "--format", "json")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    row = data["result"]["tables"][0]["rows"][0]
    assert row["经销商主体 (Bloc)"] == "未匹配"
    assert row["该主体门店数(在营)"] is None


ZHULI_ROSTER = _PRJ / "dataset" / "主理信息表.csv"


@pytest.mark.skipif(not ZHULI_ROSTER.exists(), reason="dataset/主理信息表.csv 不存在（需先运行 updater）")
def test_zhuli_section_fallback():
    r = _run("遵义吾悦广场城市展厅", "重庆万州万达城市展厅", "--format", "json")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    table = data["result"]["tables"][1]
    assert table["columns"] == ["门店", "近期主理数量", "主理归属说明"]
    rows = {row["门店"]: row for row in table["rows"]}
    fallback = rows["遵义吾悦广场城市展厅"]
    assert fallback["近期主理数量"] == "无独立主理"
    assert "遵义播州" in fallback["主理归属说明"]
    fallback2 = rows["重庆万州万达城市展厅"]
    assert fallback2["近期主理数量"] == "无独立主理"
    assert "重庆万州车城" in fallback2["主理归属说明"]


ORDER_PARQUET = _PRJ / "dataset" / "order_data.parquet"
LEADS_CSV = _PRJ / "dataset" / "门店下发线索数.csv"


@pytest.mark.skipif(not ORDER_PARQUET.exists(), reason="dataset/order_data.parquet 不存在")
def test_lock_and_presale_sections():
    r = _run("遵义吾悦广场城市展厅", "重庆万州万达城市展厅", "--format", "json",
             "--as-of", "2026-09-16")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    names = [t["name"] for t in data["result"]["tables"]]
    assert names == ["store_dealer_profile", "store_zhuli_profile", "store_leads_profile",
                     "store_lock_profile", "store_presale_profile"]
    lock = {row["门店"]: row for row in data["result"]["tables"][3]["rows"]}
    assert lock["遵义吾悦广场城市展厅"]["该主体近7日锁单"] >= 0
    assert str(lock["遵义吾悦广场城市展厅"]["锁单主体内排名"]).startswith("第")
    assert "车系分布" in lock["遵义吾悦广场城市展厅"]
    presale = {row["门店"]: row for row in data["result"]["tables"][4]["rows"]}
    assert presale["重庆万州万达城市展厅"]["该主体CM3留存小订"] >= 0
    assert "统计门店" in presale["重庆万州万达城市展厅"]
    assert "小订/线索" in presale["重庆万州万达城市展厅"]


@pytest.mark.skipif(not (ORDER_PARQUET.exists() and LEADS_CSV.exists()),
                    reason="order_data / 门店下发线索数 不存在")
def test_leads_section_fallback():
    r = _run("遵义吾悦广场城市展厅", "--format", "json", "--as-of", "2026-09-16")
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(r.stdout)
    leads = data["result"]["tables"][2]
    assert leads["columns"] == ["门店", "近7日下发线索", "该主体近7日下发线索", "线索主体内排名", "线索主体内占比"]
    row = leads["rows"][0]
    assert row["近7日下发线索"] is not None and row["近7日下发线索"] >= 0
    assert str(row["线索主体内排名"]).startswith("第")
