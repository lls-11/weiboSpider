// 由 spec.json 生成 Word：node results/person_v1/word/build_docx.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, LevelFormat, Footer, PageNumber,
} = require('docx');

const HERE = __dirname;
const spec = JSON.parse(fs.readFileSync(path.join(HERE, 'spec.json'), 'utf8'));
const FONT = { ascii: 'Calibri', hAnsi: 'Calibri', eastAsia: 'Microsoft YaHei', cs: 'Calibri' };
const ACCENT = '2F6F9F';
const CONTENT_W = 9026; // A4 减去左右各 1 英寸

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

const border = { style: BorderStyle.SINGLE, size: 4, color: 'C9CED6' };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, head) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: head ? { fill: 'E8EEF4', type: ShadingType.CLEAR, color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ spacing: { before: 0, after: 0, line: 300 },
      children: [new TextRun({ text: String(text), bold: !!head, size: 19, font: FONT })] })],
  });
}

function caption(text) {
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 200 },
    children: [new TextRun({ text, size: 18, color: '555555', font: FONT })] });
}

const children = [
  new Paragraph({ spacing: { before: 600, after: 120 }, alignment: AlignmentType.LEFT,
    children: [new TextRun({ text: spec.title, bold: true, size: 40, color: '1F2933', font: FONT })] }),
  new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: spec.subtitle, size: 26, color: '444444', font: FONT })] }),
  new Paragraph({ spacing: { after: 360 }, border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 8 } },
    children: [new TextRun({ text: spec.meta, size: 20, color: '666666', font: FONT })] }),
];

for (const b of spec.blocks) {
  if (b.t === 'h1') children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: b.text, font: FONT })] }));
  else if (b.t === 'h2') children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: b.text, font: FONT })] }));
  else if (b.t === 'p') children.push(new Paragraph({ spacing: { after: 140, line: 360 }, children: [new TextRun({ text: b.text, font: FONT })] }));
  else if (b.t === 'ul') b.items.forEach((t) => children.push(new Paragraph({ numbering: { reference: 'bullets', level: 0 },
    spacing: { after: 80, line: 340 }, children: [new TextRun({ text: t, font: FONT })] })));
  else if (b.t === 'img') {
    const s = pngSize(b.file);
    const w = Math.round(b.w * 96);
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 0 },
      children: [new ImageRun({ type: 'png', data: fs.readFileSync(b.file), transformation: { width: w, height: Math.round(w * s.h / s.w) },
        altText: { title: b.caption, description: b.caption, name: path.basename(b.file) } })] }));
    children.push(caption(b.caption));
  } else if (b.t === 'table') {
    if (b.caption) children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
      children: [new TextRun({ text: b.caption, size: 18, color: '555555', font: FONT })] }));
    const total = b.widths.reduce((a, c) => a + c, 0);
    children.push(new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: b.widths,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: b.head.map((h, i) => cell(h, b.widths[i], true)) }),
        ...b.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, b.widths[i], false)) }))] }));
    children.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
  }
}

const doc = new Document({
  creator: 'Claude',
  title: spec.title,
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 30, bold: true, color: '1F2933', font: FONT }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 420, hanging: 260 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '888888' })] })] }) },
    children,
  }],
});

const out = path.join(HERE, '创新人才指标文本分析报告.docx');
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log(out); });
