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
    """已有 ASCII 品牌名透传。"""
    assert output_paths.brand_to_slug("zhiji") == "zhiji"
    assert output_paths.brand_to_slug("im") == "im"
    assert output_paths.brand_to_slug("zeekr") == "zeekr"


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


def test_run_mode_owned_brand_daily_no_chinese():
    """owned_brand_daily run_mode 不含中文。"""
    mode = output_paths.run_mode_owned_brand_daily("智己")
    assert mode == "owned_brand_daily_zhiji"
    assert all(ord(c) < 128 for c in mode)


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
