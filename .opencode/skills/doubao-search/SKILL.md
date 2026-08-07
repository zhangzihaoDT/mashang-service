---
name: doubao-search
description: 通过豆包/火山引擎 Global Search 搜索公开网页。用于需要当前外部信息、信源发现、事实核验、近期动态或更广泛的网络研究时。支持迭代式与多查询研究。搜索是底层检索原语，查询策略由 Agent 自行决定。
compatibility: opencode
metadata:
  provider: volcengine
---

# Doubao Web Search

当需要本地仓库之外的信息时使用本技能。

## 职责边界

`scripts/search.py` 是一个**底层检索原语**，只负责 API 调用与结果归一化，不负责"怎么研究"。

**你（Agent）负责：**

1. 理解用户的实际问题
2. 决定是否需要联网搜索
3. 构造有效的搜索查询（不要机械地搜索用户原句，可构造更好的 query）
4. 将宽泛问题拆解为多个查询（`-q` 可重复）
5. 审阅返回文档
6. 证据不足时自己 refine / 再搜索
7. 去重并综合证据
8. 区分事实与推断

**本技能不包含**（这些属于 auto_launch 业务层，不要迁移进来）：
- compile_intent / intent 分类
- query_profiles / search_templates（预算、模板）
- 品牌侦察 / 事件映射
- fact_store / normalize / audit
- 固定 budget plan

## 搜索

```bash
python3 .opencode/skills/doubao-search/scripts/search.py \
  --query "QUERY"
```

控制结果数：

```bash
python3 .opencode/skills/doubao-search/scripts/search.py \
  --query "QUERY" \
  --limit 10
```

多查询 fan-out（一次 Bash 调用发多个 query）：

```bash
python3 .opencode/skills/doubao-search/scripts/search.py \
  --query "query one" \
  --query "query two" \
  --query "query three"
```

强制刷新（绕过 24h 缓存，适用于"今天刚发布"类场景）：

```bash
python3 .opencode/skills/doubao-search/scripts/search.py \
  --query "QUERY" \
  --refresh
```

参数一览：

| 参数 | 默认 | 说明 |
|------|------|------|
| `-q / --query` | 必填 | 可重复，实现 query fan-out |
| `--limit` | 10 | 每个查询返回结果数 |
| `--snippet-length` | 500 | 摘要长度（字符） |
| `--timeout` | 30 | 请求超时（秒） |
| `--retries` | 3 | 失败重试次数 |
| `--cache-ttl` | 86400 | 缓存有效期（秒），默认 24h |
| `--refresh` | off | 忽略缓存强制请求 |

## 研究策略

- **简单事实问题**：从一个聚焦 query 开始。
- **广泛研究**：
  1. 搜索主问题
  2. 识别缺失维度
  3. 发起针对性后续查询
  4. 优先一手/权威信源
  5. 涉及时效时核对日期
  6. **一旦额外查询不太可能改变答案，就停止**——不要用固定次数
- 搜索预算由**任务复杂度**决定（Agent 推理），不由 YAML/profile 预先规定。

## 输出

脚本返回 JSON：

```json
{
  "searches": [
    {
      "query": "...",
      "cached": true,
      "results": [
        {
          "title": "...",
          "url": "...",
          "snippet": "...",
          "source": "...",
          "publish_time": "...",
          "rank": 1
        }
      ]
    }
  ]
}
```

评估证据质量时，使用 `url`、`source`、`publish_time` 字段：
- 优先权威一手信源（官方/上市公司公告/政府文件）
- 核对发布日期判断时效
- 区分"公开报道实锤"与"行业推断"（如供应链推演需标注，不能当事实）

## 环境变量

凭据从仓库根目录 `.env` 读取（不写入 SKILL.md 或脚本文件）：

| 变量 | 用途 |
|------|------|
| `DOUBAO_SEARCH_GLOBAL_API_KEY` | API Key（Bearer） |
| `VOLC_SEARCH_BASE_URL` | API 基址 |

## 跨仓库复用

如需所有仓库共享本能力，将目录从项目级迁移到全局：

```bash
mv .opencode/skills/doubao-search ~/.config/opencode/skills/doubao-search
```

OpenCode 同时支持项目级与全局 Skill；现阶段放在项目 `.opencode/skills/`。
