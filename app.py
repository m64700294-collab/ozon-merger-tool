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
st.write("Сервис читает лист подбора и после каждой этикетки добавляет понятную страницу для склада.")

# --- ЗАГРУЗКА ШРИФТА ---
@st.cache_resource
def load_font():
    font_path = "Clean_Roboto_Font.ttf" 
    if not os.path.exists(font_path):
        url = "https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Me5WZLCzYlKw.ttf"
        r = requests.get(url)
        with open(font_path, 'wb') as f:
            f.write(r.content)
    pdfmetrics.registerFont(TTFont('OzonFont', font_path))
    return 'OzonFont'

font_name = load_font()

def parse_assembly_list(pdf_file):
    """
    Парсит лист подбора Ozon в новом формате.
    """
    reader = PdfReader(pdf_file)
    data = {}
    full_text = ""
    
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
        
    # Ищем строки начала заказов (Например: "1 66007881-1086-1")
    matches = list(re.finditer(r'^(\d+)\s+(\d{8,15}-\d{4}-\d+)', full_text, re.MULTILINE))
    
    for i in range(len(matches)):
        start = matches[i].end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(full_text)
        
        order_num = matches[i].group(2)
        
        # Склеиваем текст товара в одну строку
        details = full_text[start:end].replace('\n', ' ').strip()
        
        # Озон пишет в конце: [Название] [Артикул] [Количество] [4 цифры этикетки]
        detail_match = re.search(r'(.*?)\s+(\S+)\s+(\d+)\s+(\d{4})$', details)
        
        if detail_match:
            data[order_num] = {
                "name": detail_match.group(1).strip(),
                "article": detail_match.group(2).strip(),
                "qty": detail_match.group(3).strip()
            }
        else:
            data[order_num] = {"name": details, "article": "-", "qty": "1"}
            
    return data, full_text

def create_info_label(width, height, order_number, product_info):
    """
    Генерирует новую PDF-страницу с крупной и понятной информацией.
    """
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    
    x_margin = 15
    y_start = height - 25
    
    # 1. Номер отправления
    c.setFont(font_name, 12)
    c.drawString(x_margin, y_start, f"Заказ: {order_number}")
    c.line(x_margin, y_start - 5, width - x_margin, y_start - 5)
    
    # 2. Артикул
    y_current = y_start - 25
    c.setFont(font_name, 14)
    c.drawString(x_margin, y_current, f"Арт: {product_info.get('article', '-')}")
    
    # 3. Название товара (с переносом строк)
    y_current -= 20
    c.setFont(font_name, 10)
    name = product_info.get('name', 'Товар не найден')
    
    max_chars = 35 # Символов в строке
    words = name.split()
    curr_line = ""
    
    for w in words:
        if len(curr_line) + len(w) < max_chars:
            curr_line += w + " "
        else:
            c.drawString(x_margin, y_current, curr_line.strip())
            y_current -= 12
            curr_line = w + " "
    if curr_line:
        c.drawString(x_margin, y_current, curr_line.strip())
        
    # 4. Количество (ОГРОМНЫМИ ЦИФРАМИ ВНИЗУ)
    c.setFont(font_name, 26)
    qty = product_info.get('qty', '?')
    c.drawString(x_margin, 30, f"КОЛ-ВО: {qty} шт")
    
    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

# --- ИНТЕРФЕЙС СТРАНИЦЫ ---
col1, col2 = st.columns(2)
with col1:
    labels_file = st.file_uploader("1️⃣ Загрузите Ленту наклеек (PDF)", type="pdf")
with col2:
    assembly_file = st.file_uploader("2️⃣ Загрузите Лист подбора (PDF)", type="pdf")

if labels_file and assembly_file:
    if st.button("🚀 Склеить файлы", type="primary", use_container_width=True):
        
        with st.status("Обработка файлов...", expanded=True) as status:
            st.write("Анализ листа подбора...")
            assembly_data, debug_text = parse_assembly_list(assembly_file)
            
            if not assembly_data:
                st.error("Не удалось прочитать лист подбора. Проверьте формат файла.")
                st.stop()
            else:
                st.write(f"✅ Найдено {len(assembly_data)} уникальных товаров.")
                
            st.write("Склейка этикеток...")
            reader_labels = PdfReader(labels_file)
            writer = PdfWriter()
            
            progress_bar = st.progress(0)
            num_pages = len(reader_labels.pages)
            matched_count = 0
            
            for i in range(num_pages):
                page = reader_labels.pages[i]
                page_text = page.extract_text()
                
                # Добавляем саму этикетку Озона
                writer.add_page(page)
                
                # Ищем номер заказа на этикетке (Новый точный формат)
                page_order_match = re.search(r'(\d{8,15}-\d{4}-\d+)', page_text)
                
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                
                if page_order_match:
                    order_num = page_order_match.group(1)
                    product_info = assembly_data.get(order_num, {"name": "Не найдено", "article": "-", "qty": "?"})
                    
                    if product_info["name"] != "Не найдено":
                        matched_count += 1
                        
                    info_page = create_info_label(width, height, order_num, product_info)
                    writer.add_page(info_page)
                else:
                    info_page = create_info_label(width, height, "Номер не прочитан", {"name": "-", "article": "-", "qty": "-"})
                    writer.add_page(info_page)
                    
                progress_bar.progress(int(((i + 1) / num_pages) * 100))
                
            status.update(label="Готово!", state="complete", expanded=False)
            
        st.success(f"🎉 Успешно! Найдено совпадений: {matched_count} из {num_pages}.")
        
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        st.download_button(
            label="📥 Скачать готовый PDF для печати",
            data=output,
            file_name="Этикетки_с_информацией.pdf",
            mime="application/pdf",
            type="primary"
        )
