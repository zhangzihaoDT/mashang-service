# miit_formal/ —— MIIT Gov 正式公告 Source Archive（confirmed 层，主源）

**定位**：工信部主站（`miit.gov.cn` 装备工业一司 → **文件发布** 栏目 `/jgsj/zbys/wjfb/`）正式公告的 **source evidence + provenance**。是「道路机动车辆生产企业及产品（第N批）」的最终确认主源。

**进入 canonical 时**：`source=miit_gov, stage=confirmed`，且仅 `vehicle_category == passenger_vehicle` 进入 `data/vehicle_parameters/`。

> **MIIT formal = primary final source；EIDC formal = fallback / historical support。**
> 同批同时存在时，canonical merge 取 MIIT formal（`MIIT formal > EIDC formal > Gov proposed`）。

---

## 1. Pipeline

```
miit.gov.cn /jgsj/zbys/wjfb/（文件发布）
   ↓ 03_fetch_miit_formal_batch.py（source orchestration）
   ↓   [0] discover formal notice（按标题「道路机动车辆生产企业及产品（第N批）」）
   ↓   [1] fetch formal page + parse metadata（标题/公告号/日期/附件清单）
   ↓   [2] download attachments (.doc)   → attachments/
   ↓   [3] doc → txt (textutil，失败回退 olefile) → attachment_text_src/
   ↓   [4] eidc_parser.parse_road_products → product_list.json（source records）
   ↓   [5] write import_manifest.json（provenance）
   ↓
data/miit_formal/batch_{N}/
   ↓
06_build_vehicle_dataset.py（canonical 唯一入口）
   ├─ build_miit_formal_rows → confirmed 行（source=miit_gov）
   ├─ apply_formal_confirmation（strict fallback：MIIT formal > EIDC formal；
   │    Gov variant 保留完整申报型号，formal 基码只补缺、不覆盖；一条 base 确认多个 variant）
   ├─ merge_rows_by_key（exact-key dedup：同 vehicle_record_id 的多 confirmed 源）
   └─ data/vehicle_parameters/product_master + vehicle_parameter
```

### 附件同构复用

MIIT 正式公告附件与 EIDC 附件**同源**（同一 `miit.gov.cn/cms_files/.../道路机动车辆生产企业及产品（第N批）.doc`），
列结构一致，**解析层完全复用** `eidc_parser.parse_road_products`；
`miit_formal_source.py` 只负责 gov 栏目的发现/页面/元数据。

---

## 2. 批次目录结构（与 `data/eidc/batch_{N}/` 同构）

```
miit_formal/
└── batch_{N}/
    ├── import_manifest.json    ← provenance：source=miit_gov / stage=confirmed /
    │                             announcement_no / publish_date / vehicle_tax_batch /
    │                             purchase_tax_batch / 附件 sha256 / fetch_mode=gov_formal
    ├── product_list.json       ← source records（`*_raw` contract + source_section）
    ├── raw_metadata.json       ← 公告元数据（标题/公告号/日期/附件清单）
    ├── attachment_text_src/    ← 附件 txt（附件1 road / 附件2 车船税 / 附件3 购置税）
    ├── attachments/            ← 原始 .doc
    └── raw_detail.html         ← 原始公告页
```

### product_list.json（source record contract）

与 EIDC 相同（由 `eidc_parser.parse_road_products` 产出）：

```json
{
  "batch_no": "409",
  "manufacturer_raw": "小米汽车科技有限公司",
  "catalog_no_raw": "217",
  "brand_raw": "小米牌",
  "product_name_raw": "插电式增程混合动力多用途乘用车",
  "model_code_raw": "XMA6500",
  "vehicle_type_raw": "插电式增程混合动力多用途乘用车",
  "source_section": "一、汽车生产企业"
}
```

---

## 3. 命令速查

```bash
# 定位 + 抓取 + 解析 + 归档（batch 409）
python3 MIIT/scripts/03_fetch_miit_formal_batch.py --batch 409

# 只搜索定位公告页（不抓取）
python3 MIIT/scripts/03_fetch_miit_formal_batch.py --batch 409 --discover

# 显式指定公告页 URL
python3 MIIT/scripts/03_fetch_miit_formal_batch.py --batch 409 --url <URL>

# 复用缓存（网络不可用）
python3 MIIT/scripts/03_fetch_miit_formal_batch.py --batch 409 --offline

# canonical 构建（唯一入口，Gov + MIIT formal + EIDC 统一 merge）
python3 MIIT/scripts/06_build_vehicle_dataset.py
```

---

## 4. 当前覆盖

| 批次 | 公告号 | 发布日期 | 正式公告 URL | raw rows | canonical passenger |
|------|--------|----------|--------------|----------|---------------------|
| 409 | 公告2026年第21号 | 2026-08-13 | [art_4951b9…](https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_4951b91392884d049c623d59387f6172.html) | 1526 | 128（49 variant 确认 + 79 formal-only） |

> 第一轮只验证 409；401-408 历史回填留待后续（可优先找 MIIT formal，找不到再用 EIDC fallback）。
