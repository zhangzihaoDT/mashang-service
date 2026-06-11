# Metric Definitions — 核心指标口径

> 来源: schema/metrics.json, schema/schema.md, operators/registry.json
> 数据字典: `python scripts/data_dictionary.py`

## 计数类指标

### 锁单数 / 锁单量

- **业务含义**：用户最终确认锁定的订单数量
- **计算口径**：`count(order_number)` WHERE `lock_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`lock_time`
- **常用别名**：锁单量, 锁单, 订单锁单
- **参考脚本**：`scripts/daily_lock_count.py`
- **注意事项**：区分于"订单计数"（order_create_date），锁单以 lock_time 为准

### 交付数

- **业务含义**：已完成车辆交付的订单数
- **计算口径**：`count(order_number)` WHERE `delivery_date IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`delivery_date`

### 开票数

- **业务含义**：已完成发票上传的订单数
- **计算口径**：`count(order_number)` WHERE `invoice_upload_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`invoice_upload_time`

### 小订数

- **业务含义**：支付意向金的订单数
- **计算口径**：`count(order_number)` WHERE `intention_payment_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`intention_payment_time`

### 大定数

- **业务含义**：支付正式定金的订单数
- **计算口径**：`count(order_number)` WHERE `deposit_payment_time IS NOT NULL`
- **数据集**：`order_data.parquet`
- **时间字段**：`deposit_payment_time`

## 线索类指标

### 下发线索数

- **业务含义**：系统下发给门店/渠道的线索总数
- **计算口径**：`sum(下发线索数)`
- **数据集**：`assign_data.csv`
- **时间字段**：`Assign Time 年/月/日`
- **别名**：总线索数, 线索总数, 线索量

### 下发线索数（门店）

- **业务含义**：门店渠道收到的线索数
- **计算口径**：`sum(下发线索数 (门店))`
- **数据集**：`assign_data.csv`
- **别名**：门店线索, 门店线索数

### 门店当日锁单率

- **业务含义**：门店线索当日即锁单的比例
- **计算口径**：`下发线索当日锁单数（门店） / 下发线索数（门店）`
- **数据集**：`assign_data.csv`
- **别名**：门店锁单率, 门店线索当日锁单率

## ATP 类指标

### 平均开票价格 (ATP)

- **业务含义**：用户车订单的平均开票金额
- **计算口径**：`mean(invoice_amount)` WHERE `order_type='用户车'` AND `invoice_amount > 0`
- **数据集**：`order_data.parquet`
- **时间字段**：`invoice_upload_time`
- **别名**：开票均价, 平均开票金额, 均价
- **参考脚本**：`scripts/skills_atp_price.py`

## 算子类指标

### 在营门店数

- **业务含义**：30天滚动窗口内存在订单活动的活跃门店数
- **计算口径**：去重计数 store_name，窗口内存在订单且开店日 <= 当天
- **时间字段**：`order_create_date`

### 留存小订数

- **业务含义**：支付小订后在窗口结束时仍未退款的订单数
- **计算口径**：intention_payment_time 在预售期内，exit_time 为空或 >= 当日+1天
- **时间字段**：`intention_payment_time`

### 留存小订转化率

- **业务含义**：留存小订中最终锁单/交付的比例
- **计算口径**：留存小订中 lock_time 非空的比例

### 预测锁单数

- **业务含义**：基于成熟度曲线修正右删失后预测的最终30日锁单数
- **计算口径**：三段式: age>=30d 用原始值, 7d≤age<30d 用 lock_7÷r7, age<7d 用 0.5×avg+0.5×lock0
- **数据集**：`assign_data.csv`
- **参考脚本**：`scripts/cohort_forecast.py`, `scripts/lock_predict_backtest.py`

### 店均锁单数

- **业务含义**：每日锁单数 ÷ 在营门店数
- **计算口径**：日锁单数 / 在营门店数（30天窗口活跃门店）

### 年龄代际分布

- **业务含义**：用户年龄代际分组统计
- **分组**：00后/95后/90后/85后/80后/75后/70后/65后/60前

### 城市线级分布

- **业务含义**：城市等级分组统计
- **分组**：一线/新一线/二线/三线及以下

### 省份 TopK 占比

- **业务含义**：TopK 省份的锁单集中度
- **计算口径**：将城市映射到省份，按锁单数排序取 TopK

## 派生率指标

| 指标名称 | 分子 | 分母 | 别名 |
|----------|------|------|------|
| 门店下发线索数占比 | 下发线索数（门店） | 下发线索数 | 门店线索占比 |
| 下发线索当日试驾率 | 下发线索当日试驾数 | 下发线索数 | 当日试驾率, 试驾率 |
| 下发线索7日锁单率 | 下发线索7日锁单数 | 下发线索数 | 七日锁单率, 7日锁单率 |
| 下发线索30日锁单率 | 下发线索30日锁单数 | 下发线索数 | 三十日锁单率, 30日锁单率 |
| 门店当日锁单率 | 下发线索当日锁单数（门店） | 下发线索数（门店） | 门店锁单率 |

## 如何查看数据字段

运行以下命令获取所有数据集的字段清单：

```bash
python scripts/data_dictionary.py
python scripts/data_dictionary.py --format csv --output outputs/tables/
```
