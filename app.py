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
st.write("Сервис читает лист подбора и после каждой этикетки добавляет страницу с названием товара.")

# --- ЗАГРУЗКА ШРИФТА (Для поддержки русского языка в сгенерированных PDF) ---
@st.cache_resource
def load_font():
    # Задаем новое имя, чтобы проигнорировать старые битые файлы в папке
    font_path = "OzonFont_Fix.ttf" 
    
    if not os.path.exists(font_path):
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto-Regular.ttf"
        # Притворяемся браузером Safari на Mac, чтобы сервер отдал нам реальный файл
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15'
        }
        r = requests.get(url, headers=headers)
        
        with open(font_path, 'wb') as f:
            f.write(r.content)
            
    pdfmetrics.registerFont(TTFont('OzonFont', font_path))
    return 'OzonFont'

font_name = load_font()

def parse_assembly_list(pdf_file):
    """
    Парсит лист подбора. 
    Ищет связки: Номер заказа -> Наименование товара.
    """
    reader = PdfReader(pdf_file)
    data = {}
    full_text = ""
    
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
        
    lines = full_text.split('\n')
    
    for line in lines:
        # ВНИМАНИЕ: Регулярное выражение для поиска номера заказа.
        # \d{7,}-\d{4,} - ищет форматы типа 12345678-1234 (популярно у Ozon/Яндекс)
        # Если у вас другой формат, эту строчку нужно будет адаптировать.
        order_match = re.search(r'(\d{7,}-\d{4,})|\b(\d{10,})\b', line) 
            
        if order_match:
            # Берем первое совпадение (либо формат с дефисом, либо просто длинное число)
            current_order = order_match.group(1) if order_match.group(1) else order_match.group(2)
            
            # Отрезаем номер заказа от строки, чтобы осталось только название и количество
            clean_line = line.replace(current_order, '').strip()
            
            # Попытка вытащить количество (например, "2 шт")
            qty_match = re.search(r'(\d+)\s*шт', clean_line.lower())
            qty = int(qty_match.group(1)) if qty_match else 1
            
            # Убираем упоминание штук из названия
            name = re.sub(r'\d+\s*шт.*', '', clean_line, flags=re.IGNORECASE).strip()
            
            # Если строка слишком короткая, ставим заглушку
            if len(name) < 3:
                name = clean_line 
                
            data[current_order] = {"name": name, "qty": qty}
            
    return data, full_text

def create_info_label(width, height, order_number, product_info):
    """
    Генерирует новую PDF-страницу с названием товара.
    Размер страницы точно такой же, как у термоэтикетки.
    """
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    
    c.setFont(font_name, 12)
    x_margin = 15
    y_start = height - 30
    
    # Шапка информационной этикетки
    c.drawString(x_margin, y_start, f"Отправление: {order_number}")
    c.line(x_margin, y_start - 5, width - x_margin, y_start - 5)
    
    c.setFont(font_name, 14)
    
    # Текст названия товара (с простейшим переносом строк)
    name = product_info.get('name', 'ВНИМАНИЕ: Товар не найден в листе подбора')
    qty = product_info.get('qty', 1)
    
    max_chars = 30 # Примерное количество символов в строке на узкой этикетке
    words = name.split()
    lines = []
    curr_line = ""
    
    for w in words:
        if len(curr_line) + len(w) < max_chars:
            curr_line += w + " "
        else:
            lines.append(curr_line)
            curr_line = w + " "
    lines.append(curr_line)
    
    y = y_start - 25
    for line in lines:
        c.drawString(x_margin, y, line)
        y -= 18 # Отступ между строками
        
    # Крупно пишем количество внизу
    c.setFont(font_name, 16)
    c.drawString(x_margin, y - 10, f"Кол-во: {qty} шт.")
    
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
                st.error("Не удалось найти номера отправлений в Листе подбора.")
                with st.expander("Показать извлеченный текст (для отладки регулярных выражений)"):
                    st.text(debug_text[:2000] + "...")
                st.stop()
            else:
                st.write(f"✅ Найдено {len(assembly_data)} уникальных отправлений в листе подбора.")
                
            st.write("Генерация новых этикеток...")
            reader_labels = PdfReader(labels_file)
            writer = PdfWriter()
            
            progress_bar = st.progress(0)
            num_pages = len(reader_labels.pages)
            matched_count = 0
            
            for i in range(num_pages):
                page = reader_labels.pages[i]
                page_text = page.extract_text()
                
                # 1. Добавляем оригинальную этикетку
                writer.add_page(page)
                
                # Ищем номер отправления на самой этикетке
                page_order_match = re.search(r'(\d{7,}-\d{4,})|\b(\d{10,})\b', page_text)
                
                # Получаем точный размер текущей этикетки, чтобы сгенерированная была такой же
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                
                if page_order_match:
                    order_num = page_order_match.group(1) if page_order_match.group(1) else page_order_match.group(2)
                    
                    product_info = assembly_data.get(order_num, {"name": "Не найдено в листе подбора", "qty": "?"})
                    if product_info["name"] != "Не найдено в листе подбора":
                        matched_count += 1
                        
                    # 2. Создаем и добавляем информационную этикетку
                    info_page = create_info_label(width, height, order_num, product_info)
                    writer.add_page(info_page)
                else:
                    info_page = create_info_label(width, height, "Номер не распознан", {"name": "Штрихкод/номер не прочитан", "qty": "-"})
                    writer.add_page(info_page)
                    
                progress_bar.progress(int(((i + 1) / num_pages) * 100))
                
            status.update(label="Готово!", state="complete", expanded=False)
            
        st.success(f"🎉 Успешно! Сопоставлено этикеток: {matched_count} из {num_pages}.")
        
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        
        st.download_button(
            label="📥 Скачать готовый PDF для печати",
            data=output,
            file_name="Склеенные_этикетки_на_склад.pdf",
            mime="application/pdf",
            type="primary"
        )
