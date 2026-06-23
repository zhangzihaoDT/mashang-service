# Prompt 模块 01 — 字段可信度校验与清洗

## 用途

对第 `{batch_N}` 批 `product_list` 中的记录做字段一致性检查，识别字段错位、品牌缺失、产品名异常、型号异常。

**前提条件**：已完成 00_asset_check.prompt.md，确认 product_list 可用。

## 角色设定

你是一个汽车行业 MIIT 数据清洗分析师。你的职责是在开始业务分析前，先对 product_list 的结构化字段做可信度校验。

## 为什么需要字段清洗

- product_list 虽然总体可用，但部分记录存在 enterprise_name / brand / product_name / product_model 字段错位。
- Promptbuilder 不应无条件信任结构化字段，每次分析前应先执行字段可信度检查。
- 对字段错位、品牌缺失、产品名异常、型号异常的记录，要降级为低置信度。
- 对重点品牌（watchlist 内的品牌），应回看 extracted text 原文确认。
- **不要覆盖原始数据**，只输出清洗建议。

## 适用输入

- `product_list/batch_{N}_product_list.json`（records 数组）
- `extracted/text/batch_{N}/{attachment1}.txt`（附件 1 原始文本）
- `configs/miit_new_car_watchlist.csv`

## 检查规则

1. `enterprise_name` 应以 `公司` / `厂` / `集团` / `有限` 等企业后缀结尾。如果不满足，标记 `field_shift`。
2. `brand` 应为品牌简称（通常 <= 10 个字符）。如果过于异常（如纯数字、纯英文缩写过长），标记 `field_shift`。
3. `product_name` 应包含 `车` / `轿车` / `客车` / `乘用车` / `货车` / `专用车` 等产品关键词。如果为纯数字或明显异常，标记 `suspicious_product_name`。
4. `product_model` 应符合 `大写字母+数字` 的型号模式。如果为纯中文或纯数字，标记 `suspicious_model`。
5. 如果 `enterprise_name` 字段的值看起来像产品名/品牌名/价格/序号（如"79"、"纯电动轿车"），标记 `field_shift`。
6. 如果 `brand` 字段为空或明显异常，标记 `missing_brand`。
7. 如果 watchlist 关键词出现在错误的字段中（如小鹏出现在 `enterprise_name` 但 `brand` 字段是其他值），标记 `watchlist_keyword_mismatch`。
8. 如果所有字段均符合预期，标记 `ok`。
9. 如果不确定，标记 `uncertain`。

## issue_type 可选值

| 类型 | 含义 |
|------|------|
| `field_shift` | 字段错位（如 enterprise_name 和 product_model 互换了） |
| `missing_brand` | 品牌字段为空或明显异常 |
| `suspicious_product_name` | 产品名异常（如为纯数字、过短、不包含车辆关键词） |
| `suspicious_model` | 型号异常（如为纯中文、过短、不符合字母+数字模式） |
| `watchlist_keyword_mismatch` | watchlist 关键词出现在错误的字段中 |
| `ok` | 字段正常，无需清洗 |
| `uncertain` | 不确定 |

## 输出字段

| 字段 | 说明 |
|------|------|
| original_record | 原始记录关键字段（enterprise_name, brand, product_name, product_model） |
| cleaned_enterprise_name | 清洗建议的企业名称 |
| cleaned_brand | 清洗建议的品牌 |
| cleaned_product_name | 清洗建议的产品名称 |
| cleaned_product_model | 清洗建议的产品型号 |
| issue_type | 问题类型 |
| confidence | high / medium / low |
| need_raw_text_check | 是否需要回看 extracted text（true / false） |
| reason | 判断理由 |

## 输出表格示例

| original_record | cleaned_enterprise | cleaned_brand | cleaned_product | cleaned_model | issue_type | confidence | need_raw_text_check | reason |
|-----------------|--------------------|---------------|----------------|---------------|------------|------------|---------------------|--------|
| {enterprise_name: "79", brand: "比亚迪牌", product_name: "79", product_model: "比亚迪汽车工业有限公司"} | 比亚迪汽车工业有限公司 | 比亚迪 | 纯电动轿车 | BYD7001 | field_shift | low | true | enterprise_name 为序号"79"，product_model 为企业名"比亚迪汽车工业有限公司"，字段错位 |
| {enterprise_name: "上海汽车集团股份有限公司", brand: "智己", product_name: "插电式增程混合动力运动型乘用车", product_model: "CSA6492"} | 上海汽车集团股份有限公司 | 智己 | 插电式增程混合动力运动型乘用车 | CSA6492 | ok | high | false | 所有字段均符合预期 |
| {enterprise_name: "纯电动仓栅式货车", brand: "", product_name: "纯电动仓栅式货车", product_model: "比亚迪汽车工业有限公司"} | 比亚迪汽车工业有限公司 | 比亚迪 | 纯电动仓栅式货车 | BYD5040CCY | field_shift | low | true | enterprise_name 为产品名，brand 为空，product_model 为企业名 |

## Prompt 模板

```
请对以下 product_list 记录做字段一致性检查。

## product_list JSON 的 records 数组：
{将 product_list JSON 的 records 数组粘贴于此}

## watchlist 品牌：
智己, 理想, 问界, 小米, 蔚来, 小鹏, 极氪, 阿维塔, 深蓝, 零跑, 腾势, 方程豹, 比亚迪, 特斯拉

## 检查规则：
1. enterprise_name 应以"公司/厂/集团/有限"等企业后缀结尾
2. brand 应为企业简称或品牌名（长度通常 <= 10）
3. product_name 应包含"车"、"轿车"、"客车"、"乘用车"、"货车"等产品关键词
4. product_model 应符合型号模式：大写字母+数字组合
5. 如果 enterprise_name 字段的值看起来像价格/序号/品牌名，标记 field_shift
6. 如果 product_name 字段的值为纯数字，标记 suspicious_product_name
7. 如果 brand 为空或明显异常，标记 missing_brand
8. 如果 watchlist 关键词出现在错误的字段中，标记 watchlist_keyword_mismatch

## issue_type 可选值：
field_shift, missing_brand, suspicious_product_name, suspicious_model, watchlist_keyword_mismatch, ok, uncertain

## 输出格式：
Markdown 表格，包含以下列：
original_record, cleaned_enterprise_name, cleaned_brand, cleaned_product_name, cleaned_product_model, issue_type, confidence, need_raw_text_check, reason

## 关键要求：
1. 不要覆盖原始数据，只输出清洗建议
2. 对低置信度记录必须标记 need_raw_text_check=true
3. 对 watchlist 内品牌（智己、比亚迪、小鹏、问界等），如果字段疑似异常，必须回看 extracted text
4. 字段清洗是后续所有分析的前置步骤
```

## 字段对齐质量判断速查

| 条件 | 结论 |
|------|------|
| `enterprise_name` 以 `公司/厂/集团/有限` 结尾 | 企业名字段大概率正确 |
| `brand` 为已知品牌名（长度 <= 10） | 品牌字段大概率正确 |
| `product_name` 包含 `车/轿车/客车/乘用车/货车` | 产品名字段大概率正确 |
| `product_model` 匹配 `大写字母+数字` 模式 | 型号字段大概率正确 |
| 上述任一项不符合 | 可能存在字段偏移，需回看 extracted text |
