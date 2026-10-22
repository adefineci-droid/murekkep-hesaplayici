import streamlit as st
import subprocess
import pymupdf
import os
import glob
from PIL import Image
from fpdf import FPDF
import tempfile
import json

# Sayfa Ayarları
st.set_page_config(page_title="Mürekkep Sarfiyat Analizi", page_icon="🎨", layout="wide")

CONFIG_FILE = "ayarlar.json"

# Varsayılan Ayarlar
DEFAULT_CONFIG = {
    "ink_grams": 5.08,
    "solvent_orani": 20,
    "vernik_orani": 50,
    "t_etil": 50,
    "t_npropil": 30,
    "t_pm": 10,
    "t_izopropil": 10,
    "t_butil": 0,
    "price_boya": 3.60,
    "price_vernik": 2.60,
    "price_etil": 1.00,
    "price_npropil": 1.20,
    "price_pm": 1.50,
    "price_izopropil": 1.10,
    "price_butil": 1.30
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)

def tr_to_eng(text):
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
    
    total_islak_kg = 0
    total_ham_boya_kg = 0
    total_vernik_kg = 0
    total_tiner_kg = 0
    
    for color_name, weight in data['grand_total_ink'].items():
        kg_weight = weight / 1000.0
        tiner_kg = kg_weight * (data['solvent'] / 100.0)
        kalan_govde = kg_weight - tiner_kg
        vernik_kg = kalan_govde * (data['vernik'] / 100.0)
        ham_boya_kg = kalan_govde - vernik_kg
        
        total_islak_kg += kg_weight
        total_ham_boya_kg += ham_boya_kg
        total_vernik_kg += vernik_kg
        total_tiner_kg += tiner_kg
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, tr_to_eng(f"[{color_name}] Toplam Kova (Islak): {kg_weight:.2f} KG"), ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 6, tr_to_eng(f"   -> Ham Boya (Cinden): {ham_boya_kg:.2f} KG"), ln=True)
        pdf.cell(0, 6, tr_to_eng(f"   -> Vernik: {vernik_kg:.2f} KG"), ln=True)
        pdf.cell(0, 6, tr_to_eng(f"   -> Tiner Karisimi: {tiner_kg:.2f} KG"), ln=True)
        pdf.ln(3)
        
    # EN ALT KISIM: TÜM SİPARİŞİN GENEL TOPLAMI
    pdf.ln(5)
    pdf.set_fill_color(200, 220, 255)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, tr_to_eng("TUM RENKLER ICIN GENEL TOPLAM (DEPO CIKISI)"), ln=True, fill=True)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, tr_to_eng(f"TOPLAM ISLAK KARISIM: {total_islak_kg:.2f} KG"), ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 7, tr_to_eng(f"Toplam Ham Boya (Cinden): {total_ham_boya_kg:.2f} KG"), ln=True)
    pdf.cell(0, 7, tr_to_eng(f"Toplam Vernik Ihtiyaci: {total_vernik_kg:.2f} KG"), ln=True)
    pdf.cell(0, 7, tr_to_eng(f"Toplam Tiner Ihtiyaci: {total_tiner_kg:.2f} KG"), ln=True)
    
    if total_tiner_kg > 0:
        pdf.set_font("Arial", "I", 11)
        for t_name, t_pct in data['tiner_detay'].items():
            if t_pct > 0:
                t_miktar = total_tiner_kg * (t_pct / 100.0)
                pdf.cell(0, 6, tr_to_eng(f"    - {t_name} (%{t_pct}): {t_miktar:.2f} KG"), ln=True)
    
    # MALIYET ANALIZI
    pdf.ln(5)
    pdf.set_fill_color(220, 255, 220)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, tr_to_eng("MALIYET ANALIZI (USD)"), ln=True, fill=True)
    pdf.set_font("Arial", "", 12)
    
    pdf.cell(0, 7, tr_to_eng(f"Ham Boya Maliyeti: ${data['costs']['ham_boya']:.2f} (Birim: ${data['prices']['boya']:.2f}/KG)"), ln=True)
    pdf.cell(0, 7, tr_to_eng(f"Vernik Maliyeti: ${data['costs']['vernik']:.2f} (Birim: ${data['prices']['vernik']:.2f}/KG)"), ln=True)
    pdf.cell(0, 7, tr_to_eng(f"Tiner Karisimi Maliyeti: ${data['costs']['tiner']:.2f}"), ln=True)
    
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, tr_to_eng(f"TOPLAM MUREKKEP & SOLVENT MALIYETI: ${data['costs']['toplam']:.2f}"), ln=True)
    
    pdf.output(filename)

