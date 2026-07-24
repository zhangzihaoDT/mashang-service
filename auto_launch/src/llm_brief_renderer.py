"""Layer: LLM — 基于 LLM 的简报生成（质量优于规则脚本）"""

import json, os, re
from datetime import datetime
from typing import Optional

import httpx

_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
_DEFAULT_MODEL = "deepseek-chat"

_DAILY_BRIEF_PROMPT = """你是一个新能源汽车行业分析师。根据 facts 中的营销事件事实，生成一份三段式每日简报。

必须严格按照以下格式输出，不要使用代码块：

🚗 重点新能源品牌每日营销事件监控
{date_with_weekday}

📊 今日概况
事件 {event_count}｜品牌 {brand_count}｜官方 {official_pct}%

🔥 今日重点
① **品牌 / 车型 / 类型**：核心动作描述（来源名称）
② **品牌 / 车型 / 类型**：核心动作描述（来源名称）
③ **品牌 / 车型 / 类型**：核心动作描述（来源名称）
④ **品牌 / 车型 / 类型**：核心动作描述（来源名称）

写作要求：
- 今日重点按重要程度排列，最多 4 条
- 事件类型用两个字简称：配置发布→发布, 技术传播→OTA, OTA更新→OTA, 开启预售→预售, 权益调整→权益, 交付启动→交付, 交付数据→交付, 销量里程碑→销量, 发布会/亮相活动→亮相, 品牌传播战役→品牌, 高管发声→发声, 首发亮相→亮相, 售价公布→售价, 购车权益调整→权益, 官方价格调整→调价, 年度改款/中期改款上市→改款, 联名/代言/合作→合作, 舆情事件→舆情
- 每条采用 "① **品牌 / 车型 / 类型**：动作描述（来源名称）" 格式
- 车型为空时格式为 "① **品牌 / 类型**：动作描述（来源）"
- 动作描述用一句话概括核心事实，不含来源名称
- 来源名称放在末尾括号内，简短（括号外无空格），如（比亚迪官方）
- 整个简报不超过 20 行
- 少于 4 条时列实际条数
- 只使用 facts 信息，不编造
- 专业、简洁、中文"""

_SEARCH_BRIEF_PROMPT = """你是一个新能源汽车行业分析师。根据搜索发现的事件事实，生成一份{pipeline_label}。

报告必须包含以下五部分：

## {section_primary}
- 挑选最重要的 3-5 个事件，按重要程度排列
- 每条写明：品牌、车型、事件类型、简要动作、信息来源

## 品牌动作速览
- 按品牌聚合，列出每个品牌所有动作

## 事件类型分布
- 按类型汇总，写明涉及品牌数量和事件数

## {section_observation}
- 2-3 句分析性观察

## 信源质量
- 官方 / 行业媒体 / 社交信号 / 未验证 的分布

写作要求：
- 专业、简洁、用中文
- 不要编造数据
- 事件类型译为中文：launch=上市, presale=预售, benefit_adjustment=权益调整, delivery_start=交付, delivery_metric=交付数据, sales_milestone=销量里程碑, technology_release=技术发布, ota_update=OTA更新, channel_campaign=渠道活动, config_release=配置发布, price_release=售价公布
- 标题去掉平台后缀
- 报告标题：单品牌搜索用"{brand_focused}搜索简报"，多品牌用"市场搜索简报"
- 用"{period_label}"描述时间窗口"""


def _prompt_for_pipeline(pipeline: str = None, stats: dict = None, date_str: str = None) -> tuple:
    """根据 pipeline 返回 (prompt_template, context_dict)。"""
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    if pipeline == "daily":
        dt = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
        date_with_weekday = f"{date_str or dt.strftime('%Y-%m-%d')}（{weekdays[dt.weekday()]}）"
        ctx = {
            "date_with_weekday": date_with_weekday,
            "event_count": stats.get("event_count", 0),
            "brand_count": stats.get("brand_count", 0),
            "official_pct": stats.get("official_pct", 0),
        }
        return _DAILY_BRIEF_PROMPT, ctx
    ctx = {
        "pipeline_label": "搜索简报（基于公开搜索发现的事件）",
        "section_primary": "重点事件",
        "section_observation": "搜索观察",
        "period_label": "本周期",
        "brand_focused": "品牌级",
    }
    return _SEARCH_BRIEF_PROMPT, ctx


