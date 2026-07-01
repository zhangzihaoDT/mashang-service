# Volc Search Adapter — 火山方舟搜索

## 状态

✅ 已验证可用。旧 auto_launch_monitor.py（v0.5.8）中唯一成功跑通全链路的搜索后端。

## 在新架构中的角色

Volc Search 是 **可选的搜索候选信息获取后端**，不是完整 monitor 的组成部分。

它的职责：
1. 接收搜索 query（品牌 + 车型 + 事件类型 + 时间范围）
2. 调用火山方舟 Deep Search API
3. 返回候选搜索结果（title + snippet + URL + publish_date）
4. 供后续 ChatGPT Plan / Prompt + LLM 做事件判断和提取

不负责：
- 事件类型分类
- 可信度评分
- 品牌冲突检测
- 聚合输出

## API 信息

- **服务**: 火山引擎方舟 (Volcengine Ark)
- **API**: Deep Search (`https://ark.cn-beijing.volces.com/api/v3/chat/completions`)
- **模型**: `ep-xxxxxxxx` (专门的搜索模型 endpoint)
- **认证**: `VOLCENGINE_API_KEY` 或 `HUOSANFANGZHOU_API_KEY` 环境变量

## 关键字段约束

从旧 monitor 中沉淀的使用经验：

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `model` | 搜索模型 endpoint | `ep-{id}` (从火山控制台获取) |
| `messages` | system + user prompt | system 定义搜索任务，user 为搜索 query |
| `stream` | 是否流式 | `false` |
| `max_tokens` | 最大输出长度 | 4096 |
| `temperature` | 生成温度 | 0.1 (事实搜索用低温度) |
| `search_options` | 搜索配置对象 | 见下方 |

### search_options 配置

```json
{
  "search_options": {
    "enable_source": true,
    "enable_citation": true,
    "freshness": "oneMonth",
    "filter_sites": ["autohome.com.cn", "dongchedi.com", "36kr.com", "huxiu.com", "yiche.com", "xchuxing.com"]
  }
}
```

| 子字段 | 说明 | 推荐值 |
|--------|------|--------|
| `enable_source` | 返回信息来源 | `true` |
| `enable_citation` | 返回引用链接 | `true` |
| `freshness` | 搜索时间范围 | `oneDay`(日报) / `oneWeek`(周报) / `oneMonth`(月报) |
| `filter_sites` | 限定搜索源站 | 按需指定 Tier 1/2 来源域名 |

### 环境变量

```bash
# 二选一设置
export VOLCENGINE_API_KEY="your-api-key"
# 或
export HUOSANFANGZHOU_API_KEY="your-api-key"
```

## 旧经验迁移

旧 auto_launch_monitor.py 中关于 Volc Search 的经验：

1. **搜索质量与 query 构造强相关**：query 应包含品牌+车型+事件关键词+时间，避免模糊搜索
2. **filter_sites 对质量提升显著**：限定 Tier 1/2 来源可大幅减少噪声
3. **freshness 参数影响结果时效**：日报用 oneDay，周报用 oneWeek
4. **结果解析**：API 返回的消息中通常包含 `sources` 字段，列出引用的来源列表
5. **错误处理**：
   - `401` → API key 无效或过期
   - `429` → 限流，需退避重试
   - `503` → 服务暂不可用，可稍后重试
   - 超时建议 30s（旧配置）至 60s（复杂 query）

## 示例用法（概念性，非可执行代码）

```
> 当前阶段不实现完整搜索 runner。
> 如需要，后续可直接在 promptbuilder 中集成 Volc Search 作为可选前置搜索步骤。
>
> 搜索流程：
> 1. 构造 query："{品牌} {车型} {事件类型} {时间}"
> 2. 调用 Deep Search API
> 3. 提取 sources 中的候选信息
> 4. 将候选信息作为 Prompt 的上下文输入
```
