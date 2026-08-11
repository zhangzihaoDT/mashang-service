# vehicle_parameters/ —— 结构化车型参数（canonical 目标层）

**目标**：一车型一行的规范参数事实层（product_master / vehicle_parameter），
由 P1（搜索）→ P2（归档）→ P3（车船税）结构化后统一落这里。

当前该层尚未产出（最接近的是 `data/wide_tables/` 宽表）。规划中的两张核心表：

- **product_master**：一车型一行，身份 `vehicle_record_id = {batch_no}:{model_code}` ——
  batch_no / model_code / manufacturer / brand / product_name / detail_url / publish_date / source
- **vehicle_parameter**：一车型一行，身份同上 ——
  model_code / 尺寸 / 轴距 / 整备质量 / 电池类型 / 电池供应商 / 电机功率 / 续航 / 能耗 …

> 同一 `model_code` 跨批次再次申报时，`batch_no` 不同即视为不同记录（版本），
> 便于将来识别"同一车型跨批次变化"，而不是被覆盖。

产出后，reports/ 与 Agent 统一消费这一层，不再各自去扫 vehicle_details/*.md。