def _load_api_key() -> Optional[str]:
    return os.environ.get(_DEEPSEEK_API_KEY_ENV) or os.environ.get("DEEPSEEK_API_KEY")


def _build_user_message(facts: list[dict]) -> str:
    """将 facts 组装为 LLM 输入文本。"""
    if not facts:
        return "facts 库为空，无法生成简报。"

    lines = ["以下是今日 facts 库中的营销事件事实，请生成简报：", ""]
    for i, f in enumerate(facts, 1):
        brand = f.get("brand") or "?"
        model = f.get("model") or ""
        et = f.get("event_type") or "?"
        title = (f.get("title") or "")[:100]
        source = f.get("source_name") or "?"
        tier = f.get("source_tier") or "?"
        model_tag = f" / {model}" if model else ""
        lines.append(f"{i}. [{brand}{model_tag}] {et}: {title}（{source}, {tier}）")

    return "\n".join(lines)


def generate_llm_brief(facts: list[dict], brief_date: str = None, pipeline: str = None) -> str:
    """
    用 LLM 生成简报。

    pipeline: "search" | "daily" | None — 影响报告样式。
    daily 模式输出极简三段式（15 行以内），search 模式输出五段式详细分析。
    若 LLM 不可用（无 API key / 网络错误），返回空字符串，
    由调用方降级到规则脚本。
    """
    api_key = _load_api_key()
    if not api_key:
        return ""

    date_str = brief_date or datetime.now().strftime("%Y-%m-%d")

    # Pre-compute stats
    event_count = len(facts)
    brands = {f.get("brand") for f in facts if f.get("brand")}
    brand_count = len(brands)
    official_count = sum(1 for f in facts if f.get("source_tier") == "tier_1_official")
    official_pct = round(official_count / event_count * 100) if event_count else 0
    stats = {"event_count": event_count, "brand_count": brand_count, "official_pct": official_pct}

    prompt_template, ctx = _prompt_for_pipeline(pipeline, stats, date_str)

    # Detect if single brand (search mode only)
    if pipeline != "daily":
        ctx["brand_focused"] = f"{next(iter(brands))} " if len(brands) == 1 else ""

    system_prompt = prompt_template.format(**ctx)
    user_msg = _build_user_message(facts)

    if not facts:
        return _empty_brief(date_str, pipeline=pipeline, stats=stats)

    try:
        resp = httpx.post(
            _DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        if pipeline == "daily":
            # Ensure daily brief starts with the car emoji header
            if not content.startswith("🚗"):
                wd = ctx["date_with_weekday"]
                content = f"🚗 重点新能源品牌每日营销事件监控\n{wd}\n\n📊 今日概况\n事件 {event_count}｜品牌 {brand_count}｜官方 {official_pct}%\n\n🔥 今日重点\n{content}"
        else:
            if not content.startswith("# "):
                label = f"{ctx['brand_focused']}搜索简报" if pipeline == "search" else "每日简报"
                content = f"# Auto Launch {label} — {date_str}\n\n{content}"
        return content

    except Exception as e:
        print(f"[llm_brief] LLM 调用失败: {e}", file=__import__('sys').stderr)
        return ""


def _empty_brief(date_str: str, pipeline: str = None, stats: dict = None) -> str:
    stats = stats or {}
    if pipeline == "daily":
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        dt = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
        wd = f"{date_str or dt.strftime('%Y-%m-%d')}（{weekdays[dt.weekday()]}）"
        return f"""🚗 重点新能源品牌每日营销事件监控
{wd}

📊 今日概况
事件 0｜品牌 0｜官方 0%

🔥 今日重点
（无）— 当前 facts 库为空"""
    return f"""# Auto Launch 每日简报 — {date_str}

## 今日重点

（无）— 当前 facts 库无匹配有效事实。

## 品牌动作速览

facts 库未发现可用于生成简报的有效事实。

## 今日观察

- facts 库为空或全部被过滤，无法生成简报。
- 请通过 daily 或 search --to-facts 导入事实。

## 信源质量

（无）
"""
