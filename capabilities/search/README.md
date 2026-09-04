# capabilities/search — Search Base Capability

## 能力定位

**网页搜索的领域无关底层原语**（当前 provider：豆包/火山 Global Search）。
只负责：env 读取、API 请求 / retry / timeout、可选本地缓存、文档归一化、multi-query。

不负责"怎么研究"——查询策略、是否搜索、如何 refine、证据评估由调用方（Agent / 业务层）决定。

## namespace 与入口

- Python: `from capabilities.search.search_service import search, search_multi`
  - `search(SearchRequest) -> SearchResponse`
  - `search_multi(queries, **kw) -> list[SearchResponse]`：单条失败不中断。
- CLI: `python -m capabilities.search.search_service -q "..." [-q ...] [--limit N] [--refresh] [--provider doubao_global|mock]`

## providers

| provider | 说明 |
|----------|------|
| `doubao_global` | 真实：`{VOLC_SEARCH_BASE_URL}/search_api/global_search`，Bearer auth，429/5xx 可重试、其余 4xx fail fast，退避 2/4/8s，可选 24h 缓存 |
| `mock` | 离线桩，返回样例结果，无网络/密钥 |

## env 依赖

| 变量 | 说明 |
|------|------|
| `DOUBAO_SEARCH_GLOBAL_API_KEY` | 搜索 API key（`doubao_global` 必需） |
| `VOLC_SEARCH_BASE_URL` | 搜索 API base URL（`doubao_global` 必需） |

缺 env 时返回 `status="error"` + 明确信息（不抛异常）；`mock` 无此限制。

## outputs / 缓存

- 默认缓存目录：仓库 `outputs/search/cache/`（`SearchRequest.cache_dir` / CLI 可覆盖），已 gitignore（可重建）。
- cache key = sha256(provider:query:limit:snippet_length)；`refresh=True` 绕过缓存；`use_cache=False` 禁用缓存（library 场景由调用方自行缓存）。

## tests

- 随包测试：`capabilities/search/tests/`（snippet 归一、retry/fail-fast、缓存命中与刷新、multi-query 隔离、mock、缺 env），离线全绿。
- 已纳入 `make test` / `make ci` 门禁。

## 适用 / 不适用

- 适用：联网搜索原语、信源发现、事实核验、近期动态检索、多查询 fan-out。
- 不适用（not for / 边界）：
  - **查询策略与研究编排**：intent 编译、query_profile/模板、source 审计、证据链评估（auto_launch `search_agent_v2` / skill 层）。
  - **不同搜索 provider**：如 `open.feedcoopapi.com/.../web_search`（cpca 早源监控在用）需按 provider 另加，不并入本 provider。
  - 搜索结果的业务解读/报告生成。

## 消费方记录

| 消费方 | 用途 | 状态 |
|--------|------|------|
| `.opencode/skills/doubao-search/` | 豆包 Global Search 检索（skill 薄壳） | ✅ 已迁移 |
| `auto_launch/src/volc_search_client.py` | Auto Launch 搜索管线客户端（兼容薄封装） | ✅ 已迁移 |

## 历史沿革

- 收敛前：同一 Global Search 原语在两处重复实现——`doubao-search` skill `scripts/search.py` 与 `auto_launch/src/volc_search_client.py`。
- 2026-09 按 Base Capabilities 规划新增 `capabilities/search`；两份实现收敛为能力 + 消费方薄封装（skill 薄壳保留历史命令/输出形状；auto_launch 保留对外 envelope，上层缓存与业务编排不动）。
