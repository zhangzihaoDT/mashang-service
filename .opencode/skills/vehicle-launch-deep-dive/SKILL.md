---
name: vehicle-launch-deep-dive
version: "1.1"
scope: new_vehicle_launch_deep_dive
description: 新车上市深度研究 Skill。以目标代际 vs 历史对标代际的「等生命周期窗口」比较为主线，完成锁单表现、预售转化、区域网络、产品客群、订单质量、增长动能的数据叙事报告；内置口径纪律、证据分级、可视化规范与可复现性契约。
---

# vehicle-launch-deep-dive v1.1

## 能力定位

给一个**新上市代际**（如 LS8Neo、CM3）和一个或多个**历史对标代际**（如 CM3、LS8），在**各自上市后相同天数**的窗口内做同口径比较，回答四件事：

1. 卖得怎么样（累计/日增/边际差异）
2. 差异从哪来（预售池、来源结构、区域、网络、产品、客群）
3. 差异落在哪（结构定位与客群画像）
4. 意味着什么（订单质量、剩余动能、可验证假设）

产出：HTML 数据叙事报告 + 口径说明 + 数据表 + 可复现入口。

## 触发场景

用户说类似下面的话时使用：

- 「做一次 XX 新车上市深度研究 / 上市第 N 天研究」
- 「XX 和 YY、ZZ 在上市后同样天数内比一比」
- 「分析 XX 上市后的锁单表现、差异来源、区域与客群」
- 「给 XX 出一份上市复盘报告」

不适用：单日锁单查询（用 `daily_lock_count.py`）、纯预售对比（用 `presale_cumulative_order_compare.py`）、无对标代际的单车型描述。

## 输入参数（全部动态传入，禁止硬编码）

| 参数 | 说明 | 示例 |
|---|---|---|
| `gen` | 目标代际键（以 `business_definition.json` 为准，非展示名） | `LS8Neo` |
| `benchmarks` | 一个或多个对标代际键，**各自独立成基准** | `CM3 LS8` |
| `as_of` | 数据观察截止日（T−1，最后完整观察日） | `2026-11-09` |
| `context_days` | Q1 参考延长线天数，只展示形状、不参与差异计算 | `30` |
| `format` | `terminal` / `json` / `html` / `all` | `all` |
| `output` | 产物根目录 | `workspace/outputs` |

**代际键解析**：先精确匹配 `time_periods` 的键，再忽略大小写匹配，最后匹配 `monitor.series_labels`。解析失败要报错并列出可用键，**不得**用字符串包含关系猜。

## 执行入口

```bash
# 完整产物（HTML + 口径说明 + 数据表 + Result Contract）
python workspace/research_scripts/launch_deep_dive.py \
  --gen <GEN> --benchmarks <B1> [B2] --as-of <YYYY-MM-DD> \
  --format all --export-charts

# 快速核对数字（不渲染报告）
python workspace/research_scripts/launch_deep_dive.py \
  --gen <GEN> --benchmarks <B1> <B2> --as-of <YYYY-MM-DD> --format terminal
```

产物：

```
workspace/outputs/reports/<GEN>_上市第<N>天深度研究.html
workspace/outputs/reports/<GEN>_数据口径与差异计算说明.md
workspace/outputs/tables/launch_deep_dive/<GEN>_D<N>/   # 10 张 CSV + metrics.json + result_contract.json
workspace/outputs/charts/<GEN>_D<N>_*.png               # 需 --export-charts
```

## 执行步骤

### Step 0　前置审计（不可跳过）

1. 读 `shared/schema/business_definition.json`：
   - `time_periods.{gen}.end` → 上市日（**不得**从 `lock_time` 最小值推断）
   - `series_group_logic` → 代际归属规则（注意 LS8 / LS8Neo 这类父子重叠，靠 priority 裁决）
   - `model_series_mapping` / `monitor.pk_series_by_generation` → 需要竞争 PK 时的 series 映射
2. 检查数据新鲜度：`order_data.parquet` 的 `lock_time` 最大值必须 ≥ `as_of`；不足则**先告知用户**，不得用更早的日期静默替代。
3. 核对零售口径：`order_type ∈ {用户车}`，剔除 `flag_test_orders`（总部主理店 + 非 18 位身份证）、NON_RETAIL（试驾车/大客户/员工/集团员工/经销商员工/享道/仅批售/项目/展车/海外）。
4. 窗口可行性：`N = (as_of − T0).days + 1`；若某对标代际在当时的数据不覆盖 N 天，取共同可用天数并在报告中给 `window_capped` 警告。

详见 `references/metrics.md`。

### Step 1　等窗口对比

- 三车型各自 D1–D_N 累计、日增、边际差额（`Δ(d) − Δ(d−1)`）。
- 识别「差多少、哪一天形成、何时扩大/收窄/反转」。
- **一个对标一张图**，不把多个对象塞进一张复合图。

### Step 2　差异来源

- 预售池：池规模 × 转化率二元分解（`Δ = (P₁−P₀)·r₀ + P₁·(r₁−r₀)`）。
- 锁单来源三分：预售小订转锁 / **上市当日新增小订转锁** / 直接锁单（小订在上市日 24:00 停收；晚于 24:00 的残余单列，不并入）。
- 区域：绝对差额 + 按主车体量取前 N 省（**不要按差额排序**，否则体量大但差额小的省会消失）。
- 网络：有效锁单门店数 × 单店产出；门店必须按目标代际过滤。
- 产品/客群：版本、电量、座椅、颜色、选装；跨代际只比语义可比项。

