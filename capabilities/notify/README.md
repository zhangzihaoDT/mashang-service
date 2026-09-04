# capabilities/notify — Notify Base Capability

## 能力定位

**文本 / 交互卡片 → 消息渠道推送的领域无关通知原语**（当前 provider：飞书群机器人 Webhook）。

不负责任意业务内容组装（卡片正文/章节由调用方生成）——那是业务层的职责。

## namespace 与入口

- Python: `from capabilities.notify.notify_service import notify`
  - `notify(title=..., body=..., note=..., provider_name="feishu_webhook", webhook_url=None, raw_payload=None, dry_run=False) -> NotifyResult`
  - `raw_payload`：调用方已组装好完整飞书 payload 时直接透传（逃生舱）。
- CLI: `python -m capabilities.notify.notify_service --title <t> --body <md> [--note ...] [--provider feishu_webhook|mock] [--dry-run] [--webhook url]`

## providers

- `feishu_webhook`：真实 provider（httpx POST 飞书群机器人 Webhook）。
- `mock`：离线桩，无需网络/密钥，供测试与冒烟。

## 信封 builder（schemas.py）

| 函数 | 说明 |
|------|------|
| `build_interactive_card(title, body_markdown, note=None, header_template="blue")` | 通用交互卡片信封（blue header + lark_md 正文 + 可选 note 脚注） |
| `build_text(text)` | 纯文本消息 |

富卡片（多 div/hr/note/时间戳等）由调用方用 `raw_payload` 或自行组装后交给传输层。

## env 依赖

| 变量 | 说明 |
|------|------|
| `FS_WEBHOOK_URL` | 飞书群机器人 Webhook URL（`feishu_webhook` 必需；`--webhook` / `webhook_url` 可覆盖） |

缺 URL 时 `feishu_webhook` 返回 `status="failed"` 并给出明确错误（不抛异常）；`mock` 无此限制。

## 可靠性设计

- 3 次重试，退避 2/4/8s；处理 HTTP 429 与飞书 `code=11232`（频率限制）后重试。
- `code==0` 视为成功；`dry_run=True` 只解析/打印 payload，绝不发网络请求。

## tests

- 随包测试：`capabilities/notify/tests/`，mock 离线全绿。
- 已纳入 `make test` / `make ci` 门禁。

## 适用 / 不适用

- 适用：数据看板/观察结果/简报推送飞书群、任何"发送通知"调用。
- 不适用（not for / 边界声明）：
  - **接收 / 对话 bot**：飞书收消息 + agent 路由（`mashang_runtime/feishu_bot.py` 属 legacy inbound，不并入）。
  - **Bitable / 多维表格写入**：tenant token + bitable REST 是另一原语（`skills_order_observation_daily.py` 内嵌），候选能力另行收敛。
  - **文件下载/采集**：`dataset/incoming/feishu/` 属 Browser/Capture 管道。
  - 业务卡片的内容与版式设计（留在各消费方）。

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| `mashang_workspace/runtime_scripts/monthly_sales_order_type_to_feishu.py` | 月度销量推送 | 迁移目标（阶段 B） |
| `mashang_workspace/runtime_scripts/daily_dc_inventory_change.py` | DC 库存变动推送 | 迁移目标（阶段 B） |
| `mashang_workspace/utility_scripts/skills_order_observation_daily.py` | 每日观察推送（webhook 段；Bitable 段不动） | 迁移目标（阶段 B） |
| `mashang_workspace/research_scripts/l6_m2_presale_metrics_to_feishu.py` | 预售指标推送 | 迁移目标（阶段 B） |
| `mashang_workspace/research_scripts/l6_m2_launch_lock_metrics_to_feishu.py` | 上市锁单指标推送 | 迁移目标（阶段 B） |
| `auto_launch/src/feishu_sender.py` | 竞品营销日报推送 | 迁移目标（阶段 B） |

## 历史沿革

- 收敛前：5+ 个 workspace/feature 脚本各自内嵌 `build_feishu_card` + `send_to_feishu`（requests），`auto_launch/src/feishu_sender.py` 为其一（httpx）。
- 2026-09 按 Base Capabilities 规划新增 `capabilities/notify`（传输 + 通用信封 + mock），消费方迁移按阶段 B 逐脚本进行。
