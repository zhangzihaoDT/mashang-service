# 门店信息手卡与全国分布

Canonical 入口：`mashang_workspace/business_scripts/store_information_card.py`。
生成 PNG 手卡、标准 Result Contract JSON、可审计的全国门店 CSV。每张手卡包含下发线索与用户车锁单两个等宽频数直方图，以及本店值、全国分位数、中位数和低于/同值/高于本店的门店数。

```bash
.venv/bin/python mashang_workspace/business_scripts/store_information_card.py 深圳kkmall 深圳壹方城 --as-of 2026-11-01 --output mashang_workspace/outputs/reports/store_cards_distribution_20261102
# 默认截至上海时区昨天，近7个完整日；JSON模式只分析，不生成PNG。
.venv/bin/python mashang_workspace/business_scripts/store_information_card.py --store 深圳壹方城 --window-days 7 --format json
```

## 全国样本

- 复用 `store_info_loader` 读取主数据和 code/Bloc 身份映射。范围为主数据已登记的国内开业门店，排除海外网点/海外区及空、无、全部等占位名称。
- 以完整门店名合并销售、交付、售后职能代码；同名任一职能处于开业状态，即计为一家门店。该样本包括独立交付/售后网点，不代表仅销售体验店。
- 所有已登记代码先关联同名门店，再按上述门店级准入；避免同店销售码在建、售后码开业时漏掉该店数据。
- 没有指标记录的样本门店计0；这只是无观测，不等同于核实经营无产出或停业。
- 编码未在主数据登记的线索、已登记但不属于国内开业样本的数据不计入分布，逐条进入 JSON audit.excluded。不能据此称为所有实际营业网点的普查。
- 在主数据已登记但关联冲突，或订单无法关联时，阻断输出完整全国分位数，不将关联失败悄悄计0。
- 门店主数据是当前快照。as-of 控制指标窗口和可用身份观测，不重建历史门店经营状态。主理名册日期显著标注。

## 指标与分位数

- 线索：`store_daily_leads.csv` 的门店×日下发线索求和；禁止重复门店×日期记录。
- 锁单：`order_data.parquet`，`order_type=用户车`，按 `lock_time` 过滤半开窗口，按门店聚合后去重 `order_number`。
- 分位数用并列中点法：`100 × (低于本店的门店数 + 0.5 × 等于本店的门店数) / N`，同值数含本店。所有值相同时分位数为P50。它不是“严格超过多少比例门店”，也不是名次除以门店数。
- JSON 同时保留并列区间上下沿、低于/同值/高于计数、竞争排名以及等宽直方图边界与频数。
- 直方图包含完整长尾和零值，最多20个等宽整数箱；分位数从原始门店值计算，不用分箱近似。本店用橙色虚线定位，横轴为指标量、纵轴为门店频数。
- 主理及主体档案复用 `store_dealer_profile.py`；主体内排名从同一国内样本重算，车系分布使用同窗口用户车锁单，不输出其存在跨窗口口径问题的CM3小订/线索比。

## 产物

`<门店全名>_门店信息手卡.png`、`store_information_card.json`、`national_store_population.csv`，默认落在 `mashang_workspace/outputs/reports/store_information_cards/`。

## 主理名册来源与清洗

`dataset/主理信息表-全.csv` 保留原始全量名册；通过以下入口生成手卡消费的规范在职表 `dataset/主理信息表.csv`：

```bash
.venv/bin/python dataset/updater/store_daily_zhuli_to_csv.py --roster-input dataset/主理信息表-全.csv --dry-run
.venv/bin/python dataset/updater/store_daily_zhuli_to_csv.py --roster-input dataset/主理信息表-全.csv
```

规则：删除 `Unnamed: 20`，筛选 `在职状态=在职`，再按 `域账号` 去重（重复保留输入首条），最后原子写入UTF-8规范名册；缺列、在职空账号、在职人数异常过少时拒绝覆盖。计数使用域账号，不以姓名去重；同名不同账号各计一人。原全表不修改。

已有 `store_daily_zhuli_to_csv.py --with-roster` 的 Tableau 导出也执行相同清洗。手卡显示规范名册文件更新时间。门店类型仍来自独立的主理在岗统计快照，其日期不随名册导入而刷新。