### Step 3　专题追问（按发现动态生成）

上一轮结论会自然引出下钻，常见四类：

| 触发 | 下钻动作 |
|---|---|
| 某省差额最大 | 门店数 / 单店产出 / 线索 / 城市结构 / 车型结构 |
| 某版本缺口明显 | 按电量段对齐，看差额是否由缺失档位贡献 |
| 客群差异显著 | 控制变量（同电量、同座椅、同线级）后再比 |
| 出现逆向省份 | 用同店口径对比线索与锁单，判断是需求还是承接 |

专题结论必须标注「本次数据可得」与「需要外部数据验证」。

### Step 4　证据核验

- 关键数字（份额、价格、组合占比）交付前用**独立脚本从原始 parquet 复算**一次。
- 每条结论标注：事实（可复算）/ 解释（有分解支撑）/ 假设（需验证）。
- 明确写出反证或不适用的证据。

详见 `references/evidence.md`。

### Step 5　交付

> v1.1 起，报告先产出「研究主线与章节规划」（主线判定 + 第二/三幕顺序 + 跳过项），
> 渲染器按规划呈现，不再固定 Q1→Q10 顺序；数据不可比的区块（如对标无 93kWh 档）
> 自动跳过并写明原因。

- HTML 报告：四幕结构 + 附录口径，视觉遵循 `docs/共享规范/report_visual_system.md`。
- 口径说明 Markdown：窗口、过滤、指标定义、已知限制。
- 同参数重跑必须逐字节一致（除 `generated_at`）。

---

## 可视化规范（来自实战纠偏）

1. **颜色按角色**：主色承担主对象、辅色承担对标、灰阶承担残余；强调色只做标记，不大面积填充。
2. **差额用单元格内条形图**：0 中线、按列归一、正负两侧不同色；不要只给数字让读者心算。
3. **配置分布用 100% 堆积条**：取值用原始字段名，小占比保留 1 位小数（不要显示成 0%）。
4. **顺序固定**：跨版本可对照的图，维度顺序固定（与对应表格一致），不按数值幅度重排。
5. **一图一问**：同一张图不混「占比」和「绝对额」两种口径。
6. **表格对齐**：补充表/稳健性表复用主表的行名与行序，不另起一套维度。

---

## 边界与禁止项

- 不修改 `dataset/` 原始数据；不触发数据刷新或推送。
- 不修改 `shared/schema/business_definition.json` 等正式业务定义；发现定义缺失（如版本→电量映射）时，用本地常量并在报告注明「待正式登记」。
- 缺失日期不得补零、不得插值；窗口不足必须显式说明。
- 线索/试驾数据若无目标车型维度，只能作同期渠道信号，**不得**计算客户级转化率。
- 不在报告中自造品类名；配置维度一律用 `config_attribute` 的 `Attribute` / `value` 原文。
- 不把「一线占比低」写成「更下沉」——下沉程度看三线及以下占比。

---

## 引用文件

| 文件 | 用途 |
|---|---|
| `references/method.md` | 四幕十问框架、分析树、问题裁剪与动态追问规则 |
| `references/metrics.md` | 指标口径、窗口推导、来源三分、分解公式 |
| `references/pitfalls.md` | 12 条反模式与工程陷阱（含复现性） |
| `references/evidence.md` | 证据分级、核验清单、交付前检查表 |
| `templates/report-outline.md` | HTML 报告章节骨架 |
| `templates/method-doc-outline.md` | 口径说明文档骨架 |
| `workspace/research_scripts/launch_deep_dive.py` | 计算引擎（CLI 入口） |
| `workspace/research_scripts/launch_deep_dive_report.py` | 渲染层（HTML / 口径说明 / 图表导出） |
| `docs/共享规范/report_visual_system.md` | 报告视觉系统（颜色语义、组件库） |
| `shared/schema/business_definition.json` | 上市日、代际归属、版本/电池映射 |

## 变更记录

- **v1.1（2026-11-11）**：修复同档客群空数据崩溃（按样本量判定可比，不可比则跳过并说明）；
  差额表述改为"D1 领先 X / 尾段净回吐 Y / 最终 Z"；统一「预售池待转化」与「封盘池剩余」标签并加恒等式校验；
  新增研究主线与章节规划，渲染器按规划调整第二/三幕顺序。
- v1.0（2026-11-11）：首版，四幕十问 + 固定骨架。

## 已知限制

- 竞争 PK 数据只到 series 级：LS8 与 LS8Neo 共用 `LS8`，无法拆到单车型；每周只列前 9 个竞品。
- 线索数据无车型维度，且部分门店（总部孵化店）承载全国线上线索，按省汇总时必须剔除并说明。
- `final_payment_way`（全款/按揭）覆盖率低，不能用于购买力判断；`invoice_amount` 覆盖完整，可作价格代理。
- 门店→省份映射依赖 `store_city`，少量门店（<2%）无法匹配，需在口径说明中标注。
