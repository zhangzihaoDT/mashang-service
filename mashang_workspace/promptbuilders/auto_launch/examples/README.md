# Auto Launch Examples

## 目录结构

| 文件 | 职责 |
|------|------|
| `generate_golden_cases.py` | 生成标准 Prompt 样例（Golden Prompt Cases） |
| `validate_ai_response.py` | 验证 AI 返回结果是否符合 evidence schema 和输出结构要求 |
| `fixtures/` | synthetic fixture 存放目录 |
| `README.md` | 本文件 |

## validate_ai_response.py

验证 AI 搜索返回的 raw markdown 是否符合 auto_launch 的 evidence schema 和输出结构要求。

### 用法

```bash
# synthetic fixture 验证
make validate-auto-launch-ai-response

# 或手动指定真实 AI 返回结果
python mashang_workspace/promptbuilders/auto_launch/examples/validate_ai_response.py \
  --case-name my_case \
  --raw-file mashang_workspace/outputs/auto_launch/ai_response_examples/my_response.raw.md \
  --prompt-file mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
  --output mashang_workspace/outputs/auto_launch/ai_response_examples/my_response.validation.json
```

### 检查项

| 检查项 | 说明 |
|--------|------|
| JSON 区块 | 是否包含 JSON 代码块 |
| Markdown 简报 | 是否包含结构化简报 |
| evidence | 是否包含证据引用 |
| source_url | 是否包含来源 URL |
| publish_time | 是否包含发布日期信息 |
| confidence | 是否包含可信度标记 |
| unknown / 无法确认 | 是否对不确定信息做了标注 |
| event_model | 是否提及事件车型 |
| our_model（impact case） | 影响分析模式下是否提及本品车型 |
| our_model 不在 competitors | impact case 下 our_model 不得出现在竞品中 |
| event_model 不在 competitors | event_model 不得出现在竞品中 |
| competitor_context | 是否提及至少 1 个非 role model 的竞品 |
| 影响判断维度 | 是否覆盖价格、空间、续航、智驾、品牌等维度 |
| evidence 字段覆盖率 | 11 个关键 evidence 字段的覆盖情况 |

### 合成样例 vs 真实样例

| 类型 | 文件 | 用途 |
|------|------|------|
| **synthetic fixture** | `examples/fixtures/sample_response.synthetic.raw.md` | 脚本 smoke test，验证 validate_ai_response.py 能跑通 |
| **real fixture** | `outputs/auto_launch/ai_response_examples/*.raw.md` | 验证 Prompt 对 AI 搜索结果的约束力，不强制提交 |

### 使用真实 AI 返回结果

1. 打开对应的 Golden Prompt 文件，复制全部内容：

   ```bash
   # 以 byd_datang_ev_launch_7d_vs_ls8 为例
   cat mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md
   ```

2. 将内容粘贴到 DeepSeek / ChatGPT 的搜索对话中。

3. 等待 AI 搜索完成后，将完整返回结果（含 JSON + Markdown 简报）保存为：

   ```bash
   mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md
   ```

4. 运行验证：

   ```bash
   make validate-auto-launch-byd-datang-fixture
   ```

   或手动指定：

   ```bash
   make validate-auto-launch-ai-response \
     CASE_NAME=byd_datang_ev_launch_7d_vs_ls8 \
     RAW_FILE=mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.raw.md \
     PROMPT_FILE=mashang_workspace/outputs/auto_launch/prompts/examples/byd_datang_ev_launch_7d_vs_ls8.md \
     OUTPUT=mashang_workspace/outputs/auto_launch/ai_response_examples/byd_datang_ev_launch_7d_vs_ls8.validation.json
   ```

5. 如 raw.md 不存在，命令会给出清晰的步骤提示。
