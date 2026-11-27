# CPCA 全国乘用车市场零售简报海报 Job

Job ID 为 `cpca-market-retail-poster`，注册在 [Business Job 配置](../../jobs/config/jobs_config.json)。固定组合为 V1.1 Prompt、2026-10-31 版参考图和 `opencode/gemini-nano-banana-2.1`。Prompt 和参考图每次比对 [基线指纹](../../.opencode/skills/cpca-market-retail-poster/references/production-baseline.json)。模型请求为 3:4、1K，验收原生 896×1200 输出。JPEG 解码后以相同尺寸和像素保存为 PNG。

## Fast Path 职责

| 步骤 | 执行职责 |
| --- | --- |
| 数据读取及预检 | Job 直接调用 [CPCA Loader](../../shared/loaders/cpca_briefing_loader.py)，通过 Python 完成期次选择、完整性校验、字段映射和显示格式化。业务数值、起止日、统计状态和估算标记均来自 canonical export |
| 候选图生成 | Job 将本次尝试的 `briefing.json` 路径传给 Skill 的 `render()`。Skill 只使用 `layout` 中已准备好的文字，插入冻结模板，直接发起一次固定模型请求 |
| 质量门控及交付 | Job 执行文件与模型回包校验，候选图进入 `pending_review`。本地审核员根据同一份尝试快照核对实图，批准后由 Job 发布 |

以上顺序由 Job 代码固定。注册入口直接执行 Python 进程，业务数据全程由 Python 处理，唯一的模型调用用于候选图生成。CLI 和 DSH 路由以注册 Job 为入口。相同展示数据和固定资产产生相同请求正文，尝试编号、时间戳等运行元数据不会进入请求。新提交的尝试在日志及简报执行元数据中保存 `request_sha256`。

## 调用

以下命令在 Service 根目录运行。

```bash
# 最新一期预检
.venv/bin/python -m jobs.cli --job cpca-market-retail-poster --format json

# 指定统计截止日预检
.venv/bin/python -m jobs.cli --job cpca-market-retail-poster \
  --job-param date=2026-11-15 --job-param mode=dry-run --format json

# 真实生成。省略 date 时由 Loader 决定最新一期
.venv/bin/python -m jobs.cli --job cpca-market-retail-poster \
  --job-param date=2026-11-22 --job-param mode=render --format json

# 授权一次重绘。重试同一任务时必须复用原重绘编号
redraw_id=$(.venv/bin/python -c 'import uuid; print(uuid.uuid4().hex)')
.venv/bin/python -m jobs.cli --job cpca-market-retail-poster \
  --job-param date=2026-11-22 --job-param mode=render \
  --job-param "redraw=$redraw_id" --format json
```

`render` 先运行与 `dry-run` 相同的预检。已验收产物默认复用。已有待验收、失败或未确认的提交时，普通执行返回已有结果。需要重新付费时使用新编号显式重绘。进程超时或回包不明时，先核对运行日志及账单，再决定是否授权新编号。

## Capability 契约

后续 DSH-superagent 可调用 Service 的 `jobs.adapter.run_job("cpca-market-retail-poster", params)`，或使用上面的 JSON CLI。

| 参数 | 允许值 | 默认值 |
| --- | --- | --- |
| `date` | `latest` 或有效的 `YYYY-MM-DD` 统计截止日 | `latest` |
| `mode` | `dry-run`、`render` | `dry-run` |
| `redraw` | `none` 或 32 位小写十六进制编号。重绘须指定日期和 `render` | `none` |

| 控制项 | 契约 |
| --- | --- |
| 数据权限 | 读取 `MASHANG_DATA_CPCA_BRIEFING` 指定出口或平级仓库的 `exports/cpca/briefing.v1.json` |
| 文件权限 | 写入 Service 内的正式产物目录和 `logs/production-jobs/` |
| 付费权限 | `render` 在需要发起新请求时，使用获准访问 OpenCode Console 的网络及模型凭证。凭证由现有 Skill 从 `OPENCODE_API_KEY` 或 OpenCode 配置读取。调用方须授权本次生成或重绘 |
| 并发及超时 | Service 生产文件锁保护同一工作区内的预检、生成和验收。Job 默认超时 240 秒，模型连接超时 180 秒 |
| 人工权限 | 本地审核员须具备产物写入权限，验收参数由独立本地 CLI 接收 |
| 返回产物 | `summary_json.artifacts.json` 和验收完成后的 `summary_json.artifacts.png` 为绝对路径，Job 外层收集文件存在性与大小。重绘待验收时，如返回 PNG，它指向此前已通过验收的版本 |

