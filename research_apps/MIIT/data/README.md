# data/ —— 获取的数据 + 加工中间数据

二级目录按**内容直白命名**（里面是什么数据，就叫什么）。
车型身份 = `{batch_no}:{model_code}`（型号不假设全局唯一，见下方说明）。

```
data/
├── search_results/        P1 品牌/车型搜索结果（scan 快照，可重放）
├── vehicle_details/       P2 车型完整参数归档（{batch}_{型号}-{产品名}.md）
├── vehicle_photos/        P2 公告照片（{batch}_{型号}/ 下）
├── raw_html/              P2 原始详情页缓存（{batch}_{型号}.html）
├── vehicle_tax/           P3 车船税 doc/txt/json/md
├── vehicle_parameters/    结构化车型参数（canonical 目标层，见下）
├── wide_tables/           P4 参数宽表 csv/md
└── fetch_status/          P2 checkpoint / 抓取状态
```

加工流：**raw_html + vehicle_tax → vehicle_details → vehicle_parameters → wide_tables**

- **车型身份（canonical key）**：`vehicle_record_id = "{batch_no}:{model_code}"`。
  不假设 `model_code` 全局唯一——同一型号未来可能在不同批次再次申报（参数变更/扩展/重新申报），
  用批次号区分版本，避免历史数据被覆盖。
  对应文件名：`data/vehicle_details/{batch}_{model_code}-{产品名}.md`、`data/vehicle_photos/{batch}_{model_code}/`、`data/raw_html/{batch}_{model_code}.html`。

- **raw_html/**: 详情页原样缓存，只作抓取恢复用。
- **vehicle_details/**: 每款车型一个 `.md`（全部申报参数）+ 对应 `vehicle_photos/{batch}_{型号}/`。
- **vehicle_tax/**: 车船税原始附件（doc/txt）与结构化产物（json/md）。
- **vehicle_parameters/**: 未来 canonical 车型参数层（product_master / vehicle_parameter），
  由 P1/P2/P3 结构化后统一落这里；目前最接近的是 `wide_tables/`。
- **fetch_status/**: 任务进度 checkpoint（失败可补抓），不是正式数据。

以后接入 EIDC（另一官方源）时：`data/eidc/` → 统一落 `data/vehicle_parameters/`，形成"双源 → 单事实层"。
