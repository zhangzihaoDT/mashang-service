# 智己汽车官方指导价获取记录

> 目标：从智己汽车官方渠道获取各车型起步价（最低配版本价格）
> 日期：2026-07-31

## 使用工具

| 工具 | 用途 | 命令/方式 |
|------|------|----------|
| `auto_launch.cli search` | 豆包搜索召回相关网页 | `python3 -m auto_launch.cli search --request "..." --live --mode model_watch --query-profile deep_scan` |
| `playwright_browser` | 直接浏览官方配置器及新闻页面，提取结构化价格文本 | `page.goto()`, `page.evaluate()` 提取 `document.body.innerText` |
| `bash` + `python3` | 从搜索结果的 `normalized.json` 中筛选含官方信源的条目 | `json.load()` + 关键词过滤 |

## 浏览的网页

### 智己汽车官网

| URL | 内容 | 提取结果 |
|-----|------|---------|
| `immotors.com/website/configurator/l6?type=config` | L6 配置器（版本选择页） | 全新智己L6 Max **¥219,900**（21.99万） |
| `immotors.com/website/configurator/ls6?type=config` | LS6 配置器 | 新一代智己LS6 52 Max **¥229,900**（22.99万） |
| `immotors.com/website/configurator/ls7?type=config` | LS7 配置器 | LS7 Ultra **¥339,900**（33.99万，仅显示 Ultra 版本） |
| `immotors.com/website/configurator/l7?type=config` | L7 配置器 | L7 Max 超长续航版 **¥299,900**（29.99万） |
| `immotors.com/website/configurator/ls8?type=config` | LS8 配置器 | 版本选择页需交互，未直接显示价格 |
| `immotors.com/website/configurator/ls9?type=config` | LS9 配置器 | 同上，未直接显示价格 |
| `immotors.com/website/news?theme=dark` | 新闻中心列表页 | 展示各车型上市新闻标题及价格关键词 |
| `immotors.com/website/news_detail/234` | LS9 上市新闻详情 | **31.98万元起**，LS9 Hyper 权益价 34.98万元 |
| `immotors.com/website/ls9_detail` | LS9 车型详情页 | 产品介绍，价格信息不在文本中 |
| `immotors.com/website/ls8_detail` | LS8 车型详情页 | 同上 |

### 豆包搜索召回的相关结果

搜索 `auto_launch` 共执行 8 条 query（brand_watch 模板），召回 75 条结果，从中筛选出含官方价格信息的页面：

- `immotors.com/website/news_detail/234` — LS9 31.98万元起
- `chejiahao.m.autohome.com.cn/info/25236810` — LS8 官方指导价 26.18-31.18万，权益价 24.98万起（二手信源，用于交叉验证）
- `dealer.autohome.com.cn/2215625` — 经销商促销页：LS8 限时 24.98万元起（经销商店端，非官方一手）
- `immotors.com/website/news?theme=dark` — 新闻中心列表页确认 LS8 "24.98万元起"

## 筛选与信源优先级

### 信源分级

| 等级 | 定义 | 本任务中的信源 |
|------|------|---------------|
| **S级（一手官方）** | 官网配置器直接展示的 MSRP | L6/LS6/LS7/L7 配置器页面 |
| **A级（官方新闻）** | 官网新闻中心发布的上市新闻 | LS8/LS9 的"XX万元起" |
| **B级（权威第三方）** | 汽车之家等垂直媒体引用的官方价格 | LS8 指导价 26.18万起 |
| **C级（经销商/促销）** | 经销商端限时优惠价，非标准起步价 | 未采用 |

### 筛选规则

1. **优先采用 S 级**：配置器页面直接展示的 MSRP（`¥XXX` 格式），这是最权威的最低配价格
2. **配置器不可用的车型**（LS8/LS9）：采用 A 级官方新闻中的"XX万元起"，这是官方对外公布的起步价
3. **LS7 特殊情况**：配置器仅展示 Ultra 版本（¥339,900），未展示更低版本，标注为"当前仅显示 Ultra 版本"
4. **促销价与 MSRP 区分**：L6 页面同时展示"现车限时一口价 189,900 元起"（促销）和 MSRP ¥219,900，取 MSRP 作为官方起步价
5. **不采用**经销商端、垂直媒体推算的终端成交价

## 最终结果

| 车型 | 官方起步价（万元） | 信源等级 | 备注 |
|------|------------------|---------|------|
| L6 | 21.99 | S | 配置器「全新智己L6 Max」¥219,900 |
| LS6 | 22.99 | S | 配置器「新一代智己LS6 52 Max」¥229,900 |
| LS8 | 24.98 | A | 官网新闻「24.98万元起，智己LS8震撼上市」（权益价；指导价 26.18 万起） |
| LS9 | 31.98 | A | 官网新闻「31.98万元起，智己LS9全系标配线控转向」 |
| LS7 | 33.99 | S | 配置器「LS7 Ultra」¥339,900（仅显示 Ultra 版本，可能非最低配） |
| L7 | 29.99 | S | 配置器「L7 Max 超长续航版」¥299,900 |

## 局限性

- LS7 配置器未展示基础版本，无法确认是否有更低配版本及对应价格
- LS8/LS9 配置器需 JavaScript 交互选择版本后才能显示价格，本次未提取到配置器 MSRP，改用官方新闻发布价
- 官网配置器价格含限时优惠（如 L6 立减 ¥30,000），本记录取优惠前的 MSRP
