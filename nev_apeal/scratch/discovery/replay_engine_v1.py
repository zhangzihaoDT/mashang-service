"""Re-run frozen Discovery Engine v1 without mutating historical artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from analysis._common import load
from scratch.signal_scan import fixed_bins, scan_binned, scan_categorical, axis_gap
from scratch.discovery.expectation_wow_scan import EXPOSURES, build_signal, clean_levels, delight_cross, level_stats, wow_regression
from scratch.discovery.nonlinear_pattern_scan import REGISTERED as NONLINEAR_REGISTERED, scan_one
from scratch.discovery.segment_discriminator_scan import REGISTERED as SEGMENT_REGISTERED, scan_pair
from scratch.discovery.interaction_scan import TESTS, run_test

OUT = Path(__file__).resolve().parent / "replay_v1"
CATEGORICAL_AXES = [
    ("Region_DP", "地理·大区", None), ("CITY_TIER_DP", "地理·城市层级", None), ("ORIGIN3_DP", "OEM 来源结构", None),
    ("PREMMAKE_DP", "OEM 豪华/大众", None), ("SUB_ORIGIN_DP", "OEM 原产地", None), ("NEV_01", "充电生活·慢充频率", None),
    ("NEV_08", "充电生活·快充频率", None), ("NEV_05_R1", "充电生活·家充可用性", None), ("NEV_07", "充电生活·车位共享", None),
    ("NEV_11A", "使用场景·通勤", None), ("NEV_11B", "使用场景·商务", None), ("NEV_11C", "使用场景·个人/家庭", None),
    ("NEV_11D", "使用场景·户外", None), ("NEV_11E", "使用场景·越野", None), ("NEV_11F", "使用场景·拖拽", None),
    ("NEV_11G", "使用场景·驾驶乐趣", None), ("CN_EDUCATION", "家庭·教育", None), ("CN_OCCUPATION", "家庭·职业", None),
    ("CN_MARITAL_STATUS", "家庭·婚况", None), ("AGE_BUCKETS", "人口·年龄分桶", None), ("GENDER", "人口·性别", None),
]


def round1(df, meta) -> list[dict]:
    board = []
    for name, label, drop in CATEGORICAL_AXES:
        rows = scan_categorical(df, meta, name, drop_labels=drop)
        board.append({"axis": name, "label": label, "gap": axis_gap(rows), "rows": rows})
    binned_axes = [
        ("NEV_12", "使用强度·累积里程", fixed_bins(df["NEV_12"], [1000, 5000, 10000, 20000, 50000], ["<1k", "1k-5k", "5k-10k", "10k-20k", "20k-50k", "50k+"])),
        ("NEV_13a", "使用强度·日均驾驶时长", fixed_bins(df["NEV_13a"], [1, 2, 4], ["<1h", "1-2h", "2-4h", "4h+"])),
        ("CN_NUMBER_HOUSEHOLD", "家庭·人口规模", fixed_bins(df["CN_NUMBER_HOUSEHOLD"], [1, 2, 3], ["1", "2", "3", "4+"])),
        ("YPV_05", "家庭·车辆数", fixed_bins(df["YPV_05"], [1, 2], ["1", "2", "3+"])),
    ]
    for name, label, binned in binned_axes:
        rows = scan_binned(df, name, binned)
        board.append({"axis": name, "label": label, "gap": axis_gap(rows), "rows": rows})
    return sorted(board, key=lambda b: (b["gap"] is None, -(b["gap"] or -1)))


def expectation_signals(df, meta) -> list[dict]:
    signals = []
    for var, label, module_ix in EXPOSURES:
        s = clean_levels(meta, df, var)
        for outcome in ["APEAL_Index", module_ix]:
            signals.append(build_signal(f"expectation_wow_{len(signals)+1:02d}", var, label, outcome, level_stats(df, s, outcome), wow_regression(df, meta, var, outcome), int(s.notna().sum())))
        cross = delight_cross(df, meta, var)
        signals.append({"signal_id": f"expectation_wow_{len(signals)+1:02d}", "analysis_type": "expectation_wow", "exposure": var, "outcome": f"{module_ix} (delight top picks)", "effect_size": {}, "sample_support": {"n": cross["n_better"], "coverage": "PARTIAL"}, "stability": "moderate", "novelty": 4, "interpretation": f"{label} Better 亚组 delight 描述", "caveats": "缺失率高，仅描述，不作独立候选", "delight_top": cross["items"]})
    return signals


def main() -> None:
    df, meta = load()
    OUT.mkdir(parents=True, exist_ok=True)
    r1 = round1(df, meta)
    r2 = expectation_signals(df, meta)
    r2.append(scan_one(df, "NEV_12", NONLINEAR_REGISTERED["NEV_12"]))
    for exposure, moderator, exposure_label, moderator_label, contrast in SEGMENT_REGISTERED:
        signal = scan_pair(df, exposure, moderator, exposure_label, moderator_label, contrast)
        if signal:
            r2.append(signal)
    interactions = [run_test(df, *test) for test in TESTS]
    payload = {"engine_version": "discovery_engine_v1", "round1_main_effect": r1, "round2_signals": r2, "interaction_pilot": interactions}
    (OUT / "replay_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"round1_axes": len(r1), "round2_signals": len(r2), "interaction_tests": len(interactions), "output": str(OUT / "replay_results.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
