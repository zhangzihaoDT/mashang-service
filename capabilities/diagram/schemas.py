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
