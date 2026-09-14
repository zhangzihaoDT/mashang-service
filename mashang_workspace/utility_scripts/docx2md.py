#!/usr/bin/env python3
"""docx -> Markdown converter（Feature Book / 飞书导出 docx 转 Markdown + 图片）。

将 Word (OOXML .docx) 文档转换为规范 Markdown：

- 标题：`w:pStyle` 样式 2/4/5 -> `##/###/####`；Style 1 首个非 Change Log -> `#`
- 表格：pipe table，`gridSpan` 跨列、多行单元格用 `<br>`、嵌套表格递归
- 单列单行表格 -> blockquote（callout，对应飞书文档中的提示框）
- 列表：含 `numPr` 的段落 -> `- `
- 图片：`r:embed` -> `word/media/imageN.ext`，按出现顺序重命名 `{prefix}_{seq:03d}.{ext}`，
  图片引用写入 Markdown，图片文件落在 `<md同名单>_images/`

用法：
    python utility_scripts/docx2md.py <input.docx> [--output out.md] [--title "标题"]
                                   [--img-dir DIR] [--prefix img]

示例：
    python utility_scripts/docx2md.py "~/Downloads/LS6 M2_T1产品简介Feature Book.docx" \
        --output docs/archive/LS6_M2_T1_FeatureBook.md \
        --title "LS6 M2/T1 产品简介 Feature Book"

依赖：lxml（python-docx / pandoc 均不需要）
"""

import argparse
import os
import re
import zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def qw(tag):
    return '{' + W + '}' + tag


def qr(tag):
    return '{' + R + '}' + tag


def qa(tag):
    return '{' + A + '}' + tag


def text_of(el):
    return ''.join(t.text or '' for t in el.iter(qw('t')))


def style_of(p):
    pr = p.find(qw('pPr'))
    if pr is None:
        return None
    st = pr.find(qw('pStyle'))
    return st.get(qw('val')) if st is not None else None


def embed_rids(el):
    rids = []
    for blip in el.iter(qa('blip')):
        for k, v in blip.attrib.items():
            if k.endswith('}embed'):
                rids.append(v)
    return rids


def is_list_item(p):
    pr = p.find(qw('pPr'))
    if pr is None:
        return False
    return pr.find(qw('numPr')) is not None


def render_paragraph_body(p, rid2img):
    """Paragraph body: text runs + inline drawings, in order."""
    buf = []
    for node in p:
        local = etree.QName(node).localname
        if local == 'r':
            rids = embed_rids(node)
            if rids:
                for rid in rids:
                    if rid in rid2img:
                        buf.append(f"![ ]({rid2img[rid]})")
            else:
                buf.append(text_of(node))
        elif local == 'hyperlink':
            for r in node.findall(qw('r')):
                rids = embed_rids(r)
                if rids:
                    for rid in rids:
                        if rid in rid2img:
                            buf.append(f"![ ]({rid2img[rid]})")
                else:
                    buf.append(text_of(r))
    return ''.join(buf)


def render_table(tbl, rid2img):
    grid = tbl.find(qw('tblGrid'))
    ncol = 0
    if grid is not None:
        ncol = len(grid.findall(qw('gridCol')))
    rows = tbl.findall(qw('tr'))
    if ncol == 0:
        for r in rows:
            ncol = max(ncol, len(r.findall(qw('tc'))))

    out_rows = []
    for r in rows:
        cells = []
        for tc in r.findall(qw('tc')):
            span = 1
            tcpr = tc.find(qw('tcPr'))
            if tcpr is not None:
                gs = tcpr.find(qw('gridSpan'))
                if gs is not None:
                    span = int(gs.get(qw('val'), '1'))
            parts = []
            for node in tc:
                local = etree.QName(node).localname
                if local == 'p':
                    body = render_paragraph_body(node, rid2img).strip() or text_of(node).strip()
                    if is_list_item(node):
                        parts.append('- ' + body if body and not body.startswith('- ') else body)
                    else:
                        parts.append(body)
                elif local == 'tbl':
                    inner = render_table(node, rid2img)
                    if inner:
                        parts.append(inner)
            cell = '<br>'.join(x for x in parts if x)
            for _ in range(span):
                cells.append(cell)
        while len(cells) < ncol:
            cells.append('')
        out_rows.append(cells)

    while out_rows and all(not c for c in out_rows[-1]):
        out_rows.pop()
    if not out_rows:
        return ''

    # single-column single-row table -> blockquote (callout)
    if ncol == 1 and len(out_rows) == 1:
        content = out_rows[0][0]
        if content:
            paras = [x for x in content.split('<br>') if x]
            return '\n'.join('> ' + x for x in paras)
        return ''

    lines = []
    for i, row in enumerate(out_rows):
        lines.append('| ' + ' | '.join(row) + ' |')
        if i == 0:
            lines.append('|' + '---|' * ncol)
    return '\n'.join(lines)


