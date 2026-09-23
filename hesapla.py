import subprocess
import pymupdf  # Deprecation uyarısını gidermek için güncellendi
import os
import glob
from PIL import Image

def get_page_dimensions_in_sqm(pdf_path):
    """PDF'in her sayfası için metrekare cinsinden alanı hesaplar."""
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
    """tiffsep ile belgeyi silindir (plaka) bazında renklere ayırır."""
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
    
    print("Renk ayrımları (Spot/Pantone) plakaları çıkartılıyor, lütfen bekleyin...")
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
                # tiffsep çıktısında 255 (beyaz) kağıdı, 0 (siyah) tam dolu mürekkebi temsil eder.
                # Renk yoğunluğunu doğru bulmak için (255 - piksel tonu) hesabı yapıyoruz.
                ink_value = (255 - tone) / 255.0
                total_ink += ink_value * count
                
            coverage_percent = total_ink / total_pixels
            
            # %0.01'in altındaysa o plaka boştur (Örn: kullanılmayan CMYK plakaları atlanır)
            if coverage_percent > 0.0001:
                if page_num not in coverages_by_page:
                    coverages_by_page[page_num] = {}
                coverages_by_page[page_num][color_name] = coverage_percent
                
        except Exception as e:
            print(f"Hata: {filename} dosyası analiz edilemedi. {e}")
            
    return coverages_by_page

def calculate_pantone_ink(pdf_path, ink_grams_per_sqm=5.0):
    print(f"'{pdf_path}' analiz ediliyor...\n")
    areas_sqm = get_page_dimensions_in_sqm(pdf_path)
    coverages_by_page = get_spot_coverages(pdf_path)
    
    if not coverages_by_page:
        print("Renk ayırımı yapılamadı veya belge boş.")
        return
        
    total_ink_all_colors = {}
    total_area = sum(areas_sqm)
    
    for i, area in enumerate(areas_sqm):
        page_num = i + 1
        print(f"--- Sayfa {page_num} ---")
        print(f"Sayfa Alanı: {area:.4f} m²")
        
        page_coverages = coverages_by_page.get(page_num, {})
        
        for color_name, coverage in page_coverages.items():
            covered_area = area * coverage
            ink_weight = covered_area * ink_grams_per_sqm
            
            if color_name not in total_ink_all_colors:
                total_ink_all_colors[color_name] = 0.0
            total_ink_all_colors[color_name] += ink_weight
            
            print(f"{color_name}: %{coverage*100:.2f} kaplama -> {ink_weight:.4f} gram")
        print("")
        
    print(f"=== TOPLAM SONUÇ (Tamamı {total_area:.4f} m² olan belge için) ===")
    print(f"Hesaplama Kriteri: %100 dolu alan için {ink_grams_per_sqm} gr/m²")
    for color, weight in total_ink_all_colors.items():
        print(f"Toplam {color} Mürekkebi: {weight:.4f} gram")

pdf_dosya_yolu = "murekkepsarf.pdf" 
calculate_pantone_ink(pdf_dosya_yolu, ink_grams_per_sqm=5.0)