# --- ARAYÜZ (UI) TASARIMI ---
st.title("🎨 Pusula Basım - Üretim ve Maliyet Analiz Sistemi")
cfg = load_config()

# Sekmeli (Tab) Yapı
tab1, tab2 = st.tabs(["🚀 Analiz ve Raporlama", "⚙️ Sistem ve Reçete Ayarları"])

with tab2:
    st.header("Sistem Ayarları")
    st.markdown("Burada yaptığınız değişiklikler kaydedilir ve tüm analizlerde varsayılan olarak kullanılır.")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Baskı Standartları")
        ink_grams = st.number_input("%100 Dolulukta Gramaj (gr/m²)", min_value=0.1, value=float(cfg['ink_grams']), step=0.01)
        solvent_orani = st.slider("Tiner (Solvent) Payı (%)", min_value=0, max_value=50, value=int(cfg['solvent_orani']), step=1)
        vernik_orani = st.slider("Vernik (Extender) Payı (%)", min_value=0, max_value=80, value=int(cfg['vernik_orani']), step=5)
        
    with c2:
        st.subheader("Tiner Karışım Oranları (%)")
        t_etil = st.number_input("Etil Asetat (%)", min_value=0, max_value=100, value=int(cfg['t_etil']), step=5)
        t_npropil = st.number_input("n-Propil Asetat (%)", min_value=0, max_value=100, value=int(cfg['t_npropil']), step=5)
        t_pm = st.number_input("PM (Propylene Glycol) (%)", min_value=0, max_value=100, value=int(cfg['t_pm']), step=5)
        t_izopropil = st.number_input("İzopropil Alkol (%)", min_value=0, max_value=100, value=int(cfg['t_izopropil']), step=5)
        t_butil = st.number_input("Butil Asetat (%)", min_value=0, max_value=100, value=int(cfg['t_butil']), step=5)
        
        toplam_t = t_etil + t_npropil + t_pm + t_izopropil + t_butil
        if toplam_t != 100:
            st.error(f"HATA: Toplam %{toplam_t}. Lütfen %100'e tamamlayın!")
            
    with c3:
        st.subheader("Birim Fiyatlar (USD/KG)")
        price_boya = st.number_input("Ham Boya Fiyatı", min_value=0.0, value=float(cfg['price_boya']), step=0.10)
        price_vernik = st.number_input("Vernik Fiyatı", min_value=0.0, value=float(cfg['price_vernik']), step=0.10)
        price_etil = st.number_input("Etil Asetat Fiyatı", min_value=0.0, value=float(cfg['price_etil']), step=0.10)
        price_npropil = st.number_input("n-Propil Asetat Fiyatı", min_value=0.0, value=float(cfg['price_npropil']), step=0.10)
        price_pm = st.number_input("PM Fiyatı", min_value=0.0, value=float(cfg['price_pm']), step=0.10)
        price_izopropil = st.number_input("İzopropil Alkol Fiyatı", min_value=0.0, value=float(cfg['price_izopropil']), step=0.10)
        price_butil = st.number_input("Butil Asetat Fiyatı", min_value=0.0, value=float(cfg['price_butil']), step=0.10)

    if st.button("💾 Ayarları Kaydet", type="primary"):
        if toplam_t == 100:
            new_config = {
                "ink_grams": ink_grams, "solvent_orani": solvent_orani, "vernik_orani": vernik_orani,
                "t_etil": t_etil, "t_npropil": t_npropil, "t_pm": t_pm, "t_izopropil": t_izopropil, "t_butil": t_butil,
                "price_boya": price_boya, "price_vernik": price_vernik, "price_etil": price_etil,
                "price_npropil": price_npropil, "price_pm": price_pm, "price_izopropil": price_izopropil, "price_butil": price_butil
            }
            save_config(new_config)
            st.success("Ayarlar başarıyla kaydedildi! Analiz sekmesine geçebilirsiniz.")
        else:
            st.error("Tiner oranları toplamı %100 olmadan ayarlar kaydedilemez.")

