# Terminal Launcher

## 为什么有 Launcher

Auto Launch 有 15+ 个子命令，每个负责一个具体环节。对于日常使用来说，记住所有命令和参数不是必要的事情。

Launcher 把最常用的操作编排成一个交互菜单，用户不需要记住具体命令，只需要选择要做的事情，系统引导完成剩余操作。

## 启动

```bash
python -m auto_launch.cli launch
```

或别名：

```bash
python -m auto_launch.cli start
```

## 菜单

```
  1. 处理 ChatGPT Daily Run
  2. 定向搜索并写入事实库
  3. 查看事实库
  4. 生成今日简报
  5. 查看 outputs 状态
  6. 退出
```

## 功能说明

### 1. 处理 ChatGPT Daily Run

适合接收每日人工整理的营销事件摘要。

流程：

1. 输入日期（默认今天）
2. 粘贴 ChatGPT daily run 文本
3. 输入 `/done` 结束粘贴
4. 自动完成：parse → filter(keep/discard) → write facts
5. 展示 keep / discard 摘要
6. 可选生成并展示简报
7. 简报写入 `outputs/briefs/{date}.md`

### 2. 定向搜索并写入事实库

适合临时搜索某个品牌或车型的最新动态。

流程：

1. 输入搜索请求（如：看看极氪最近 7 天有什么动作）
2. 输入日期
3. 确认是否执行真实搜索（默认 no）

⚠ 默认不触发真实 API。必须用户明确选择 yes 才执行 live search。

### 3. 查看事实库

快速浏览事实库内容。

- 输入最近 N 天（默认 7）
- 可选输入品牌筛选
- 展示 facts 列表和统计（by brand / by event type）

### 4. 生成今日简报

基于 facts 生成每日简报。

- 输入最近 N 天（默认 1）
- 可选品牌筛选
- 终端展示 Markdown
- 可选写入 `outputs/briefs/{date}.md`

### 5. 查看 outputs 状态

等同于 `outputs inspect`，检查各目录的完整性和文件数量。

## 输出文件

Launcher 不新增顶层输出目录，所有产出写入既有结构：

| 产出 | 路径 |
|------|------|
| 事实 | `outputs/facts/auto_launch_facts.sqlite` |
| 简报（option 1） | `outputs/briefs/{date}.md` |
| 简报（option 4） | `outputs/briefs/{date}.md` |

## 和 run-day / demo 的区别

| 命令 | 定位 | 自动化程度 |
|------|------|-----------|
| `launch` | 交互式引导，适合日常操作 | 用户一步步操作 |
| `run-day` | 一键日更（搜索 + facts + 审计 + 简报） | 全自动 pipeline |
| `demo` | 演示（replay fixtures） | 全自动，不调 API |

高级用户仍可直接使用 `inbox` / `search` / `facts` / `brief` / `run-day` 等子命令获得更精细的控制。
