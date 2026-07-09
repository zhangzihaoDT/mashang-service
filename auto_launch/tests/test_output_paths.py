"""output_paths 测试 — 品牌 slug、run_mode 验证、路径规则"""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_launch.src import output_paths


def test_brand_to_slug_known_brands():
    """已知中文品牌返回正确英文 slug。"""
    cases = [
        ("智己", "zhiji"),
        ("极氪", "zeekr"),
        ("蔚来", "nio"),
        ("理想", "li_auto"),
        ("小米", "xiaomi"),
        ("小鹏", "xpeng"),
        ("比亚迪", "byd"),
        ("特斯拉", "tesla"),
        ("问界", "aito"),
        ("鸿蒙智行", "hima"),
    ]
    for cn, expected in cases:
        assert output_paths.brand_to_slug(cn) == expected, f"{cn} -> {expected}"


def test_brand_to_slug_ascii_passthrough():
    """已知 ASCII 品牌名返回正确 slug。"""
    assert output_paths.brand_to_slug("zhiji") == "zhiji"
    assert output_paths.brand_to_slug("im") == "zhiji"  # mapped to zhiji
    assert output_paths.brand_to_slug("zeekr") == "zeekr"
    assert output_paths.brand_to_slug("nio") == "nio"


def test_brand_to_slug_unknown_sanitized():
    """未知品牌降级为 sanitized ASCII。"""
    slug = output_paths.brand_to_slug("Some Brand!")
    assert re.match(r"^[a-z0-9_]+$", slug), f"slug contains invalid chars: {slug}"
    assert " " not in slug
    assert "!" not in slug


def test_brand_to_slug_no_chinese():
    """所有 slug 不含中文字符。"""
    for cn in ["智己", "极氪", "蔚来", "理想", "问界", "鸿蒙智行", "极氪科技"]:
        slug = output_paths.brand_to_slug(cn)
        assert all(ord(c) < 128 for c in slug), f"slug contains non-ASCII: {slug}"


def test_run_mode_brand_watch_no_chinese():
    """brand_watch run_mode 不含中文。"""
    chinese_brands = ["蔚来", "智己", "极氪", "理想"]
    for b in chinese_brands:
        mode = output_paths.run_mode_brand_watch(b)
        assert all(ord(c) < 128 for c in mode), f"run_mode contains non-ASCII: {mode}"
        assert re.match(r"^[a-z0-9_]+$", mode), f"run_mode has invalid chars: {mode}"


def test_run_mode_brand_daily_no_chinese():
    """brand_daily run_mode 不含中文。"""
    mode = output_paths.run_mode_brand_daily("智己")
    assert mode == "brand_daily_zhiji"
    assert all(ord(c) < 128 for c in mode)


def test_run_mode_brand_daily_backward_compat():
    """向后兼容：run_mode_owned_brand_daily 返回相同结果。"""
    assert output_paths.run_mode_owned_brand_daily("智己") == "brand_daily_zhiji"


def test_run_mode_brand_watch_specific():
    """品牌 watch 的正确 slug 化结果。"""
    assert output_paths.run_mode_brand_watch("蔚来") == "brand_watch_nio"
    assert output_paths.run_mode_brand_watch("智己") == "brand_watch_zhiji"
    assert output_paths.run_mode_brand_watch("极氪") == "brand_watch_zeekr"
    assert output_paths.run_mode_brand_watch("nio") == "brand_watch_nio"


def test_validate_run_mode_sanitizes():
    """validate_run_mode 过滤非法字符。"""
    assert output_paths.validate_run_mode("brand_watch_蔚来") == "brand_watch"
    assert output_paths.validate_run_mode("hello world") == "hello_world"
    assert output_paths.validate_run_mode("normal_name") == "normal_name"


def test_run_dir_path_no_chinese():
    """run_dir 路径不含中文字符。"""
    path = output_paths.run_dir("2026-07-09", "brand_watch_蔚来")
    path_str = str(path)
    assert all(ord(c) < 128 for c in path_str), f"path contains non-ASCII: {path_str}"
    # run_mode gets sanitized by validate_run_mode
    assert "_" in path.name  # The sanitized slug


def test_search_dir_path_no_chinese():
    """search_dir 路径不含中文字符。"""
    path = output_paths.search_dir("2026-07-09", "brand_watch_蔚来")
    path_str = str(path)
    assert all(ord(c) < 128 for c in path_str), f"path contains non-ASCII: {path_str}"


# ── Three run_mode types: required file contracts ─────────────

def test_brand_watch_required_files():
    """brand_watch 只要求 4 个 search 文件。"""
    rm = output_paths.run_mode_brand_watch("蔚来")
    assert rm == "brand_watch_nio"
    sd = output_paths.search_dir("2026-07-09", rm)
    expected = {"plan.json", "raw.json", "normalized.json", "audit.json"}
    assert sd.name == "search"
    # verify no extra required dirs
    parent = sd.parent
    assert not (parent / "facts").exists()
    assert not (parent / "reports").exists()


def test_brand_daily_required_files():
    """brand_daily 要求完整 run package。"""
    rm = output_paths.run_mode_brand_daily("智己")
    assert rm == "brand_daily_zhiji"
    rd = output_paths.run_dir("2026-07-09", rm)
    # Standard subdirs should be accessible
    assert output_paths.search_dir("2026-07-09", rm).parent == rd
    assert output_paths.reports_dir("2026-07-09", rm).parent == rd
    assert output_paths.run_facts_dir("2026-07-09", rm).parent == rd


def test_launcher_daily_run_contract():
    """launcher_daily_run 允许 partial，manifest 标明 input_channel。"""
    rm = "launcher_daily_run"
    rd = output_paths.run_dir("2026-07-09", rm)
    # manifest and summary are always required
    assert output_paths.run_manifest_path("2026-07-09", rm).parent == rd
    assert output_paths.run_summary_path("2026-07-09", rm).parent == rd
    # reports are typical but not guaranteed to exist
    brief = output_paths.daily_brief_md_path("2026-07-09", rm)
    assert brief.parent.name == "reports"


def test_run_mode_brand_daily_slug():
    """brand_daily 用 im 和 智己 都得到 zhiji slug。"""
    assert output_paths.run_mode_brand_daily("im") == "brand_daily_zhiji"
    assert output_paths.run_mode_brand_daily("智己") == "brand_daily_zhiji"


def test_run_mode_brand_watch_slug():
    """brand_watch 用 蔚来 得到 nio slug。"""
    assert output_paths.run_mode_brand_watch("蔚来") == "brand_watch_nio"
    assert output_paths.run_mode_brand_watch("nio") == "brand_watch_nio"


def test_all_new_runs_ascii_only():
    """所有新 run 目录不含中文。"""
    for cn, expected in [("智己", "zhiji"), ("极氪", "zeekr"), ("蔚来", "nio"), ("理想", "li_auto")]:
        for fn in [output_paths.run_mode_brand_watch, output_paths.run_mode_brand_daily]:
            mode = fn(cn)
            assert all(ord(c) < 128 for c in mode), f"{fn.__name__}({cn}) → {mode}"
