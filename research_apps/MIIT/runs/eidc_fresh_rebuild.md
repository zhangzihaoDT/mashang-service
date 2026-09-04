# EIDC 401-408 Fresh Rebuild 经验沉淀

## 概览

- **目的**：将 EIDC 401-408 从 legacy 字段错位导入，升级为 fresh rebuild（官方公告 → 全量解析 → passenger scope gate → canonical）
- **结果**：401-410 十批 canonical 统一为乘用车业务事实层，831 行，0 非乘用车
  - eidc/confirmed：401-408 全 fresh，765 行（legacy passenger 121 → fresh 536，+415）
  - miit_gov/proposed：409:49 + 410:17
- **关键产物**：`03_fetch_eidc_batch.py` / `eidc_doc_extract.py` / `validate_eidc_batch.py` / `06` scope gate
- **迁移后清理**：legacy 已删除（`legacy/` 目录 + `08_archive_eidc_legacy.py` + `08_import_eidc_history.py` + `eidc_record_adapter.py`），
  迁移记录见 `data/eidc/migration_eidc_fresh_rebuild.json`。原则：迁移成功后删除迁移态。
- **完整技术文档**：[data/eidc/README.md](../data/eidc/README.md)

## 运行数据

- 上一轮 Agent 独立工作时长：**6 小时 8 分钟**
- 覆盖：8 批 EIDC fresh fetch + 13 个 tax/purchase 附件解析 + 2 个超大 doc 提取 + canonical 重建 + reconciliation

## Lessons（按主题分组）

### 技术实现

1. **超大 doc 附件获取（olefile）**
   - 现象：textutil 对 32MB/30MB WPS 完整版目录报 "isn't in the correct format"
   - 解法：`eidc_doc_extract.py` 用 olefile 读 WordDocument 流 + FIB（fcMin/fcMac）精确切文本区（UTF-16LE）
   - 关键认识：完整版目录可达 849/777 页、解析出 12163 条（购置税26批），是常规精简版的百倍

2. **Benchmark 本身可能比 pipeline 更容易错**
   - 教训：附件定位必须用 manifest 的 `title` 关键词（`道路机动车辆` / `车船税` / `购置税`），不靠 glob 排序

3. **单批多购置税批次**
   - 402 购置税为"第二十五、二十六批"两批，manifest `purchase_tax_batch="25,26"` 逗号分隔
   - 06 的 index loader 需支持多批次合并（`_load_eidc_tax_purchase_index` 拆逗号遍历）

### 架构 / 流程

4. **Scope gate = source-record 级 existential，且必须聚合前执行**
   - 同 chassis 多车型（旅居车/商务车 + 救护车/巡逻车等）必须逐 record 分类后 gate，否则漏掉乘用变体
   - 迁移中实际触发：416→831 时新出现 5 个 multi-record chassis（如 408:JKF5030X 七条记录含旅居车变体）
   - 已落档为架构约束：`vehicle_record_builder.is_canonical_in_scope` + `classify_source_record`

5. **source_section 对第一部分混排产品不可靠**
   - 第一部分仅"一、汽车生产企业"一个一级标题，摩托车/底盘/起重机产品表共享稀疏标题，摩托车表无独立子标题
   - 分类必须靠 `vehicle_category`（产品名强规则 + 目录序号信号），`source_section` 只作 evidence

6. **目录序号格式 = 官方企业类别信号**
   - `（X）数字`（如 `(一)03`）= 专用车/改装车企业；`纯数字` = 整车企业
   - 用于分类兜底：产品名无强规则 + （X）数字 → `commercial_vehicle/special_vehicle`，减少 `other` 累积

7. **legacy 字段错位 vs fresh 全量**
   - legacy parser 只保留部分 valid records（401 的 1224 条中仅 474 条有合法型号）
   - fresh 全量解析（1585 条），passenger 121→536 是重建价值而非异常

### 验收 / 工程纪律

8. **schema_status 判断语义**
   - diff > 0（fresh 发现更多）是预期现象；只有 **legacy_only（legacy 有 fresh 没有）才算异常**，不能简单用 abs(diff)
   - `validate_eidc_batch.py` 落地此判断，8 批全 OK / 0 REVIEW

9. **Migration safety check**
   - 改 canonical 前备份 observation_id 集（old 5219 / old passenger 411），rebuild 后对比 new_only / missing_after_scope_change，先定位原因再接受数据变化
   - 本工程：0 missing，5 new_only（均为同 chassis 多车型的乘用变体重分类），无静默数据损失

10. **幂等是硬验收**
    - 06 连续重建必须 byte-identical，否则视为 bug
    - Source fetch：相同文件 + 相同 sha256 可跳过下载

## 下一轮改进

- 自动发现公告页（pageId）替代人工登记 `KNOWN_ANNOUNCEMENT`
- 超大 doc 提取集成进 09 主流程（现在是独立脚本 `eidc_doc_extract.py` 手动调用）
- 401-410 全 fresh 后，跨批次 diff 可按 `analysis_scope='in_scope'`（乘用车）母体跑
- 分类规则继续用官方信号收敛，减少 regex 新增（未来批次生僻产品名自动归入 special_vehicle）
