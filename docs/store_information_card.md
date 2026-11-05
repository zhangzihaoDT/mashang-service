# 门店信息手卡与全国分布

Canonical 入口：`workspace/business_scripts/store_information_card.py`。
生成 PNG 手卡、标准 Result Contract JSON、可审计的全国门店 CSV。每张手卡包含下发线索与用户车锁单两个等宽频数直方图，以及本店值、全国分位数、中位数和低于/同值/高于本店的门店数。

```bash
.venv/bin/python workspace/business_scripts/store_information_card.py 深圳kkmall 深圳壹方城 --as-of 2026-11-01 --output workspace/outputs/reports/store_cards_distribution_20261102
# 默认截至上海时区昨天，近7个完整日；JSON模式只分析，不生成PNG。
.venv/bin/python workspace/business_scripts/store_information_card.py --store 深圳壹方城 --window-days 7 --format json
```

## 全国样本（active_store 固定算子）

- 直接消费 `shared/operators/active_store.py::get_active_store_names`。原计数算子 `_calc_active_store_count` 同样消费此名单，行为不变。
- 统计日 D 的名单：订单创建日在 `[D-29, D]` 的原始 `store_name`，且该名称在订单表中的最早 `store_create_date <= D`；建店日期缺失不纳入。订单创建时间遵循算子 `order_create_date` 优先、`order_create_time` 补缺规则。
- 活动判断使用全部订单类型，不要求有锁单；线索、用户车锁单则计算手卡指标窗口（默认近7日）。活动窗口固定30日，不随 `--window-days` 改变。
- 分母按原始 `store_name` 去重，与固定算子计数完全一致。不再用主数据“开业”状态准入，不要求在职主理，不另行剔除交付/售后、海外、总部等记录，也不合并档期别名。算子数据本身的别名和虚拟门店局限在卡面注明。
- code / Bloc 用于关联门店身份，不改变算子名单；原始名称精确命中可直接关联指标。名称不一致时仅接受唯一code对应；同code对应多个算子名称时阻断输出，避免重复分摊。
- 未登记主数据但属于算子名单的门店仍在分母内，JSON audit.active_store.unresolved_identities 明确列出；名单外记录进入排除审计。
- 近7日无指标记录的在营门店仍计0，不因零锁单/零线索删除样本。
- 主体内排名同样使用上述在营名单，档案主数据仍为当前快照。

## 指标与分位数

- 线索：`store_daily_leads.csv` 的门店×日下发线索求和；禁止重复门店×日期记录。
- 锁单：`order_data.parquet`，`order_type=用户车`，按 `lock_time` 过滤半开窗口，按门店聚合后去重 `order_number`。
- 分位数用并列中点法：`100 × (低于本店的门店数 + 0.5 × 等于本店的门店数) / N`，同值数含本店。所有值相同时分位数为P50。它不是“严格超过多少比例门店”，也不是名次除以门店数。
- JSON 同时保留并列区间上下沿、低于/同值/高于计数、竞争排名以及等宽直方图边界与频数。
- 直方图包含完整长尾和零值，最多20个等宽整数箱；分位数从原始门店值计算，不用分箱近似。本店用橙色虚线定位，横轴为指标量、纵轴为门店频数。
- 主理及主体档案复用 `store_dealer_profile.py`；主体内排名从同一国内样本重算，车系分布使用同窗口用户车锁单，不输出其存在跨窗口口径问题的CM3小订/线索比。

## 产物

`<门店全名>_门店信息手卡.png`、`store_information_card.json`、`national_store_population.csv`，默认落在 `workspace/outputs/reports/store_information_cards/`。

## 主理名册来源与清洗

`dataset/主理信息表-全.csv` 保留原始全量名册；通过以下入口生成手卡消费的规范在职表 `dataset/主理信息表.csv`：

```bash
.venv/bin/python dataset/updater/store_daily_zhuli_to_csv.py --roster-input dataset/主理信息表-全.csv --dry-run
.venv/bin/python dataset/updater/store_daily_zhuli_to_csv.py --roster-input dataset/主理信息表-全.csv
```

规则：删除 `Unnamed: 20`，筛选 `在职状态=在职`，再按 `域账号` 去重（重复保留输入首条），最后原子写入UTF-8规范名册；缺列、在职空账号、在职人数异常过少时拒绝覆盖。计数使用域账号，不以姓名去重；同名不同账号各计一人。原全表不修改。

已有 `store_daily_zhuli_to_csv.py --with-roster` 的 Tableau 导出也执行相同清洗。手卡显示规范名册文件更新时间。门店类型仍来自独立的主理在岗统计快照，其日期不随名册导入而刷新。
