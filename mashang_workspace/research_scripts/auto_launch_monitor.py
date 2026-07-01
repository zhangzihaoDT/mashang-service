#!/usr/bin/env python3
"""
此文件已下线。

auto_launch_monitor.py (v0.5.8) 已于 2026-07 正式下线。

旧方案是一个 3264 行的单体搜索+提取+裁判脚本，包含：
  - 火山方舟搜索 API 调用
  - Firecrawl 爬取（已不可用）
  - 正则事件提取引擎
  - LLM Judge 裁判
  - 聚合输出

该方案已由新的 Prompt workflow 架构替代：

    mashang_workspace/promptbuilders/auto_launch/

新架构：
  - ChatGPT Plan        → 定时触发 + 公开信息搜索 + 事件判断
  - promptbuilders      → Prompt 模板 + 配置 + 输出结构 + 校验
  - Volc Search Adapter → 可选搜索后端（仅保留已验证的火山搜索）
  - mashang-service     → validate / normalize / 入库 / 复盘

历史版本记录已迁入 git 历史，不再保留运行入口。

迁移的资产：
  - watchlist 配置         → promptbuilders/auto_launch/configs/ls8_competitor_watchlist.csv
  - event types 定义       → configs/event_types.yaml
  - source tiers 定义      → configs/source_tiers.yaml
  - battle fields 分类     → configs/battle_fields.yaml
  - target profiles        → configs/target_profiles.yaml
  - LLM Judge Prompt 经验  → prompts/llm_judge.md
  - 火山搜索 API 经验      → search_adapters/volc_search.md
  - validate/normalize      → examples/validate_ai_response.py, normalize_ai_response.py

命令行入口:
  make build-auto-launch-prompt        # 生成搜索 Prompt
  make validate-auto-launch-ai-response  # 验证 AI 返回
  make build-auto-launch-golden-prompts  # 生成 Golden Prompt 样例
"""
