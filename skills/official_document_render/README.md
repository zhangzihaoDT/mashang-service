# official_document_render

正式材料排版渲染 Skill

## 适用场景

- 项目申报书（比赛报名、课题申报、基金申请）
- 正式通知、制度文件、管理办法
- 项目验收材料、结题报告
- Markdown → Word / PDF / HTML 格式转换
- 需要正式公文排版气质的任何文本材料

## 输入

| 参数 | 说明 | 示例 |
|------|------|------|
| `--input` | Markdown 文件路径 | `project_application.md` |
| `--output-dir` | 输出目录 | `outputs/submission/` |
| `--basename` | 输出文件基础名（不含后缀） | `项目申报书_xxx` |
| `--formats` | 输出格式，逗号分隔 | `html,pdf,docx` |
| `--title` | 可选，覆盖文档标题 | `"项目申报书"` |
| `--insert-architecture` | 可选架构图路径 | `assets/arch.png` |
| `--max-pdf-mb` | PDF 文件大小上限 | `5` |

## 输出

- `.docx` — Word 文档（通过 pandoc 生成）
- `.pdf` — PDF 文档（通过 weasyprint 生成）
- `.html` — 中间 HTML（带正式排版 CSS）
- 终端 summary（见运行日志）

## 排版规范

- **页面**: A4 纵向，页边距约 25mm
- **正文字体**: Songti SC / SimSun / STSong, 12pt
- **标题字体**: Heiti SC / SimHei, 加粗
- **行距**: 1.6—1.8
- **标题**: 居中，一级 `h2.section` 加粗醒目
- **段落**: 首行缩进 2em
- **页码**: PDF 底部居中，格式 `— 1 —`
- **配色**: 白底黑字，无彩色商业风
- **不加入**: 红头、发文字号、主办单位抬头、印发机关

## 依赖检查

运行前脚本会自动检测以下工具：

| 工具 | 用途 | 缺失影响 |
|------|------|---------|
| pandoc | 生成 DOCX | DOCX 不可用 |
| weasyprint (Python) | 生成 PDF | PDF 不可用 |
| Pillow (Python) | 图片处理 | 无压缩能力 |

## 使用方式

```bash
# 完整生成（自动检测可用格式）
python scripts/render_official_document.py \
  --input skills/official_document_render/examples/project_application_sample.md \
  --output-dir outputs/submission \
  --basename 项目申报书_示例 \
  --formats html,pdf,docx

# 仅 HTML + PDF
python scripts/render_official_document.py \
  --input path/to/doc.md \
  --output-dir outputs/submission \
  --formats html,pdf

# 通过 Makefile
make render-official-doc INPUT=path/to/doc.md BASENAME=项目申报书_示例
```

## 注意事项

- 不改写正文内容
- 不加入政府机关身份信息
- 图片自动压缩，控制 PDF < 5MB
- 不依赖单一工具，降级友好

## 后续可扩展

- `reference.docx` 参考样式模板（pandoc --reference-doc）
- LaTeX 模板（用于 xelatex 引擎）
- 更多排版预设（`--style report / notice / official`）