def load_rid2img(docx):
    root = etree.fromstring(docx.read('word/_rels/document.xml.rels'))
    rid2img = {}
    for rel in root:
        tgt = rel.get('Target', '')
        m = re.search(r'media/image(\d+)\.([A-Za-z0-9]+)$', tgt)
        if m:
            rid2img[rel.get('Id')] = f'media/image{m.group(1)}.{m.group(2)}'
    return rid2img


def extract_images(docx, rid2img, body, out_dir, prefix='img'):
    """Extract embedded images into out_dir, keyed by rid in first-appearance order."""
    aorder = []
    seen = set()
    for el in body.iter():
        for k, v in el.attrib.items():
            if k.endswith('}embed') and v in rid2img and v not in seen:
                seen.add(v)
                aorder.append(v)
    os.makedirs(out_dir, exist_ok=True)
    renamed = {}
    for i, rid in enumerate(aorder, 1):
        src = rid2img[rid]
        m = re.search(r'image(\d+)\.([A-Za-z0-9]+)$', src)
        ext = m.group(2)
        out_name = f'{prefix}_{i:03d}.{ext}'
        data = docx.read('word/' + src)
        with open(os.path.join(out_dir, out_name), 'wb') as f:
            f.write(data)
        renamed[rid] = f'{os.path.basename(out_dir)}/{out_name}'
    return renamed


def convert(docx_path, md_path, img_dir=None, prefix='img', title=None):
    """Convert a .docx file to Markdown, extracting images alongside."""
    docx = zipfile.ZipFile(docx_path)
    rid2img = load_rid2img(docx)
    body = etree.fromstring(docx.read('word/document.xml')).find(qw('body'))

    if img_dir is None:
        base = os.path.splitext(os.path.basename(md_path))[0]
        img_dir = os.path.join(os.path.dirname(md_path), base + '_images')
        prefix = base
    renamed_rids = extract_images(docx, rid2img, body, img_dir, prefix)
    rid2img2 = {rid: renamed_rids.get(rid, v) for rid, v in rid2img.items()}

    lines = []
    first_plain = True
    for node in body:
        local = etree.QName(node).localname
        if local == 'p':
            st = style_of(node)
            txt = text_of(node).strip()
            if st == '1':
                if txt:
                    if txt == 'Change Log':
                        lines.append('## ' + txt)
                    else:
                        lines.append('# ' + txt)
            elif st == '2':
                if txt:
                    lines.append('## ' + txt)
            elif st == '4':
                if txt:
                    lines.append('### ' + txt)
            elif st == '5':
                if txt:
                    lines.append('#### ' + txt)
            else:
                buf = render_paragraph_body(node, rid2img2)
                if first_plain and buf.strip():
                    first_plain = False
                    if not title:
                        lines.append('# ' + buf.strip())
                    continue
                if is_list_item(node):
                    if buf.lstrip().startswith('- '):
                        lines.append(buf.lstrip())
                    else:
                        lines.append('- ' + buf.lstrip()
                                      if buf.strip() else '')
                elif buf.strip():
                    lines.append(buf)
        elif local == 'tbl':
            tbl = render_table(node, rid2img2)
            if tbl:
                lines.append(tbl)

    md = '\n\n'.join(l for l in lines)
    if title:
        md = '# ' + title + '\n\n' + md
    with open(md_path, 'w') as f:
        f.write(md)
    return md


def main():
    parser = argparse.ArgumentParser(description='docx -> Markdown converter')
    parser.add_argument('input', help='input .docx file')
    parser.add_argument('-o', '--output', default='output.md', help='output .md file')
    parser.add_argument('--title', default='', help='document title (used as H1 if provided)')
    parser.add_argument('--img-dir', default=None, help='image output directory')
    parser.add_argument('--prefix', default='img', help='image file prefix (default: img)')
    args = parser.parse_args()

    md = convert(args.input, args.output, img_dir=args.img_dir,
                 prefix=args.prefix, title=args.title or None)
    print(f'chars: {len(md)}')
    print(f'img refs: {md.count("![")}')
    print(f'lines: {len(md.splitlines())}')


if __name__ == '__main__':
    main()