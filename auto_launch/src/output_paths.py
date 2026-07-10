"""统一输出路径管理 — auto_launch 所有输出路径的唯一来源。

所有会写入 outputs/ 的脚本必须通过此模块获取路径，不得硬编码。

顶层白名单（长期生产目录）:
  runs/          — 唯一业务交付入口
  facts/         — 长期事实资产
  search_cache/  — 性能缓存
  demo/          — 非生产演示
  _legacy/       — 历史归档

不再允许的顶层目录:
  briefs/  owned_brand_daily/  search/  _migration/
"""

import re
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_ROOT = _SERVICE_ROOT / "outputs"

# ── Brand slug map ────────────────────────────────────────────
# 所有中文品牌名 → ASCII slug 映射。新增品牌务必在此添加。
# run_mode 只允许 [a-z0-9_]，不允许中文、空格、路径敏感字符。

BRAND_SLUG_MAP = {
    "智己": "zhiji",
    "极氪": "zeekr",
    "蔚来": "nio",
    "理想": "li_auto",
    "小米": "xiaomi",
    "小鹏": "xpeng",
    "比亚迪": "byd",
    "特斯拉": "tesla",
    "阿维塔": "avatr",
    "零跑": "leapmotor",
    "腾势": "denza",
    "方程豹": "fangchengbao",
    "问界": "aito",
    "智界": "luxeed",
    "享界": "stelato",
    "尊界": "zunjie",
    "尚界": "shangjie",
    "鸿蒙智行": "hima",
    "乐道": "ledao",
    "萤火虫": "firefly",
    "深蓝": "deepal",
    "岚图": "voyah",
    "领克": "lynkco",
    "埃安": "aion",
    "极氪科技": "zeekr",
    "蔚来汽车": "nio",
    "小鹏汽车": "xpeng",
    "上汽": "saic",
    # Internal brand keys (used by CLI --brand / run_mode)
    "im": "zhiji",
    "zeekr": "zeekr",
    "nio": "nio",
}


def brand_to_slug(name: str) -> str:
    """将品牌名转为 ASCII slug。

    - 匹配 BRAND_SLUG_MAP 优先。
    - 不匹配时降级为 sanitized_ascii：只保留 [a-zA-Z0-9]，小写化。
    - 不会返回中文、空格、斜杠等路径敏感字符。
    """
    name = name.strip()
    if name in BRAND_SLUG_MAP:
        return BRAND_SLUG_MAP[name]
    slug = re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()
    return slug if slug else "unknown"


def resolve_brand(brand_input: str) -> tuple[str, str]:
    """将品牌标识符解析为 (slug, display_name)。

    接受以下输入:
      - 中文名: "智己", "极氪"
      - ASCII slug: "zhiji", "zeekr"
      - 内部 key: "im", "zeekr"

    返回 (slug, 显示名)，显示名优先使用中文。
    """
    # Build reverse slug → display_name map (prefer shortest Chinese name)
    _display_by_slug: dict[str, str] = {}
    for name, slug in BRAND_SLUG_MAP.items():
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in name)
        if slug not in _display_by_slug:
            _display_by_slug[slug] = name
        elif is_chinese and len(name) < len(_display_by_slug.get(slug, '')):
            # Shorter Chinese name wins (e.g. "极氪" over "极氪科技")
            _display_by_slug[slug] = name

    # 1. Direct key lookup
    if brand_input in BRAND_SLUG_MAP:
        slug = BRAND_SLUG_MAP[brand_input]
        return slug, _display_by_slug.get(slug, slug)

    # 2. Convert to slug, then check reverse map
    slug = brand_to_slug(brand_input)
    if slug in _display_by_slug:
        return slug, _display_by_slug[slug]

    # 3. Fallback: slug is the identifier itself
    return slug, brand_input


def validate_run_mode(run_mode: str) -> str:
    """验证 run_mode 只含 [a-z0-9_]，否则 sanitize。"""
    cleaned = re.sub(r"[^a-z0-9_]", "_", run_mode.lower()).strip("_")
    if not cleaned:
        cleaned = "unknown"
    return cleaned


# ── 顶层目录 ──────────────────────────────────────────────

def output_root() -> Path:
    return _OUTPUT_ROOT


def facts_dir() -> Path:
    return _OUTPUT_ROOT / "facts"


