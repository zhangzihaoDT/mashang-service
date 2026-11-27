import pandas as pd
import pytest

from dataset.updater import lock_attribution_data_to_parquet
from dataset.updater.refresh_validation import inspect_dataset, publish_dataset


def _attribution(rows):
    frame = pd.DataFrame(rows, columns=["lc_user_phone_md5", "lc_main_code", "lc_order_lock_time_min"])
    frame["lc_order_lock_time_min"] = pd.to_datetime(frame["lc_order_lock_time_min"])
    return frame


def test_atomic_publish_rejects_invalid_and_regressed_data(tmp_path):
    target = tmp_path / "lock_attribution_data.parquet"
    dataset = "lock_attribution"
    old = _attribution([("p1", "id1", "2026-01-01"), (None, "id2", "2026-01-02")])
    old.to_parquet(target, index=False)
    before = target.read_bytes()
    for rows, reason in [
        ([("p1", "id1", "2026-01-01")], "regressed"),
        ([("p1", "same", "2026-01-01"), ("p1", "same", "2026-01-02")], "Primary key"),
        ([("p1", "id1", None), (None, "id2", None)], "cutoff"),
    ]:
        updated = _attribution(rows)
        with pytest.raises(ValueError, match=reason):
            publish_dataset(dataset, target, lambda stage: updated.to_parquet(stage, index=False))
        assert target.read_bytes() == before
    good = _attribution([("p1", "id1", "2026-01-01"), (None, "id2", "2026-01-03")])
    assert publish_dataset(dataset, target, lambda stage: good.to_parquet(stage, index=False))
    assert inspect_dataset(dataset, target)["validated_cutoff"] == "2026-01-03T00:00:00"
    assert list(tmp_path.iterdir()) == [target]


def test_attribution_unreadable_history_stops_publish(tmp_path, monkeypatch):
    updater = lock_attribution_data_to_parquet
    history = tmp_path / "lock_attribution_data.parquet"
    history.write_bytes(b"invalid old parquet")
    source = tmp_path / "锁单归因_data_2026.csv"
    source.write_text("fixture")
    monkeypatch.setattr(updater, "ORIGINAL_DIR", tmp_path)
    monkeypatch.setattr(updater, "OUTPUT_FILE", history)
    monkeypatch.setattr(updater, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(updater, "read_csv_smart", lambda _: _attribution([("p", "id", "2026-01-01")]))
    assert updater.process_lock_attribution_parquet() == 1
    assert history.read_bytes() == b"invalid old parquet"
