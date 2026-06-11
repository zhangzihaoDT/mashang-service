from __future__ import annotations
import json
from pathlib import Path


_METRICS_FILE = Path(__file__).resolve().parent / "metrics.json"


class MetricRegistry:
    def __init__(self, metrics_file: str | Path = _METRICS_FILE):
        self._raw: dict = {}
        self._alias_to_canonical: dict[str, str] = {}
        with open(metrics_file, encoding="utf-8") as f:
            self._raw = json.load(f)
        self._build_index()

    def _build_index(self):
        metrics = self._raw.get("metrics", {})
        for name, cfg in metrics.items():
            self._alias_to_canonical[name] = name
            for alias in cfg.get("aliases", []):
                if alias not in self._alias_to_canonical:
                    self._alias_to_canonical[alias] = name

    def resolve(self, name_or_alias: str) -> str | None:
        return self._alias_to_canonical.get(name_or_alias)

    def get(self, name_or_alias: str) -> dict | None:
        canonical = self.resolve(name_or_alias)
        if canonical:
            return self._raw.get("metrics", {}).get(canonical)
        return self._raw.get("derived_metrics", {}).get(name_or_alias)

    def match_by_query(self, query: str) -> list[tuple[str, dict]]:
        metrics = self._raw.get("metrics", {})
        results: list[tuple[str, dict]] = []
        for name, cfg in metrics.items():
            all_tokens = [name] + cfg.get("aliases", [])
            if any(t in query for t in all_tokens if t):
                results.append((name, cfg))
        derived = self._raw.get("derived_metrics", {})
        for name, cfg in derived.items():
            all_tokens = [name] + cfg.get("aliases", [])
            if any(t in query for t in all_tokens if t):
                results.append((name, cfg))
        return results

    def get_group(self, group_name: str) -> list[str] | None:
        groups = self._raw.get("metric_groups", {})
        g = groups.get(group_name)
        if g:
            return g.get("metrics", [])
        return None

    def get_all_metric_names(self) -> list[str]:
        return list(self._raw.get("metrics", {}).keys())

    def is_operator_metric(self, name_or_alias: str) -> bool:
        cfg = self.get(name_or_alias)
        return bool(cfg and cfg.get("type") == "operator")

    def get_operator_name(self, name_or_alias: str) -> str | None:
        cfg = self.get(name_or_alias)
        if cfg and cfg.get("type") == "operator":
            return cfg.get("operator")
        return None

    def match_metric_relation(self, query: str, relation_type: str | None = None) -> tuple[str, dict] | None:
        relations = self._raw.get("metric_relations", {})
        scored: list[tuple[int, str, dict]] = []
        for name, cfg in relations.items():
            if cfg.get("type") not in ("ratio",):
                continue
            if relation_type and cfg.get("type") != relation_type:
                continue
            all_tokens = [name] + (cfg.get("aliases") or [])
            for t in all_tokens:
                if t and t in query:
                    scored.append((len(t) + 200, name, cfg))
                    break
        if scored:
            scored.sort(key=lambda x: -x[0])
            return (scored[0][1], scored[0][2])

        relation_keywords = {"占比", "比例", "比率", "率", "份额", "占"}
        if not any(k in query for k in relation_keywords):
            return None

        metrics = self._raw.get("metrics", {})
        candidates = []
        for name, cfg in relations.items():
            if cfg.get("type") not in ("ratio",):
                continue
            num = cfg.get("numerator", "")
            den = cfg.get("denominator", "")
            num_tokens = [num] + (metrics.get(num, {}).get("aliases", []) if num in metrics else [])
            den_tokens = [den] + (metrics.get(den, {}).get("aliases", []) if den in metrics else [])
            num_match = any(t and t in query for t in num_tokens)
            den_match = any(t and t in query for t in den_tokens)
            name_match = any(t and t in query for t in [name] + (cfg.get("aliases") or []))
            if name_match:
                candidates.append((500, name, cfg))
            elif num_match and den_match:
                candidates.append((300, name, cfg))
        if candidates:
            candidates.sort(key=lambda x: -x[0])
            return (candidates[0][1], candidates[0][2])
        return None

    def to_markdown_catalog(self) -> str:
        lines = ["## 可用指标 (Metric Registry)\n"]
        groups = self._raw.get("metric_groups", {})
        metrics = self._raw.get("metrics", {})
        for gname, ginfo in groups.items():
            lines.append(f"\n### {gname} — {ginfo.get('description', '')}")
            for mname in ginfo.get("metrics", []):
                cfg = metrics.get(mname)
                if not cfg:
                    continue
                aliases = cfg.get("aliases", [])
                alias_str = f" (别名: {'/'.join(aliases[:3])})" if aliases else ""
                mtype = cfg.get("type", "")
                lines.append(f"- **{mname}**{alias_str} — {cfg.get('dataset')}.{cfg.get('field')} [{cfg.get('agg')}]{' [算子]' if mtype == 'operator' else ''}")
        return "\n".join(lines) + "\n"

    def to_metric_defaults_md(self) -> str:
        lines = ["### 业务指标默认映射 (Metric Defaults)\n"]
        metrics = self._raw.get("metrics", {})
        for name, cfg in metrics.items():
            if cfg.get("type") == "operator":
                continue
            field = cfg.get("field")
            agg = cfg.get("agg")
            time_field = cfg.get("time_field")
            aliases = cfg.get("aliases", [])
            alias_str = f" (别名: {'/'.join(aliases[:3])})" if aliases else ""
            lines.append(f"- **{name}**{alias_str}: `{agg}({field})` → time_field=`{time_field}`, dataset=`{cfg.get('dataset')}`")
        return "\n".join(lines) + "\n"