def fact_db_path() -> Path:
    return _OUTPUT_ROOT / "facts" / "auto_launch_facts.sqlite"


def cache_dir() -> Path:
    p = _OUTPUT_ROOT / "search_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def demo_dir() -> Path:
    p = _OUTPUT_ROOT / "demo"
    p.mkdir(parents=True, exist_ok=True)
    return p


def legacy_dir() -> Path:
    p = _OUTPUT_ROOT / "_legacy"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Runs 层 ────────────────────────────────────────────────

def runs_dir() -> Path:
    return _OUTPUT_ROOT / "runs"


def _date_fmt(date_str: str) -> str:
    return date_str.replace("-", "")


def run_dir(date_str: str, run_mode: str) -> Path:
    run_mode = validate_run_mode(run_mode)
    d = _OUTPUT_ROOT / "runs" / _date_fmt(date_str) / run_mode
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_manifest_path(date_str: str, run_mode: str) -> Path:
    return run_dir(date_str, run_mode) / "manifest.json"


def run_summary_path(date_str: str, run_mode: str) -> Path:
    return run_dir(date_str, run_mode) / "summary.md"


# ── Search 子目录 ──────────────────────────────────────────

def search_dir(date_str: str, run_mode: str) -> Path:
    d = run_dir(date_str, run_mode) / "search"
    d.mkdir(parents=True, exist_ok=True)
    return d


def search_plan_path(date_str: str, run_mode: str) -> Path:
    return search_dir(date_str, run_mode) / "plan.json"


def search_raw_path(date_str: str, run_mode: str) -> Path:
    return search_dir(date_str, run_mode) / "raw.json"


def search_normalized_path(date_str: str, run_mode: str) -> Path:
    return search_dir(date_str, run_mode) / "normalized.json"


def search_audit_path(date_str: str, run_mode: str) -> Path:
    return search_dir(date_str, run_mode) / "audit.json"


# ── Facts 子目录 ───────────────────────────────────────────

def run_facts_dir(date_str: str, run_mode: str) -> Path:
    d = run_dir(date_str, run_mode) / "facts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def facts_delta_path(date_str: str, run_mode: str) -> Path:
    return run_facts_dir(date_str, run_mode) / "facts_delta.json"


def facts_audit_path(date_str: str, run_mode: str) -> Path:
    return run_facts_dir(date_str, run_mode) / "facts_audit.json"


# ── Reports 子目录 ─────────────────────────────────────────

def reports_dir(date_str: str, run_mode: str) -> Path:
    d = run_dir(date_str, run_mode) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def daily_brief_md_path(date_str: str, run_mode: str) -> Path:
    return reports_dir(date_str, run_mode) / "daily_brief.md"


def daily_brief_html_path(date_str: str, run_mode: str) -> Path:
    return reports_dir(date_str, run_mode) / "daily_brief.html"


def source_audit_md_path(date_str: str, run_mode: str) -> Path:
    return reports_dir(date_str, run_mode) / "source_audit.md"


def source_audit_json_path(date_str: str, run_mode: str) -> Path:
    return reports_dir(date_str, run_mode) / "source_audit.json"


# ── Run Mode 构建函数 ───────────────────────────────────────
# 所有 run_mode 通过 brand_to_slug 确保只含 ASCII 小写字母、数字、下划线。

def run_mode_brand_daily(brand: str) -> str:
    return f"brand_daily_{brand_to_slug(brand)}"


# backward compat
def run_mode_owned_brand_daily(brand: str) -> str:
    return run_mode_brand_daily(brand)


def run_mode_brand_watch(brand_label: str) -> str:
    return f"brand_watch_{brand_to_slug(brand_label)}"


def run_mode_model_watch(model_label: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]", "_", model_label).strip("_").lower()
    return f"model_watch_{slug}" if slug else "model_watch"


def run_mode_demo() -> str:
    return "demo"


# ── Legacy paths (should not be used for writes) ───────────

LEGACY_SEARCH_ROOT = _OUTPUT_ROOT / "search"
LEGACY_BRIEFS_DIR = _OUTPUT_ROOT / "briefs"
LEGACY_OWNED_BRAND_DAILY = _OUTPUT_ROOT / "owned_brand_daily"

LEGACY_DIRS = [
    LEGACY_SEARCH_ROOT,
    LEGACY_BRIEFS_DIR,
    LEGACY_OWNED_BRAND_DAILY,
]
