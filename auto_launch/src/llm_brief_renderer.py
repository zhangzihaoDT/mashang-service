"""Layer: LLM — 基于 LLM 的简报生成（质量优于规则脚本）"""

import json, os, re
from datetime import datetime
from typing import Optional

import httpx

_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
_DEFAULT_MODEL = "deepseek-chat"

_BRIEF_SYSTEM_PROMPT_TEMPLATE = """你是一个新能源汽车行业分析师。你的任务是根据 facts 库中的营销事件事实，生成一份专业、可读的{report_type}。

简报必须包含以下五个部分：

## {section_primary}
- 挑选最重要的 3-5 个事件，按重要程度排列
- 每条写明：品牌、车型、事件类型、简要动作、信息来源
- 相似事件合并为一条（如"交付数据"合并为一句"XX 交付 X 台，同比增长 X%"）

## 品牌动作速览
- 按品牌聚合
- 每个品牌下列出该品牌所有动作
- 同一品牌下相似事件合并

## 事件类型分布
- 按类型汇总：交付/销量、上市/预售、权益/价格、技术/产品、品牌/渠道
- 写明涉及品牌数量和事件数

## {section_observation}
- 2-3 句分析性观察
- 包括：主要动作集中领域、官方源覆盖情况、哪些品牌或事件值得后续跟踪
- 语气专业、客观、数据支撑

## 信源质量
- 官方 / 行业媒体 / 社交信号 / 未验证 的分布

写作要求：
- 专业、简洁、用中文
- 不要编造数据
- 事件类型译为中文：launch=上市, presale=预售, benefit_adjustment=权益调整, delivery_start=交付, delivery_metric=交付数据, sales_milestone=销量里程碑, technology_release=技术发布, ota_update=OTA更新, channel_campaign=渠道活动
- 标题去掉平台后缀
- 报告标题反映数据来源：单品牌搜索用"{brand_focused}搜索简报"，多品牌用"市场搜索简报"
- 不要在内容内再添加"新能源汽车行业"等宽泛标题
- 用"{period_label}"而非"今日"来描述时间窗口，避免误导
- 如果 facts 为空的生成空状态报告"""


def _prompt_for_pipeline(pipeline: str = None) -> dict:
    """根据 pipeline 返回 prompt 上下文。"""
    if pipeline == "search":
        return {
            "report_type": "搜索简报（基于公开搜索发现的事件）",
            "section_primary": "重点事件",
            "section_observation": "搜索观察",
            "period_label": "本周期",
            "brand_focused": "品牌级",
        }
    return {
        "report_type": "每日简报（基于 facts 库收录的事件）",
        "section_primary": "今日重点",
        "section_observation": "今日观察",
        "period_label": "今日",
        "brand_focused": "",
    }


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

    pipeline: "search" | "daily" | None — 影响报告标题和措辞。
    若 LLM 不可用（无 API key / 网络错误），返回空字符串，
    由调用方降级到规则脚本。
    """
    api_key = _load_api_key()
    if not api_key:
        return ""

    date_str = brief_date or datetime.now().strftime("%Y-%m-%d")
    ctx = _prompt_for_pipeline(pipeline)
    # Detect if single brand
    brands = {f.get("brand") for f in facts if f.get("brand")}
    ctx["brand_focused"] = f"{next(iter(brands))} " if len(brands) == 1 else ""
    system_prompt = _BRIEF_SYSTEM_PROMPT_TEMPLATE.format(**ctx)
    user_msg = _build_user_message(facts)

    if not facts:
        return _empty_brief(date_str, filtered_count=0)

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
        # Wrap in markdown title if not present
        if not content.startswith("# "):
            label = f"{ctx['brand_focused']}搜索简报" if pipeline == "search" else "每日简报"
            content = f"# Auto Launch {label} — {date_str}\n\n{content}"
        return content

    except Exception as e:
        print(f"[llm_brief] LLM 调用失败: {e}", file=__import__('sys').stderr)
        return ""


def _empty_brief(date_str: str, filtered_count: int = 0) -> str:
    filter_note = f"\n已过滤 test/invalid 数据 {filtered_count} 条。" if filtered_count else ""
    return f"""# Auto Launch 每日简报 — {date_str}

## 今日重点

（无）— 当前 facts 库无匹配有效事实。{filter_note}

## 品牌动作速览

facts 库未发现可用于生成简报的有效事实。

## 今日观察

- facts 库为空或全部被过滤，无法生成简报。
- 请通过 daily 或 search --to-facts 导入事实。

## 信源质量

（无）
"""
