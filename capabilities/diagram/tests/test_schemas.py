"""Tests for the milestone dumbbell data contract."""

from datetime import date

import pytest

from capabilities.diagram.schemas import (
    DumbbellValidationError,
    MilestoneDumbbellChart,
    MilestoneDumbbellRow,
    parse_date,
)


def _row(**overrides) -> MilestoneDumbbellRow:
    base: dict[str, object] = dict(
        milestone="BEV",
        date_a="2021-08-19",
        date_b="2022-05-07",
        entity_a="Tesla",
        entity_b="Huawei",
        event_a="AI Day BEV",
        event_b="ADS 1.0",
    )
    base.update(overrides)
    return MilestoneDumbbellRow(**base)  # type: ignore[arg-type]


def _chart(rows=None, **overrides) -> MilestoneDumbbellChart:
    base: dict[str, object] = dict(
        rows=rows if rows is not None else [_row()],
        title="Demo",
        entity_a="Tesla",
        entity_b="Huawei",
    )
    base.update(overrides)
    return MilestoneDumbbellChart(**base)  # type: ignore[arg-type]


class TestParseDate:
    def test_accepts_iso(self):
        assert parse_date("2021-08-19") == date(2021, 8, 19)

    def test_accepts_slash_and_dot(self):
        assert parse_date("2021/08/19") == date(2021, 8, 19)
        assert parse_date("2021.08.19") == date(2021, 8, 19)

    def test_accepts_date_object(self):
        assert parse_date(date(2022, 5, 7)) == date(2022, 5, 7)

    def test_rejects_garbage(self):
        with pytest.raises(DumbbellValidationError):
            parse_date("not-a-date")


class TestRow:
    def test_delta_days_positive(self):
        assert _row().delta_days == 261

    def test_delta_days_negative_when_a_later(self):
        row = _row(date_a="2022-05-07", date_b="2021-08-19")
        assert row.delta_days == -261

    def test_anchor_date_is_earlier(self):
        row = _row(date_a="2022-05-07", date_b="2021-08-19")
        assert row.anchor_date == date(2021, 8, 19)

    def test_to_dict_includes_derived_delta(self):
        data = _row().to_dict()
        assert data["delta_days"] == 261
        assert data["date_a"] == "2021-08-19"
        assert data["event_b"] == "ADS 1.0"

    def test_round_trip(self):
        original = _row()
        rebuilt = MilestoneDumbbellRow.from_dict(original.to_dict())
        assert rebuilt.to_dict() == original.to_dict()


class TestChartValidation:
    def test_valid_chart_resolves_entities(self):
        chart = _chart(entity_a="", entity_b="").validate()
        assert chart.entity_a == "Tesla"
        assert chart.entity_b == "Huawei"

    def test_empty_rows_rejected(self):
        with pytest.raises(DumbbellValidationError, match="at least one"):
            _chart(rows=[]).validate()

    def test_blank_milestone_rejected(self):
        with pytest.raises(DumbbellValidationError, match="empty milestone"):
            _chart(rows=[_row(milestone="  ")]).validate()

    def test_duplicate_milestone_rejected(self):
        with pytest.raises(DumbbellValidationError, match="duplicate milestone"):
            _chart(rows=[_row(), _row()]).validate()

    def test_bad_date_reported_with_milestone(self):
        with pytest.raises(DumbbellValidationError, match="BEV"):
            _chart(rows=[_row(date_a="oops")]).validate()

    def test_ambiguous_entity_rejected(self):
        rows = [_row(entity_a="Tesla"), _row(milestone="Occupancy", entity_a="Ford")]
        with pytest.raises(DumbbellValidationError, match="ambiguous"):
            _chart(rows=rows, entity_a="").validate()

    def test_conflicting_entity_rejected(self):
        rows = [_row(entity_a="Tesla")]
        with pytest.raises(DumbbellValidationError, match="conflicts"):
            _chart(rows=rows, entity_a="Ford").validate()

    def test_missing_entity_rejected(self):
        rows = [_row(entity_a="", entity_b="")]
        with pytest.raises(DumbbellValidationError, match="entity_a is required"):
            _chart(rows=rows, entity_a="", entity_b="Huawei").validate()

    def test_sorted_rows_by_anchor_date(self):
        late = _row(milestone="End-to-end", date_a="2024-01-22", date_b="2024-08-26")
        early = _row(milestone="BEV", date_a="2021-08-19", date_b="2022-05-07")
        chart = _chart(rows=[late, early]).validate()
        assert [row.milestone for row in chart.sorted_rows()] == ["BEV", "End-to-end"]

    def test_from_dict_requires_list_rows(self):
        with pytest.raises(DumbbellValidationError, match="must be a list"):
            MilestoneDumbbellChart.from_dict({"rows": "nope"})
