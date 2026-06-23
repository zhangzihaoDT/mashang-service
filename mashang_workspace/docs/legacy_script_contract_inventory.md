# Legacy Script Contract Inventory

> Generated: 2026-06-11

## 盘点

| 脚本 | 存在 | CLI | 输出格式 | Result Contract | 数据依赖 | 推荐升级方式 |
|------|:----:|:---:|:--------:|:---------------:|:---------:|-------------|
| `skills_atp_price.py` | ✅ | month, --output | Terminal + HTML | ❌ | order_data.parquet | 复用函数 |
| `atp_price_report.py` | ✅ | month, --output | Terminal(基础) | ❌ | 同 | 重写为完整 Contract |
| `lock_predict_backtest.py` | ✅ | 无参数 | Terminal + HTML | ❌ | assign_data.csv | subprocess 截取 |
| `lock_predict_backtest.py` | ✅ | --format | Terminal + JSON | ❌ | assign_data.csv | 已合并 <sup>†</sup> |

## 详情

### skills_atp_price.py — ATP 价格月报 (原脚本)

- **位置**: `mashang_workspace/runtime_scripts/skills_atp_price.py`
- **行数**: 180
- **核心逻辑**: 从 order_data.parquet 读取订单，apply_business_logic 添加 series_group，按 12 个系别分组计算 ATP
- **关键函数**: `run_atp_operator(seg_df, start, end)` → {total_orders, avg_price}
- **依赖**: `operators.atp_analysis`
- **CLI**: `python runtime_scripts/skills_atp_price.py [YYYY-MM] [--output PATH]`
- **输出**: Terminal 表格 + HTML 报告
- **Contract 状态**: ❌ 不支持

### atp_price_report.py — ATP 价格月报 (当前 wrapper)

- **位置**: `mashang_workspace/scripts/atp_price_report.py`
- **行数**: 82
- **方式**: 委派调用 `skills_atp_price.main()`
- **CLI**: `--month`, `--output`, `--format terminal/html`
- **Contract 状态**: ❌ 不支持

**升级方案**: 复用 `skills_atp_price` 中的 `run_atp_operator`/`apply_business_logic`/`_load_business_definition` 直接计算指标，构建 Result Contract。terminal 模式保持 legacy 输出。

### lock_predict_backtest.py — 锁单预测回测 (原脚本)

- **位置**: `mashang_workspace/scripts/lock_predict_backtest.py`
- **行数**: 329
- **核心逻辑**: 三段式成熟度预测 → 计算 MAE/RMSE/MAPE
- **关键指标**: MAE, RMSE, MAPE (lines 107-110), n_bt (回测天数)
- **依赖**: `operators.mature_lock_prediction`, `operators.assign_conversion`
- **CLI**: 无参数（全量运行）
- **输出**: Terminal 摘要 + HTML 报告 (Plotly)
- **Contract 状态**: ❌ 不支持

### lock_predict_backtest.py — 锁单预测回测 (已合并)

- **位置**: `mashang_workspace/research_scripts/lock_predict_backtest.py`
- **行数**: 405
- **方式**: 原生 Result Contract 支持，含 --format json/terminal
- **CLI**: `--format`, `--output`
- **Contract 状态**: ✅ 完整 Contract

**注意**: `lock_predict_backtest_cli.py` 已合并至此文件，不再单独存在。

## 运行风险

| 风险 | 说明 |
|------|------|
| ATP 字段口径 | `invoice_amount` 过滤条件 `order_type='用户车'`，如果有口径变化需保持一致 |
| 预测耗时 | lock_predict_backtest.py 全量运行约 2-3 分钟，subprocess 需设置合理 timeout |
| JSON 体积 | ATP 报告含 12 个 segment 的维度数据，contract 可能较大 |
| numeric 校验 | 新增 numeric cases 的真实 dataset 依赖可能影响 CI-safe |
