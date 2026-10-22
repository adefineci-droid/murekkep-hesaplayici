import streamlit as st
import subprocess
import pymupdf
import os
import glob
from PIL import Image
from fpdf import FPDF
import tempfile

# Sayfa Ayarları
st.set_page_config(page_title="Mürekkep Sarfiyat Analizi", page_icon="🎨", layout="wide")

def tr_to_eng(text):
    """PDF raporunda Türkçe karakter hatası almamak için çeviri yapar"""
    tr = "ğüşöçıİĞÜŞÖÇ"
    eng = "gusoiiIGUSOC"
    return text.translate(str.maketrans(tr, eng))

def get_page_dimensions_in_sqm(pdf_path):
    doc = pymupdf.open(pdf_path)
    areas = []
    for page in doc:
        rect = page.rect
        width_m = (rect.width / 72.0) * 0.0254
        height_m = (rect.height / 72.0) * 0.0254
        areas.append(width_m * height_m)
    doc.close()
    return areas

def get_spot_coverages(pdf_path):
    temp_dir = "renk_ayrimlari"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    else:
        for f in glob.glob(os.path.join(temp_dir, "*")):
            os.remove(f)
            
    gs_cmd = 'gs' if os.name != 'nt' else 'gswin64c'
    output_pattern = os.path.join(temp_dir, "sayfa_%d.tif")
    
    cmd = [
        gs_cmd, '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=tiffsep',
        '-r72', f'-sOutputFile={output_pattern}', pdf_path
    ]
    
    subprocess.run(cmd, check=True)
    coverages_by_page = {}
    
    for filepath in glob.glob(os.path.join(temp_dir, "*.tif")):
        filename = os.path.basename(filepath)
        if "(" not in filename:
            continue
            
        try:
            page_part, color_part = filename.split('(', 1)
            page_num = int(page_part.split('_')[1])
            color_name = color_part.split(')')[0]
            
            img = Image.open(filepath)
            histogram = img.histogram()
            total_pixels = img.width * img.height
            total_ink = 0
            
            for tone, count in enumerate(histogram):
                ink_value = (255 - tone) / 255.0
                total_ink += ink_value * count
                
            coverage_percent = total_ink / total_pixels
            
            if coverage_percent > 0.0001:
                if page_num not in coverages_by_page:
                    coverages_by_page[page_num] = {}
                coverages_by_page[page_num][color_name] = coverage_percent
                
        except Exception as e:
            st.error(f"Hata: {filename} analiz edilemedi. {e}")
            
    return coverages_by_page

def create_pdf_report(data, filename="Sarfiyat_Raporu.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, tr_to_eng("Mürekkep Sarfiyat Analiz Raporu"), ln=True, align="C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, tr_to_eng(f"Analiz Edilen Dosya: {data['filename']}"), ln=True)
    pdf.cell(0, 8, tr_to_eng(f"Hesaplama Kriteri: %100 dolu alan icin {data['criteria']} gr/m2"), ln=True)
    pdf.cell(0, 8, tr_to_eng(f"Toplam Belge Alani: {data['total_area']:.4f} m2"), ln=True)
    pdf.cell(0, 8, tr_to_eng(f"Siparis Miktari: {data['order_qty']:,.0f} Adet"), ln=True)
    pdf.ln(5)
    
    # Sayfa Detayları
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, tr_to_eng("Sayfa Detaylari (Tek Adet Icin)"), ln=True)
    pdf.set_font("Arial", "", 11)
    
    for page in data['pages']:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, tr_to_eng(f"--- Sayfa {page['page_num']} (Alan: {page['area']:.4f} m2) ---"), ln=True)
        pdf.set_font("Arial", "", 11)
        for color in page['colors']:
            pdf.cell(0, 6, tr_to_eng(f"  - {color['name']}: %{color['coverage']:.2f} kaplama -> {color['weight']:.4f} gram"), ln=True)
        pdf.ln(3)
        
    # Toplam Sonuçlar (Tek)
    pdf.ln(2)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, tr_to_eng("TEK ADET ICIN TOPLAM TUKETIM"), ln=True)
    pdf.set_font("Arial", "B", 12)
    for color_name, weight in data['total_ink'].items():
        pdf.cell(0, 8, tr_to_eng(f"{color_name}: {weight:.4f} gram"), ln=True)
        
    # Toplam Sonuçlar (Sipariş - KG Cinsinden ve Dağılımlı)
    pdf.ln(8)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, tr_to_eng(f"TUM SIPARIS ICIN GENEL TOPLAM ({data['order_qty']:,.0f} Adet)"), ln=True, fill=True)
    pdf.set_font("Arial", "", 12)
    
    for color_name, weight in data['grand_total_ink'].items():
        kg_weight = weight / 1000.0
        tiner_kg = kg_weight * (data['solvent'] / 100.0)
        kalan_govde = kg_weight - tiner_kg
        vernik_kg = kalan_govde * (data['vernik'] / 100.0)
        ham_boya_kg = kalan_govde - vernik_kg
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, tr_to_eng(f"[{color_name}] Toplam Kova (Islak): {kg_weight:.2f} KG"), ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 6, tr_to_eng(f"   -> Ham Boya (Cinden): {ham_boya_kg:.2f} KG"), ln=True)
        pdf.cell(0, 6, tr_to_eng(f"   -> Vernik: {vernik_kg:.2f} KG"), ln=True)
        pdf.cell(0, 6, tr_to_eng(f"   -> Tiner: {tiner_kg:.2f} KG"), ln=True)
        pdf.ln(3)
        
    pdf.output(filename)

