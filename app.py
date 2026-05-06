import streamlit as st
import re
import os
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Умная склейка этикеток", page_icon="🖨️", layout="wide")

st.title("🖨️ Склейка: Этикетки + Лист подбора")
st.write("Сервис автоматически подбирает размер текста, чтобы всё влезло на этикетку.")

# --- ЗАГРУЗКА ШРИФТА ---
@st.cache_resource
def load_font():
    font_path = "Roboto_Full_Final.ttf" 
    if not os.path.exists(font_path):
        url = "https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.66/fonts/Roboto/Roboto-Regular.ttf"
        r = requests.get(url)
        with open(font_path, 'wb') as f:
            f.write(r.content)
    pdfmetrics.registerFont(TTFont('OzonFont', font_path))
    return 'OzonFont'

font_name = load_font()

def parse_assembly_list(pdf_file):
    reader = PdfReader(pdf_file)
    data = {}
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
    
    matches = list(re.finditer(r'^(\d+)\s+(\d{8,15}-\d{4}-\d+)', full_text, re.MULTILINE))
    for i in range(len(matches)):
        start = matches[i].end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(full_text)
        order_num = matches[i].group(2)
        details = full_text[start:end].replace('\n', ' ').strip()
        detail_match = re.search(r'(.*?)\s+(\S+)\s+(\d+)\s+(\d{4})$', details)
        
        if detail_match:
            data[order_num] = {
                "name": detail_match.group(1).strip(),
                "article": detail_match.group(2).strip(),
                "qty": detail_match.group(3).strip()
            }
        else:
            data[order_num] = {"name": details, "article": "-", "qty": "1"}
    return data

def create_info_label(width, height, order_number, product_info):
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    
    x_margin = 10
    # 1. Заголовок (Номер заказа)
    c.setFont(font_name, 10)
    c.drawString(x_margin, height - 18, f"Заказ: {order_number}")
    c.line(x_margin, height - 20, width - x_margin, height - 20)
    
    # 2. Артикул (Чуть крупнее)
    c.setFont(font_name, 12)
    article = product_info.get('article', '-')
    if len(article) > 25: article = article[:22] + "..."
    c.drawString(x_margin, height - 35, f"Арт: {article}")
    
    # 3. Название товара с динамическим сжатием
    name = product_info.get('name', 'Товар не найден')
    
    top_limit = height - 52   # Верхняя граница текста
    bottom_limit = 50        # Нижняя граница (над количеством)
    available_h = top_limit - bottom_limit
    
    current_size = 10
    line_h = 12
    
    def get_lines(txt, chars):
        words = txt.split()
        res, cur = [], ""
        for w in words:
            if len(cur) + len(w) < chars: cur += w + " "
            else:
                res.append(cur.strip())
                cur = w + " "
        res.append(cur.strip())
        return res

    # Подбираем размер, чтобы влезло в высоту
    lines = get_lines(name, 32)
    while (len(lines) * line_h) > available_h and current_size > 6:
        current_size -= 0.5
        line_h -= 0.6
        lines = get_lines(name, int(32 * (10/current_size)))

    c.setFont(font_name, current_size)
    y_text = top_limit
    for line in lines:
        if y_text > bottom_limit:
            c.drawString(x_margin, y_text, line)
            y_text -= line_h
            
    # 4. Количество (Фиксировано в самом низу)
    c.setFont(font_name, 24)
    qty = product_info.get('qty', '?')
    c.drawString(x_margin, 15, f"КОЛ-ВО: {qty}")
    
    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

# --- ИНТЕРФЕЙС ---
col1, col2 = st.columns(2)
with col1:
    labels_file = st.file_uploader("1️⃣ Этикетки (PDF)", type="pdf")
with col2:
    assembly_file = st.file_uploader("2️⃣ Лист подбора отправлений (PDF)", type="pdf")

if labels_file and assembly_file:
    if st.button("🚀 Склеить файлы", type="primary", use_container_width=True):
        with st.status("Склеиваем...") as status:
            assembly_data = parse_assembly_list(assembly_file)
            reader = PdfReader(labels_file)
            writer = PdfWriter()
            
            for i in range(len(reader.pages)):
                page = reader.pages[i]
                writer.add_page(page)
                
                text = page.extract_text()
                order_match = re.search(r'(\d{8,15}-\d{4}-\d+)', text)
                
                w, h = float(page.mediabox.width), float(page.mediabox.height)
                
                if order_match:
                    order_num = order_match.group(1)
                    info = assembly_data.get(order_num, {"name": "Не найдено", "article": "-", "qty": "?"})
                    writer.add_page(create_info_label(w, h, order_num, info))
                else:
                    writer.add_page(create_info_label(w, h, "???", {"name": "Номер не найден", "article": "-", "qty": "-"}))
            
            status.update(label="Готово!", state="complete")
            
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        st.download_button("📥 Скачать результат", output, "Ready_Labels.pdf", "application/pdf")
