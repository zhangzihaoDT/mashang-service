#!/usr/bin/env python
"""
生成交付库存分析报告 — dealer_unsold_inventory.py 的结果输出为 MD 报告。

用法:
    python utility_scripts/generate_delivery_inventory_report.py
    python utility_scripts/generate_delivery_inventory_report.py --output outputs/reports/
"""

import sys, importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WS_ROOT))

import pandas as pd
import argparse

# 加载算子
spec = importlib.util.spec_from_file_location(
    "d", REPO_ROOT / "shared/operators" / "dealer_unsold_inventory.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

DEFAULT_OUTPUT = WS_ROOT / "outputs" / "reports"
INVENTORY = REPO_ROOT / "dataset" / "delivery_inventory.parquet"
ORDER_DATA = REPO_ROOT / "dataset" / "order_data.parquet"


def build_report(inv, odf) -> str:
    inv = d.compute(inv, odf)
    r = d.report(inv)

    bc = r["业务分类分布"]
    total = sum(bc.values())
    pos = r["物理位置分布"]
    cross = r["交叉表"]

    lines = []
    lines.append("# 交付库存分析报告")
    lines.append("")
    lines.append(f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**数据源**: `dataset/delivery_inventory.parquet` ({total:,} VIN) + `dataset/order_data.parquet` ({odf['vin'].nunique():,} VIN)")
    lines.append("**算子**: `shared/operators/dealer_unsold_inventory.py`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 库存定义")
    lines.append("")
    lines.append("本报告采用\"物理位置 × 业务状态\"二维分类模型：")
    lines.append("")
    lines.append("```")
    lines.append("物理库存 = 仍位于中央物流体系（VDC / VDC→DC在途 / DC内）")
    lines.append("经销商责任库存 = 已离开DC 且 属于经销商模式")
    lines.append("历史直营 = 已离开DC，无 Dealer Attribute，但订单完整")
    lines.append("")
    lines.append("库存判定 = 物理位置 + 订单状态 + Dealer模式 共同决定")
    lines.append("```")
    lines.append("")
    lines.append("所有数字均基于事件时间字段的事实判定，时序违反记录仅标记不重分类。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、VIN 全生命周期状态机")
    lines.append("")
    lines.append("```")
    lines.append("未进入物流链")
    lines.append("        │")
    lines.append("        ▼")
    lines.append("      VDC内")
    lines.append("        │")
    lines.append("        ▼")
    lines.append("  VDC→DC在途")
    lines.append("        │")
    lines.append("        ▼")
    lines.append("      DC内")
    lines.append("        │")
    lines.append("        ▼")
    lines.append("    已离开DC")
    lines.append("        │")
    lines.append("  ┌─────┴──────────┐")
    lines.append("  ▼                 ▼")
    lines.append("直营历史        经销商模式")
    lines.append("                    │")
    lines.append("           ┌────────┴────────┐")
    lines.append("           ▼                 ▼")
    lines.append("       已锁单            未锁单")
    lines.append("```")
    lines.append("")
    lines.append("## 二、物理位置分布（客观物流事实）")
    lines.append("")
    lines.append("| 物理位置 | 数量 | 占比 |")
    lines.append("|:---------|-----:|----:|")
    for s in d.PHYSICAL_STAGES:
        v = pos.get(s, 0)
        if v:
            lines.append(f"| {s} | {v:,} | {v/total*100:.1f}% |")
    lines.append(f"| **合计** | **{sum(pos.values()):,}** | **100%** |")
    lines.append("")
    lines.append("## 三、业务分类分布")
    lines.append("")
    lines.append("| 业务分类 | 数量 | 占比 | 说明 |")
    lines.append("|:---------|-----:|----:|:-----|")
    notes = {
        "总部可控(VDC内/在途)": "VDC内 + VDC→DC在途，总部真正可调配",
        "经销商端(DC在库)": "DC内，经销商前置仓",
        "经销商端已锁单": "已离开DC、已归属经销商、已锁单",
        "经销商端未锁单": "已离开DC、已归属经销商、未锁单",
        "历史直营已售车辆": "早期直营模式，有订单无 Dealer Attribute",
        "直营流程待核验": "边缘个案",
        "未进入物流链": "尚未进入VDC/DC物流体系",
    }
    for c in d.BUSINESS_CLASSES:
        v = bc.get(c, 0)
        if v:
            note = notes.get(c, "")
            lines.append(f"| {c} | {v:,} | {v/total*100:.1f}% | {note} |")

    lines.append("")
    lines.append("> **历史直营已售车辆说明**：2022 年 IM 品牌采用直营销售模式，`Attribute Dealer Date` 字段尚未启用，因此这部分车辆天然不存在 Dealer 归属事件。该批车辆高度集中于 2022 年 L7（83.2%），且 99.8% 已有完整订单与 VIN 绑定记录，属于历史流程差异，不属于当前库存。")
    lines.append("")
    lines.append("## 四、物理位置 × 业务分类 交叉")
    lines.append("")
    all_bc = [c for c in d.BUSINESS_CLASSES if any(c in row for row in cross.values())]
    lines.append("| 位置 | " + " | ".join(all_bc) + " | 合计 |")
    lines.append("|:-----|" + "|".join("---:" for _ in all_bc) + "|----:|")
    for pos_name in d.PHYSICAL_STAGES:
        row = cross.get(pos_name)
        if not row:
            continue
        vals = [row.get(c, 0) for c in all_bc]
        if sum(vals) == 0:
            continue
        lines.append("| " + pos_name + " | " + " | ".join(f"{v:,}" for v in vals) + f" | {sum(vals):,} |")
    lines.append("")
    lines.append("## 五、核心指标")
    lines.append("")
    hq = bc.get("总部可控(VDC内/在途)", 0)
    dc = bc.get("经销商端(DC在库)", 0)
    du = bc.get("经销商端未锁单", 0)
    core = r.get("国内DC在库_未开票", 0)
    lines.append(f"| 指标 | 数量 | 说明 |")
    lines.append(f"|:-----|-----:|:-----|")
    lines.append(f"| **总部可控(VDC内/在途)** | **{hq:,}** | VDC内 + VDC→DC在途 |")
    lines.append(f"| **经销商端(DC在库)** | **{dc:,}** | 物理在 DC 的全部车辆 |")
    lines.append(f"| **国内DC在库_未开票** | **{core:,}** | **核心库存监控指标**：国内DC物理库存扣除已开票车辆 |")
    lines.append(f"| **经销商端未锁单** | **{du:,}** | 经销商责任、尚未锁单 |")
    lines.append(f"| **经销商端责任合计** | **{dc+du:,}** | DC在库 + 已离店未锁单 |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 核心库存监控指标：国内DC在库_未开票")
    lines.append("")
    lines.append("**口径：** 物理位置=DC内 + bloc_name不为上汽国际/海外（剔除出口） + invoice_upload_time为空（未开票）")
    lines.append("")
    lines.append("**含义：** 国内经销商端交付中心中，已到店、未开票的实物库存，反映当前可售现车供给水平。")
    lines.append("")
    lines.append("> 注意：DC（交付中心）本质为经销商接车节点，DC内库存归属经销商端而非总部。")
    lines.append("")
    lines.append("## 六、分车型库存（国内DC在库_未开票）")
    lines.append("")
    series_map = {"LSJEL":"LS8","LSJEH":"LS9","LSJWL":"LS7","LSJWR":"LS6","LSJWT":"L6","LSJE3":"L7"}
    inv["series"] = inv["vin"].str[:5].map(series_map).fillna("其他")
    lines.append(f"{"车型":<6} {"国内DC在库_未开票":>18}")
    lines.append("  " + "-" * 28)
    for s in ['LS8','LS6','LS9','L6','LS7','L7']:
        v = len(inv[(inv['series'] == s) & (inv['is_dc_domestic_uninvoiced'] == 1)])
        lines.append(f"  {s:<4} {v:>14,}")
    lines.append("")
    lines.append("## 七、时序异常")
    lines.append("")
    exc = r.get("time_sequence_exception_count", 0)
    lines.append(f"- 时序异常记录: **{exc:,}** 条（{exc/total*100:.1f}%）")
    lines.append("- 异常类型: VDC 晚于 DC（188 条）、DC 晚于 OutDC（2,803 条）")
    lines.append("- 处理原则: 分钟级回写差异，事件已发生优先，仅标记不重分类")
    lines.append("")
    lines.append("## 八、模型架构总结")
    lines.append("")
    lines.append("```")
    lines.append(f"{total:,} VIN")
    lines.append("")
    lines.append("    ↓")
    lines.append("")
    lines.append("物流状态机")
    lines.append("（VDC → DC → Dealer）")
    lines.append("")
    lines.append("    ↓")
    lines.append("")
    lines.append("业务状态机")
    lines.append("（中央库存 / 经销商库存 / 直营历史）")
    lines.append("")
    lines.append("    ↓")
    lines.append("")
    lines.append("订单状态机")
    lines.append("（锁单 / 未锁单）")
    lines.append("")
    lines.append("    ↓")
    lines.append("")
    dc = bc.get("经销商端(DC在库)", 0)
    du = bc.get("经销商端未锁单", 0)
    lines.append(f"最终库存口径（总部可控 {hq:,} + 经销商端(DC在库) {dc:,} + 经销商端未锁单 {du:,} = {hq+dc+du:,}）")
    lines.append("```")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成交付库存分析报告")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出目录")
    args = parser.parse_args(argv)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("📖 读取数据 ...")
    inv = pd.read_parquet(INVENTORY)
    odf = pd.read_parquet(ORDER_DATA)

    print("📊 生成报告 ...")
    md = build_report(inv, odf)

    out_path = out_dir / "delivery_inventory_analysis_report.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"✅ 报告已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
