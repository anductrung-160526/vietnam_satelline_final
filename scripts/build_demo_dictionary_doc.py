"""Sinh Word phần C từ hai tài liệu Markdown, không cần dữ liệu ở ổ E.

python -m pip install -r docs/requirements.txt
python scripts/build_demo_dictionary_doc.py
"""
from collections import Counter
from pathlib import Path
import re

from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs'


def dictionary_rows():
    lines = [line for line in (DOCS/'NIGHT_DATA_DICTIONARY.md').read_text(encoding='utf-8').splitlines()
             if line.startswith('|')]
    headers = [s.strip() for s in lines[0].strip('|').split('|')]
    rows = [dict(zip(headers, [s.strip().strip('`') for s in line.strip('|').split('|')])) for line in lines[2:]]
    assert len({r['field'] for r in rows}) == len(rows), 'Trùng trường trong dictionary.'
    assert {r['table'] for r in rows} == {'Night Data', 'Night Economy'}
    assert all(r['field'] == r['field'].lower() for r in rows)
    assert [r['note'] for r in rows] == sorted([r['note'] for r in rows], key=lambda x: x != 'Raw')
    return rows


def clean(text):
    text = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', text)
    return text.replace('`', '').replace('**', '')


def style_section(section, landscape=False):
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = (Cm(29.7), Cm(21)) if landscape else (Cm(21), Cm(29.7))
    section.top_margin = section.bottom_margin = Cm(1.6)
    section.left_margin = section.right_margin = Cm(1.4)


def main():
    rows = dictionary_rows()
    counts = Counter(r['note'] for r in rows)
    proposed = {'valid_area_km2', 'valid_area_pct', 'class_area_pct'}
    identity = sum(r['group'] == 'Định danh' for r in rows)
    document = Document()
    style_section(document.sections[0])
    normal = document.styles['Normal']
    normal.font.name = 'Arial'
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    for name in ['Title', 'Heading 1', 'Heading 2']:
        document.styles[name].font.name = 'Arial'
        document.styles[name].font.color.rgb = RGBColor.from_string('174A6E')
    document.add_heading('ĐỊNH NGHĨA BIẾN VÀ CÔNG THỨC', 0)
    document.add_paragraph('APP KINH TẾ ĐÊM · PHẦN C · 22/11/2026', style='Subtitle')
    document.add_paragraph('Bản làm việc cho demo — chưa xác nhận theo form giảng viên. Công thức NEI tổng hợp chưa chốt.')
    document.add_heading('Thống kê danh mục', 1)
    summary = document.add_table(rows=1, cols=2)
    summary.style = 'Light Shading Accent 1'
    summary.rows[0].cells[0].text = 'Phạm vi đếm'
    summary.rows[0].cells[1].text = 'Số mục'
    for label, count in [
        ('Tổng mục trong từ điển', len(rows)),
        ('Raw gồm định danh và metadata đầu vào', counts['Raw']),
        ('Trong Raw: định danh tỉnh/thời gian', identity),
        ('Raw không gồm định danh (vẫn gồm metadata)', counts['Raw']-identity),
        ('Processed gồm chỉ số, tham số và metadata', counts['Processed']),
        ('Trong Processed: công thức đề xuất, chưa có đầu ra riêng', len(proposed)),
        ('Mục đã có nguồn/cột hoặc tham chiếu thực tế', len(rows)-len(proposed)),
    ]:
        cells = summary.add_row().cells
        cells[0].text, cells[1].text = label, str(count)
    document.add_paragraph('Không cộng trùng khóa ở hai CSV; đây không phải số biến độc lập thống kê. TNL và SOL_raw trùng bản chất trên cùng đầu vào. Chưa có đủ 64 cột trong một file đầu ra duy nhất.')
    for line in (DOCS/'DINH_NGHIA_BIEN_VA_CONG_THUC_DEMO.md').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('# '):
            continue
        if line.startswith('## '):
            document.add_heading(clean(line[3:]), 1)
        else:
            document.add_paragraph(clean(line[2:] if line.startswith('- ') else line), style='List Bullet' if line.startswith('- ') else None)
    document.add_heading('Công thức đối chiếu', 1)
    for text in ['SOL_raw = ∑ᵢ∈ᵥ Rᵢ', 'SOL = ∑ᵢ∈ᵥ Rᵢ · 1[Rᵢ ≥ b]',
                 'A_lit = ∑ᵢ∈ᵥ aᵢ · 1[Rᵢ ≥ h]', 'sol_density = SOL_selected / A',
                 'ln(G) = α + β · ln(SOL) + ε']:
        p = document.add_paragraph()
        math = OxmlElement('m:oMath')
        run = OxmlElement('m:r')
        value = OxmlElement('m:t')
        value.text = text
        run.append(value)
        math.append(run)
        p._p.append(math)
    section = document.add_section(WD_SECTION_START.NEW_PAGE)
    style_section(section, landscape=True)
    document.add_heading('Phụ lục — danh mục trường dữ liệu', 1)
    document.add_paragraph('Bản đầy đủ các cột table/group/task3_field_lowercase nằm trong NIGHT_DATA_DICTIONARY.md. Phụ lục giữ cùng 64 định nghĩa, rút gọn cấu trúc cột để đọc trên trang ngang.')
    widths = [3.2, 6.0, 5.3, 1.9, 1.8, 8.7]
    for stage in ['Raw', 'Processed']:
        document.add_heading(stage, 2)
        table = document.add_table(rows=1, cols=6)
        table.style = 'Light Shading Accent 1'
        table.autofit = False
        for column, width in zip(table.columns, widths):
            column.width = Cm(width)
        for cell, text in zip(table.rows[0].cells, ['field', 'table / group / description', 'formula', 'unit', 'frequency', 'storage / implementation']):
            cell.text = text
        properties = table.rows[0]._tr.get_or_add_trPr()
        properties.append(OxmlElement('w:tblHeader'))
        for r in [r for r in rows if r['note'] == stage]:
            cells = table.add_row().cells
            values = [r['field'], f"{r['table']} · {r['group']}\n{r['description']}", r['formula'], r['unit'], r['frequency'], r['storage']]
            for cell, text, width in zip(cells, values, widths):
                cell.width = Cm(width)
                cell.text = clean(text)
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(3)
                    for run in paragraph.runs:
                        run.font.size = Pt(8.5)
            table.rows[-1]._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    footer = document.sections[0].footer.paragraphs[0]
    footer.text = 'Kinh tế đêm · Bản làm việc phần C · Trang '
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    document.core_properties.title = 'Định nghĩa biến và công thức — kinh tế đêm'
    document.core_properties.subject = 'Raw, Processed, phân lớp sáng, GRDP và trạng thái NEI'
    target = DOCS/'DINH_NGHIA_BIEN_VA_CONG_THUC_DEMO.docx'
    document.save(target)
    # Mở lại bằng bộ đọc Word để kiểm tra gói và số dòng phụ lục.
    opened = Document(target)
    assert sum(len(t.rows)-1 for t in opened.tables[1:]) == len(rows)
    print(f'{target}\n{len(rows)} mục: Raw={counts["Raw"]}, Processed={counts["Processed"]}; đề xuất={len(proposed)}')


if __name__ == '__main__':
    main()