调用方使用 `summary_json.result.outcome` 判断业务状态。进程在完成预检、返回待验收或复用正式产物时退出 0，失败时退出非零。

| 外层状态 | `outcome` | 含义 |
| --- | --- | --- |
| `ok` | `preflight_passed`、`reused` | 预检完成或复用已验收产物 |
| `pending_review` | `pending_review` | 返回候选图、对应简报快照和 SHA-256，等待人工核对 |
| `failed` | `busy` | 当前工作区已有任务持锁 |
| `failed` | `preflight_failed`、`baseline_invalid` | 数据、区间、可绘制指标或固定资产预检失败 |
| `failed` | `model_unavailable`、`generation_failed` | 凭证、权限、余额、模型或回包失败 |
| `failed` | `submission_uncertain`、`attempt_superseded` | 提交结果未确认，或同一编号已被更新的尝试取代 |
| `failed` | `validation_failed`、`job_error` | 实物验收失败、文件完整性异常或其他运行错误 |
| `failed` / `error` | `invalid_parameters` 或外层 `error` 字段 | 日期、参数组合、白名单或 Job 注册校验失败 |
| `failed` | 外层 `error` 字段 | Job 超时且进程已终止，须以日志确认提交状态 |

`pending_review` 需要转交人工验收。调用方读取 `result.candidate_path`、`review_briefing_path`、`attempt` 和 `candidate_sha256`。遇到生成失败或提交状态不明时返回原状态，新的付费尝试须另行授权并显式使用新重绘编号。

## 验收与保存

打开 `summary_json.result.candidate_path` 指向的实际图片，对照 `review_briefing_path`。逐项核对所有显示的销量和同比（完整期为 12 项）、三个区间、标题、单位、来源、初步统计和估算说明。月首只显示最新区间，缺失项留空或省略。检查首卡单边框、标签和分隔线对齐、汽车和叶片图标、参考图风格及可读性。完整标准见 [Skill 的验收表](../../.opencode/skills/cpca-market-retail-poster/references/generation-and-review.md#视觉核验)。

核对后，使用返回的期次、`attempt` 和 `candidate_sha256` 记录结果。两种决定分别为 `approve` 和 `reject`。

```bash
.venv/bin/python -m workspace.business_scripts.cpca_market_retail_poster \
  --date YYYY-MM-DD --review approve --attempt "$attempt" \
  --sha256 "$candidate_sha256" --note '填写实际数据和视觉核验结果'
```

正式路径为 `workspace/outputs/charts/cpca_market_retail_poster/YYYY-MM-DD/`。`briefing.json` 保存原始 `business`、canonical `export` 版本、实际待排版字段 `layout` 和独立 `execution` 元数据。批准后发布 `poster.png`，消费者可用 JSON 中的 `execution.image_sha256` 核对图文是否属于同一版本。若写入过程被终止，同一期 `render` 可从已验收日志恢复文件。候选图、失败图片及运行记录保存在 `logs/production-jobs/cpca-market-retail-poster/`，旧实验在 `workspace/outputs/archive_assets/cpca_market_retail_poster/`。

## Fast Path 离线验收

- 对当前 canonical export 的 108 个期次比对原始业务字段、显示字段及完整 V1.1 请求正文。所有已展示值与来源一致，重构前后请求逐字节相同。
- 使用本地 HTTP 桩捕获实际客户端请求。重绘编号、出口时间戳和字段顺序变化后，请求正文一致。模拟尺寸错误返回 `validation_failed`，复跑复用失败记录。
- 已驳回的原始实图保持归档，正式目录没有海报。离线用例核验了待验收、人工驳回及保护已有正式产物的逻辑。本轮付费请求数为零。

## 首次部署验收

- 最新期 `2026-11-22` 和历史期 `2026-11-15` 的 dry-run 均准备三段数据。
- 月首期 `2026-11-08` 与缺少累计段的 `2026-04-06` 仅准备最新区间。
- 真正的模型请求只发起一次，耗时 45.0 秒，费用 0.0441645 美元。逐项打开原图核对，六项销量和六项同比 12/12 正确，视觉布局与原生尺寸通过。「当年累计」绘制为 11 月 1 日至 11 月 22 日，正确区间为 1 月 1 日至 11 月 22 日，实物验收驳回。
- 重复执行返回同一 `validation_failed`，正式路径仅有 `briefing.json`。回归用例以桩响应覆盖模型不可用、重复提交、JPEG 转码、验收拒绝和发布恢复。
