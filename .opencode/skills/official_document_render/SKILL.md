---
name: official-document-render
description: 将 Markdown 文档转换为正式通知/申报材料风格的 Word、PDF 和 HTML 文件。版式参考正式通知/申报材料风格：A4、宋体正文、黑体标题、标题居中、段落首行缩进、页边距规整、页码规范、白底黑字、克制正式。
---

# official-document-render

## 能力定位

将 Markdown 文档渲染为正式通知、项目申报书、比赛材料、政府/机构申报附件风格的 Word/PDF/HTML 文件。

## 适用场景

- 项目申报书
- 比赛报名材料
- 正式通知
- 制度文件
- 正式汇报材料
- Markdown 转 Word
- Markdown 转 PDF
- 公文附件式排版

## 不适用场景

- 彩色商业报告
- PPT 风格页面
- 海报设计
- 公众号长图
- 需要大量视觉设计的品牌报告

## 默认排版风格

- A4 纵向
- 正文宋体 / Songti SC / SimSun
- 标题黑体 / Heiti SC / SimHei
- 标题居中
- 正文首行缩进 2em
- 行距 1.5—1.8
- 一级标题清晰醒目
- 页边距约 25mm
- 白底黑字
- 页码底部居中，格式 `— 1 —`
- 不添加政府红头
- 不添加发文字号
- 不添加机关落款
- 只参考正式通知/申报材料的版式气质

## 核心命令

```bash
# Python 脚本方式
python scripts/render_official_document.py \
  --input <markdown_file> \
  --output-dir <output_dir> \
  --basename <output_basename> \
  --formats html,pdf,docx \
  --max-pdf-mb 5

# Makefile 方式
make render-official-doc INPUT=<markdown_file> BASENAME=<output_basename>

# Smoke test
make render-official-doc-smoke
```

## Agent 使用步骤

当用户要求"把 md 转成正式通知/申报书/材料风格的 Word 或 PDF"时：

1. 定位输入 Markdown 文件路径
2. 确认输出目录（默认 `outputs/submission/`）
3. 如用户未指定格式，默认输出 html,pdf,docx
4. 调用 `scripts/render_official_document.py`
5. 检查生成文件是否存在
6. 检查 PDF 是否小于 5MB
7. 输出生成路径和文件大小
8. 不改写正文内容，除非用户明确要求润色

## 默认输出目录

`outputs/submission/`

## 默认文件命名

```
<文档类型>_<项目名称>_<作者或团队>.pdf
<文档类型>_<项目名称>_<作者或团队>.docx
project_application_print.html
```

## 重要约束

- 不要把个人姓名硬编码进 skill
- 不要把具体比赛申报书正文硬编码进 skill
- 不要删除原 Markdown
- 不要自动添加政府红头、发文字号、机关落款
- 不要做成彩色商业报告或 PPT 风格
- 不要泄露敏感信息
- 生成正式申报材料时，优先控制 PDF 在 5MB 以内

## 引用文件

| 文件 | 用途 |
|------|------|
| `scripts/render_official_document.py` | 核心渲染脚本 |
| `scripts/smoke_test_official_document_render.py` | Smoke test |
| `.opencode/skills/official_document_render/README.md` | 人类开发者文档 |
| `.opencode/skills/official_document_render/templates/official_print.css` | 正式排版 CSS 模板 |
| `.opencode/skills/official_document_render/examples/project_application_sample.md` | 示例 Markdown |