with tab1:
    st.markdown("Dosyanızı yükleyin ve güncel ayarlarla üretimi planlayın.")
    
    col_file, col_qty = st.columns([3, 1])
    with col_file:
        uploaded_file = st.file_uploader("Lütfen PDF baskı dosyasını yükleyin", type=["pdf"])
    with col_qty:
        order_qty = st.number_input("Sipariş Miktarı (Adet)", min_value=1, value=50000, step=1000)

    # Aktif konfigürasyon üzerinden hesaplama kontrolü
    toplam_tiner_yuzde = cfg['t_etil'] + cfg['t_npropil'] + cfg['t_pm'] + cfg['t_izopropil'] + cfg['t_butil']
    
    if uploaded_file is not None:
        if toplam_tiner_yuzde != 100:
             st.error("Ayarlar sekmesindeki tiner oranları toplamı %100 değil. Lütfen düzeltin.")
        else:
            if st.button("🚀 Analizi Başlat", type="primary", use_container_width=True):
                with st.spinner('Renk plakaları ayrıştırılıyor ve maliyet hesaplanıyor...'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                        temp_pdf.write(uploaded_file.read())
                        temp_pdf_path = temp_pdf.name
                    
                    areas_sqm = get_page_dimensions_in_sqm(temp_pdf_path)
                    coverages_by_page = get_spot_coverages(temp_pdf_path)
                    
                    if not coverages_by_page:
                        st.warning("Belgede analiz edilecek renk bulunamadı.")
                    else:
                        total_ink_all_colors = {}
                        total_area = sum(areas_sqm)
                        
                        report_data = {
                            'filename': uploaded_file.name,
                            'criteria': cfg['ink_grams'],
                            'order_qty': order_qty,
                            'total_area': total_area,
                            'pages': [],
                            'total_ink': {},
                            'grand_total_ink': {},
                            'solvent': cfg['solvent_orani'],
                            'vernik': cfg['vernik_orani'],
                            'tiner_detay': {
                                'Etil Asetat': cfg['t_etil'], 'n-Propil Asetat': cfg['t_npropil'],
                                'PM (Propylene Glycol)': cfg['t_pm'], 'Izopropil Alkol': cfg['t_izopropil'], 'Butil Asetat': cfg['t_butil']
                            },
                            'prices': {
                                'boya': cfg['price_boya'], 'vernik': cfg['price_vernik'],
                                'tiner_bilesenler': {
                                    'Etil Asetat': cfg['price_etil'], 'n-Propil Asetat': cfg['price_npropil'],
                                    'PM (Propylene Glycol)': cfg['price_pm'], 'Izopropil Alkol': cfg['price_izopropil'], 'Butil Asetat': cfg['price_butil']
                                }
                            },
                            'costs': {}
                        }
                        
                        st.subheader("📊 Sayfa Bazlı Analiz (Tek Adet İçin)")
                        
                        for i, area in enumerate(areas_sqm):
                            page_num = i + 1
                            page_coverages = coverages_by_page.get(page_num, {})
                            
                            with st.expander(f"📄 Sayfa {page_num} (Alan: {area:.4f} m²)", expanded=True):
                                page_info = {'page_num': page_num, 'area': area, 'colors': []}
                                for color_name, coverage in page_coverages.items():
                                    covered_area = area * coverage
                                    ink_weight = covered_area * cfg['ink_grams']
                                    if color_name not in total_ink_all_colors:
                                        total_ink_all_colors[color_name] = 0.0
                                    total_ink_all_colors[color_name] += ink_weight
                                    st.write(f"**{color_name}:** %{coverage*100:.2f} yoğunluk ➔ **{ink_weight:.4f} gram**")
                                    page_info['colors'].append({'name': color_name, 'coverage': coverage*100, 'weight': ink_weight})
                                report_data['pages'].append(page_info)
                        
                        report_data['total_ink'] = total_ink_all_colors
                        grand_total = {color: weight * order_qty for color, weight in total_ink_all_colors.items()}
                        report_data['grand_total_ink'] = grand_total
                        
                        st.divider()
                        st.subheader("📦 Tüm Renkler İçin Genel Toplam İhtiyaç (Depo Çıkışı)")
                        
                        t_islak = sum([w/1000.0 for w in grand_total.values()])
                        t_tiner = t_islak * (cfg['solvent_orani'] / 100.0)
                        t_govde = t_islak - t_tiner
                        t_vernik = t_govde * (cfg['vernik_orani'] / 100.0)
                        t_ham = t_govde - t_vernik
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Toplam Islak Karışım", f"{t_islak:.2f} KG")
                        c2.metric("Toplam Ham Boya", f"{t_ham:.2f} KG")
                        c3.metric("Toplam Vernik", f"{t_vernik:.2f} KG")
                        c4.metric("Toplam Tiner Karışımı", f"{t_tiner:.2f} KG")
                        
                        cost_ham_boya = t_ham * cfg['price_boya']
                        cost_vernik = t_vernik * cfg['price_vernik']
                        cost_tiner = 0.0
                        
                        if t_tiner > 0:
                            with st.expander("🧪 Tiner Alt Bileşenleri (Detaylı KG ve Maliyet)"):
                                for t_name, t_pct in report_data['tiner_detay'].items():
                                    if t_pct > 0:
                                        t_miktar = t_tiner * (t_pct / 100.0)
                                        b_fiyat = report_data['prices']['tiner_bilesenler'][t_name]
                                        b_cost = t_miktar * b_fiyat
                                        cost_tiner += b_cost
                                        st.write(f"- **{t_name} (%{t_pct}):** {t_miktar:.2f} KG ( ${b_cost:.2f} )")
                                        
                        total_cost = cost_ham_boya + cost_vernik + cost_tiner
                        
                        report_data['costs'] = {
                            'ham_boya': cost_ham_boya, 'vernik': cost_vernik, 'tiner': cost_tiner, 'toplam': total_cost
                        }
                        
                        st.divider()
                        st.subheader("💰 Maliyet Analizi (USD)")
                        mc1, mc2, mc3, mc4 = st.columns(4)
                        mc1.metric("Ham Boya Maliyeti", f"${cost_ham_boya:,.2f}")
                        mc2.metric("Vernik Maliyeti", f"${cost_vernik:,.2f}")
                        mc3.metric("Tiner Maliyeti", f"${cost_tiner:,.2f}")
                        mc4.metric("TOPLAM MALIYET", f"${total_cost:,.2f}")
                        
                        report_file = "Sarfiyat_Raporu.pdf"
                        create_pdf_report(report_data, report_file)
                        
                        st.divider()
                        with open(report_file, "rb") as pdf_file:
                            st.download_button(
                                label="📥 Sonuçları PDF Raporu Olarak İndir",
                                data=pdf_file,
                                file_name=f"{uploaded_file.name}_Rapor.pdf",
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True
                            )
                    
                    os.remove(temp_pdf_path)
