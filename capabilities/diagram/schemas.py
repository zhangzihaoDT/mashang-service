"""Data contracts for the Diagram Base Capability.

Currently defines one reusable chart primitive:

    Milestone Temporal Dumbbell — compare two entities' time positions
    across a set of corresponding milestones, plus the time delta.

The contract is intentionally flat: one row per milestone, mirroring the
standard tabular shape used in business analysis work.

    milestone, entity_a, date_a, event_a, entity_b, date_b, event_b

`delta_days` is always derived (date_b - date_a) and never supplied by the
caller, so the rendered figure and the JSON contract can never disagree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Optional

CHART_TYPE_MILESTONE_DUMBBELL = "milestone_temporal_dumbbell"

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")


class DumbbellValidationError(ValueError):
    """Raised when a milestone dumbbell chart's input is not renderable."""


def parse_date(value: Any) -> date:
    """Parse a date-like value into a ``datetime.date``.

    Accepts ``date``, ``datetime``, and the string formats
    ``YYYY-MM-DD`` / ``YYYY/MM/DD`` / ``YYYY.MM.DD``.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise DumbbellValidationError(
        f"Invalid date {value!r}; expected YYYY-MM-DD"
    )


@dataclass
class MilestoneDumbbellRow:
    """One milestone and the two entities' event dates for it."""

    milestone: str
    date_a: Any
    date_b: Any
    entity_a: str = ""
    event_a: str = ""
    entity_b: str = ""
    event_b: str = ""

    @property
    def parsed_date_a(self) -> date:
        return parse_date(self.date_a)

    @property
    def parsed_date_b(self) -> date:
        return parse_date(self.date_b)

    @property
    def delta_days(self) -> int:
        """Signed gap in days, computed as ``date_b - date_a``."""
        return (self.parsed_date_b - self.parsed_date_a).days

    @property
    def anchor_date(self) -> date:
        """Earlier of the two dates — used for stable row ordering."""
        return min(self.parsed_date_a, self.parsed_date_b)

    def to_dict(self) -> dict:
        return {
            "milestone": self.milestone,
            "entity_a": self.entity_a,
            "date_a": self.parsed_date_a.isoformat(),
            "event_a": self.event_a,
            "entity_b": self.entity_b,
            "date_b": self.parsed_date_b.isoformat(),
            "event_b": self.event_b,
            "delta_days": self.delta_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MilestoneDumbbellRow":
        return cls(
            milestone=str(data.get("milestone", "")),
            date_a=data.get("date_a", ""),
            date_b=data.get("date_b", ""),
            entity_a=str(data.get("entity_a", "") or ""),
            event_a=str(data.get("event_a", "") or ""),
            entity_b=str(data.get("entity_b", "") or ""),
            event_b=str(data.get("event_b", "") or ""),
        )


@dataclass
class MilestoneDumbbellChart:
    """A milestone temporal dumbbell chart definition."""

    rows: list[MilestoneDumbbellRow] = field(default_factory=list)
    title: str = ""
    subtitle: str = ""
    entity_a: str = ""
    entity_b: str = ""
    source_note: str = ""
    chart_type: str = CHART_TYPE_MILESTONE_DUMBBELL

    def validate(self) -> "MilestoneDumbbellChart":
        """Validate the chart and resolve the two entity names in place.

        Raises :class:`DumbbellValidationError` with an actionable message.
        """
        if not self.rows:
            raise DumbbellValidationError("chart needs at least one milestone row")

        seen: set[str] = set()
        for index, row in enumerate(self.rows):
            milestone = row.milestone.strip()
            if not milestone:
                raise DumbbellValidationError(f"row[{index}] has an empty milestone")
            if milestone in seen:
                raise DumbbellValidationError(
                    f"duplicate milestone {milestone!r}; each milestone must appear once"
                )
            seen.add(milestone)
            try:
                row.parsed_date_a
                row.parsed_date_b
            except DumbbellValidationError as exc:
                raise DumbbellValidationError(
                    f"row[{index}] milestone {milestone!r}: {exc}"
                ) from exc

        self.entity_a = self._resolve_entity("a")
        self.entity_b = self._resolve_entity("b")
        return self

    def _resolve_entity(self, side: str) -> str:
        chart_name = str(getattr(self, f"entity_{side}") or "").strip()
        row_names = {
            str(getattr(row, f"entity_{side}") or "").strip()
            for row in self.rows
        }
        row_names.discard("")

        if chart_name:
            conflicting = sorted(name for name in row_names if name != chart_name)
            if conflicting:
                raise DumbbellValidationError(
                    f"entity_{side} {chart_name!r} conflicts with row value(s) {conflicting}"
                )
            return chart_name
        if len(row_names) == 1:
            return next(iter(row_names))
        if len(row_names) > 1:
            raise DumbbellValidationError(
                f"entity_{side} is ambiguous across rows: {sorted(row_names)}; "
                f"set a chart-level entity_{side}"
            )
        raise DumbbellValidationError(f"entity_{side} is required")

    def sorted_rows(self) -> list[MilestoneDumbbellRow]:
        """Rows ordered by their earlier endpoint date (stable)."""
        return sorted(self.rows, key=lambda row: (row.anchor_date, row.milestone))

    def to_dict(self) -> dict:
        rows = []
        for row in self.sorted_rows():
            data = row.to_dict()
            data["entity_a"] = self.entity_a or data["entity_a"]
            data["entity_b"] = self.entity_b or data["entity_b"]
            rows.append(data)
        return {
            "chart_type": self.chart_type,
            "title": self.title,
            "subtitle": self.subtitle,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "source_note": self.source_note,
            "rows": rows,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "MilestoneDumbbellChart":
        raw_rows = data.get("rows", [])
        if not isinstance(raw_rows, list):
            raise DumbbellValidationError("'rows' must be a list of milestone objects")
        return cls(
            rows=[MilestoneDumbbellRow.from_dict(row) for row in raw_rows],
            title=str(data.get("title", "") or ""),
            subtitle=str(data.get("subtitle", "") or ""),
            entity_a=str(data.get("entity_a", "") or ""),
            entity_b=str(data.get("entity_b", "") or ""),
            source_note=str(data.get("source_note", "") or ""),
        )


# ---------------------------------------------------------------------------
# Comparison Line — compare several entities on the same ordered categories
# ---------------------------------------------------------------------------

CHART_TYPE_COMPARISON_LINE = "comparison_line"

LINE_ROLES = ("own", "peer")


class ComparisonLineValidationError(ValueError):
    """Raised when a comparison line chart's input is not renderable."""


def _coerce_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ComparisonLineValidationError(f"{where} must be a number, got {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ComparisonLineValidationError(
            f"{where} must be a number, got {value!r}"
        ) from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ComparisonLineValidationError(f"{where} must be finite, got {value!r}")
    return number


@dataclass
class ComparisonLineSeries:
    """One entity's values across the chart's ordered categories.

    ``role`` only drives visual emphasis (``own`` = the subject of the
    analysis, always solid and heavier); it carries no business meaning.
    ``color`` / ``dash`` are optional overrides on top of the default palette.
    """

    name: str
    values: list[float] = field(default_factory=list)
    role: str = "peer"
    color: str = ""
    dash: str = ""

    def to_dict(self) -> dict:
        payload = {
            "name": self.name,
            "role": self.role,
            "values": list(self.values),
        }
        if self.color:
            payload["color"] = self.color
        if self.dash:
            payload["dash"] = self.dash
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonLineSeries":
        if not isinstance(data, dict):
            raise ComparisonLineValidationError("each series must be an object")
        raw_values = data.get("values", [])
        if not isinstance(raw_values, (list, tuple)):
            raise ComparisonLineValidationError("series 'values' must be a list")
        return cls(
            name=str(data.get("name", "") or ""),
            values=list(raw_values),
            role=str(data.get("role", "peer") or "peer"),
            color=str(data.get("color", "") or ""),
            dash=str(data.get("dash", "") or ""),
        )


@dataclass
class ComparisonLineChart:
    """A multi-entity comparison line chart over ordered categories."""

    categories: list[str] = field(default_factory=list)
    series: list[ComparisonLineSeries] = field(default_factory=list)
    title: str = ""
    subtitle: str = ""
    x_label: str = ""
    y_label: str = ""
    source_note: str = ""
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    y_step: Optional[float] = None
    markers: Optional[bool] = None
    decimals: int = 0
    value_suffix: str = ""
    chart_type: str = CHART_TYPE_COMPARISON_LINE

    def validate(self) -> "ComparisonLineChart":
        """Validate the chart in place and normalise numeric values."""
        categories = [str(c).strip() for c in self.categories]
        if len(categories) < 2:
            raise ComparisonLineValidationError("chart needs at least two categories")
        if any(not c for c in categories):
            raise ComparisonLineValidationError("categories cannot be empty")
        if len(set(categories)) != len(categories):
            raise ComparisonLineValidationError("categories must be unique")
        self.categories = categories

        if len(self.series) < 2:
            raise ComparisonLineValidationError("chart needs at least two series")

        names: set[str] = set()
        own_count = 0
        for index, item in enumerate(self.series):
            name = str(item.name).strip()
            if not name:
                raise ComparisonLineValidationError(f"series[{index}] has an empty name")
            if name in names:
                raise ComparisonLineValidationError(
                    f"duplicate series name {name!r}; each series must appear once"
                )
            names.add(name)
            item.name = name

            if len(item.values) != len(categories):
                raise ComparisonLineValidationError(
                    f"series {name!r} has {len(item.values)} values but the chart has "
                    f"{len(categories)} categories"
                )
            item.values = [
                _coerce_number(value, f"series {name!r} value[{i}]")
                for i, value in enumerate(item.values)
            ]

            if item.role not in LINE_ROLES:
                raise ComparisonLineValidationError(
                    f"series {name!r} role must be one of {LINE_ROLES}, got {item.role!r}"
                )
            if item.role == "own":
                own_count += 1
        if own_count > 1:
            raise ComparisonLineValidationError("at most one series can use role='own'")

        if not 0 <= int(self.decimals) <= 3:
            raise ComparisonLineValidationError("decimals must be between 0 and 3")
        self.decimals = int(self.decimals)

        for attr in ("y_min", "y_max", "y_step"):
            value = getattr(self, attr)
            if value is not None:
                setattr(self, attr, _coerce_number(value, attr))
        if self.y_step is not None and self.y_step <= 0:
            raise ComparisonLineValidationError("y_step must be positive")
        if (
            self.y_min is not None
            and self.y_max is not None
            and self.y_max <= self.y_min
        ):
            raise ComparisonLineValidationError("y_max must be greater than y_min")
        return self

    @property
    def own_series(self) -> Optional[ComparisonLineSeries]:
        for item in self.series:
            if item.role == "own":
                return item
        return None

    def value_bounds(self) -> tuple[float, float]:
        values = [value for item in self.series for value in item.values]
        return min(values), max(values)

    def to_dict(self) -> dict:
        return {
            "chart_type": self.chart_type,
            "title": self.title,
            "subtitle": self.subtitle,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "source_note": self.source_note,
            "categories": list(self.categories),
            "series": [item.to_dict() for item in self.series],
            "y_min": self.y_min,
            "y_max": self.y_max,
            "y_step": self.y_step,
            "markers": self.markers,
            "decimals": self.decimals,
            "value_suffix": self.value_suffix,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonLineChart":
        if not isinstance(data, dict):
            raise ComparisonLineValidationError("input JSON must be an object")
        raw_categories = data.get("categories", [])
        raw_series = data.get("series", [])
        if not isinstance(raw_categories, (list, tuple)):
            raise ComparisonLineValidationError("'categories' must be a list")
        if not isinstance(raw_series, list):
            raise ComparisonLineValidationError("'series' must be a list of objects")
        markers = data.get("markers", None)
        return cls(
            categories=list(raw_categories),
            series=[ComparisonLineSeries.from_dict(item) for item in raw_series],
            title=str(data.get("title", "") or ""),
            subtitle=str(data.get("subtitle", "") or ""),
            x_label=str(data.get("x_label", "") or ""),
            y_label=str(data.get("y_label", "") or ""),
            source_note=str(data.get("source_note", "") or ""),
            y_min=data.get("y_min"),
            y_max=data.get("y_max"),
            y_step=data.get("y_step"),
            markers=None if markers is None else bool(markers),
            decimals=int(data.get("decimals", 0) or 0),
            value_suffix=str(data.get("value_suffix", "") or ""),
        )