# --- ARAYÜZ (UI) TASARIMI ---
st.title("🎨 Ambalaj Mürekkep Sarfiyat ve Renk Analizi")
st.markdown("Yüksek tirajlı rotogravür/flekso baskılar için metrekare, renk ayrımı ve reçete bazlı gramaj hesaplayıcı.")

# Yan Menü (Sidebar) Ayarları
with st.sidebar:
    st.header("⚙️ Hesaplama Ayarları")
    ink_grams = st.number_input("%100 Dolulukta Gramaj (gr/m²)", min_value=0.1, value=5.08, step=0.01)
    
    st.divider()
    st.header("🧪 Mürekkep Reçetesi")
    solvent_orani = st.slider("Tiner (Solvent) Payı (%)", min_value=0, max_value=50, value=20, step=1)
    vernik_orani = st.slider("Vernik (Extender) Payı (%)", min_value=0, max_value=80, value=50, step=5)
    st.info("Vernik payı %50 ise, boya 1:1 oranında vernikle açılıyor demektir.")
    
    st.divider()
    st.header("📦 Üretim Ayarları")
    order_qty = st.number_input("Sipariş Miktarı (Adet)", min_value=1, value=50000, step=1000)
    
    st.info("Sipariş miktarı, atölye için toplam hazırlanması gereken mürekkep hacmini (KG) hesaplamanızı sağlar.")

# Dosya Yükleme Alanı
uploaded_file = st.file_uploader("Lütfen PDF baskı dosyasını yükleyin", type=["pdf"])

if uploaded_file is not None:
    st.success(f"{uploaded_file.name} başarıyla yüklendi!")
    
    if st.button("🚀 Analizi Başlat", type="primary"):
        with st.spinner('Renk plakaları ayrıştırılıyor ve hesaplanıyor... Lütfen bekleyin.'):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                temp_pdf.write(uploaded_file.read())
                temp_pdf_path = temp_pdf.name
            
            # Analizi Yap
            areas_sqm = get_page_dimensions_in_sqm(temp_pdf_path)
            coverages_by_page = get_spot_coverages(temp_pdf_path)
            
            if not coverages_by_page:
                st.warning("Belgede analiz edilecek renk bulunamadı.")
            else:
                total_ink_all_colors = {}
                total_area = sum(areas_sqm)
                
                report_data = {
                    'filename': uploaded_file.name,
                    'criteria': ink_grams,
                    'order_qty': order_qty,
                    'total_area': total_area,
                    'pages': [],
                    'total_ink': {},
                    'grand_total_ink': {},
                    'solvent': solvent_orani,
                    'vernik': vernik_orani
                }
                
                st.subheader("📊 Sayfa Bazlı Analiz (Tek Adet İçin)")
                
                for i, area in enumerate(areas_sqm):
                    page_num = i + 1
                    page_coverages = coverages_by_page.get(page_num, {})
                    
                    with st.expander(f"📄 Sayfa {page_num} (Alan: {area:.4f} m²)", expanded=True):
                        page_info = {'page_num': page_num, 'area': area, 'colors': []}
                        
                        for color_name, coverage in page_coverages.items():
                            covered_area = area * coverage
                            ink_weight = covered_area * ink_grams
                            
                            if color_name not in total_ink_all_colors:
                                total_ink_all_colors[color_name] = 0.0
                            total_ink_all_colors[color_name] += ink_weight
                            
                            st.write(f"**{color_name}:** %{coverage*100:.2f} yoğunluk ➔ **{ink_weight:.4f} gram**")
                            
                            page_info['colors'].append({'name': color_name, 'coverage': coverage*100, 'weight': ink_weight})
                        
                        report_data['pages'].append(page_info)
                
                report_data['total_ink'] = total_ink_all_colors
                
                # Tüm Sipariş İçin Toplam Hesaplama (Adet * Tekli Ağırlık)
                grand_total = {color: weight * order_qty for color, weight in total_ink_all_colors.items()}
                report_data['grand_total_ink'] = grand_total
                
                st.divider()
                
                # Ekranda İki Sütunlu Gösterim
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔹 Tek Adet İçin")
                    for color, weight in total_ink_all_colors.items():
                        st.metric(label=color, value=f"{weight:.4f} gr")
                        
                with col2:
                    st.subheader(f"🏆 Tüm Sipariş İçin ({order_qty:,} Adet)")
                    for color, total_w in grand_total.items():
                        kg_w = total_w / 1000.0
                        
                        # Reçete Hesaplamaları
                        tiner_kg = kg_w * (solvent_orani / 100.0)
                        kalan_govde_kg = kg_w - tiner_kg
                        vernik_kg = kalan_govde_kg * (vernik_orani / 100.0)
                        ham_boya_kg = kalan_govde_kg - vernik_kg
                        
                        st.metric(label=f"{color} (Toplam Kova)", value=f"{kg_w:.2f} KG")
                        st.markdown(f"""
                        * 🛢️ **Ham Boya (Çin):** {ham_boya_kg:.2f} KG
                        * 💧 **Vernik:** {vernik_kg:.2f} KG
                        * 🧪 **Tiner:** {tiner_kg:.2f} KG
                        ---
                        """)
                
                # Rapor Oluşturma ve İndirme Butonu
                report_file = "Sarfiyat_Raporu.pdf"
                create_pdf_report(report_data, report_file)
                
                st.divider()
                with open(report_file, "rb") as pdf_file:
                    st.download_button(
                        label="📥 Sonuçları PDF Raporu Olarak İndir",
                        data=pdf_file,
                        file_name=f"{uploaded_file.name}_Rapor.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
            
            os.remove(temp_pdf_path)
