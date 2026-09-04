#!/usr/bin/env python
"""Runtime V2 内核泛化测试 + 去业务硬编码静态审计。

覆盖：
  - config 注入新能力（demo_cap）即可被 dispatch，无需改内核代码
  - 禁用能力不会被匹配
  - no-match 消息通用（列出 enabled label，不含写死 capability_id）
  - response_renderer 的 metric_labels / hint_suffix 参数注入生效，缺省兼容
  - 静态审计：核心 app 模块不含锁单领域 token（把"去硬编码"固化为测试）

本文件 hermetic：不执行脚本、不读 dataset。
"""

import json
import sys
from pathlib import Path

import pytest

_V2_ROOT = Path(__file__).resolve().parents[1]

CORE_MODULES = [
    "app/capability_dispatcher.py",
    "app/response_renderer.py",
    "app/runtime_service.py",
]
BANNED_TOKENS = [
    "lock_by_model",
    "lock_city_distribution",
    "lock_count",
    "锁单",
    "城市分布",
    "分车型",
    "总锁单数",
]


def _demo_config() -> dict:
    return {
        "enabled_capabilities": ["demo_cap"],
        "capabilities": {
            "demo_cap": {
                "script": "mashang_workspace/runtime_scripts/lock_by_model.py",
                "label": "演示能力",
                "dispatch": {
                    "explicit": {"group_by": ["model"], "keywords": ["demo", "演示"], "confidence": 0.9},
                    "keyword_fallback": {"keywords": ["随便查查"], "metric_allowed": ["", "lock_count"], "confidence": 0.6},
                },
            }
        },
        "metric_labels": {"demo_metric": "演示指标"},
    }


@pytest.fixture()
def _fake_config(tmp_path, monkeypatch):
    from app import capability_dispatcher as cd
    path = tmp_path / "runtime_v2_config.json"
    path.write_text(json.dumps(_demo_config(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cd, "CONFIG_PATH", path)


# ── Generic dispatch via config ───────────────────────────────────

class TestGenericDispatch:
    def test_injected_capability_matches_without_code_change(self, _fake_config):
        """config 加一个 demo 能力即可被 dispatch（explicit）。"""
        from app.capability_dispatcher import dispatch
        ctx = {"raw_text": "demo 演示一下", "resolved_context": {"metric": "some_metric", "group_by": "model"}}
        r = dispatch(ctx)
        assert r["capability_id"] == "demo_cap"

    def test_keyword_fallback_rule_matches(self, _fake_config):
        from app.capability_dispatcher import dispatch
        ctx = {"raw_text": "随便查查", "resolved_context": {"metric": "", "group_by": ""}}
        r = dispatch(ctx)
        assert r["capability_id"] == "demo_cap"
        assert r["reason"] == "keyword fallback"

    def test_disabled_capability_not_matched(self, _fake_config, monkeypatch):
        from app import capability_dispatcher as cd
        cfg = _demo_config()
        cfg["enabled_capabilities"] = []
        p = Path(str(cd.CONFIG_PATH))
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        ctx = {"raw_text": "demo 演示", "resolved_context": {"group_by": "model"}}
        r = cd.dispatch(ctx)
        assert r["capability_id"] is None

    def test_no_match_message_is_generic(self, _fake_config):
        from app.capability_dispatcher import dispatch
        ctx = {"raw_text": "完全无关的内容", "resolved_context": {}}
        r = dispatch(ctx)
        assert r["capability_id"] is None
        assert r["message"].startswith("未匹配到已启用的能力：")
        assert "演示能力" in r["message"]
        assert "demo_cap" not in r["message"]


# ── Renderer parameterization ─────────────────────────────────────

class TestRendererParams:
    def test_metric_labels_and_suffix_injected(self):
        from app.response_renderer import render
        data = {
            "status": "success",
            "metrics": {"total": 100},
            "followup_context": {"top_entities": [{"value": "LS8"}]},
        }
        out = render(data, metric_labels={"total": "总量"}, hint_suffix="分车型")
        assert "总量：100" in out
        assert "LS8" in out and "分车型" in out

    def test_renderer_defaults_compatible(self):
        from app.response_renderer import render
        data = {"status": "success", "summary": "s", "metrics": {"k": 1}}
        out = render(data)
        assert "k：1" in out


# ── Static audit: no lock-domain tokens in core modules ───────────

class TestCoreStaticAudit:
    @pytest.mark.parametrize("rel", CORE_MODULES)
    @pytest.mark.parametrize("token", BANNED_TOKENS)
    def test_core_module_has_no_lock_token(self, rel, token):
        path = _V2_ROOT / rel
        text = path.read_text(encoding="utf-8")
        assert token not in text, f"{rel} 含业务硬编码 token: {token!r}"
