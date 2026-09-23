import subprocess
import fitz  # PyMuPDF
import re
import os

def get_page_dimensions_in_sqm(pdf_path):
    """PDF'in her sayfası için metrekare cinsinden alanı hesaplar."""
    doc = fitz.open(pdf_path)
    areas = []
    
    for page in doc:
        rect = page.rect
        # PDF noktalarını (points) inç'e (1 inç = 72 point), sonra metreye çeviriyoruz (1 inç = 0.0254 metre)
        width_m = (rect.width / 72.0) * 0.0254
        height_m = (rect.height / 72.0) * 0.0254
        area_sqm = width_m * height_m
        areas.append(area_sqm)
        
    doc.close()
    return areas

def get_ink_coverage(pdf_path):
    """Ghostscript kullanarak CMYK renklerin kaplama yüzdelerini alır."""
    # Ghostscript komutu (Windows'ta 'gswin64c' veya 'gswin32c' olabilir, Linux/Mac'te 'gs')
    gs_cmd = 'gs' if os.name != 'nt' else 'gswin64c'
    
    cmd = [
        gs_cmd, '-q', '-o', '-', '-sDEVICE=inkcov', pdf_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("Hata: Ghostscript sisteminizde yüklü değil veya PATH'e eklenmemiş.")
        return []
        
    output = result.stdout.strip().split('\n')
    coverages = []
    
    # Çıktı formatı: " 0.05203  0.10301  0.00000  0.02100 CMYK OK"
    for line in output:
        match = re.search(r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+CMYK OK', line)
        if match:
            # Ghostscript 0.0 ile 1.0 arası değer döndürür (1.0 = %100 kaplama)
            c, m, y, k = [float(x) for x in match.groups()]
            coverages.append({'Cyan': c, 'Magenta': m, 'Yellow': y, 'Black': k})
            
    return coverages

def calculate_ink_consumption(pdf_path, ink_grams_per_sqm=5.0):
    """Tüm belge için renk bazında mürekkep tüketimini gram olarak hesaplar."""
    print(f"'{pdf_path}' analiz ediliyor...\n")
    
    areas_sqm = get_page_dimensions_in_sqm(pdf_path)
    coverages = get_ink_coverage(pdf_path)
    
    if not coverages:
        print("Mürekkep verisi alınamadı.")
        return
        
    total_ink = {'Cyan': 0.0, 'Magenta': 0.0, 'Yellow': 0.0, 'Black': 0.0}
    total_area = sum(areas_sqm)
    
    for i, (area, coverage) in enumerate(zip(areas_sqm, coverages)):
        print(f"--- Sayfa {i+1} ---")
        print(f"Sayfa Alanı: {area:.4f} m²")
        
        for color in total_ink.keys():
            # Sayfadaki o rengin dolu (kaplanmış) alanı
            covered_area = area * coverage[color]
            # Gram cinsinden ağırlığı
            ink_weight = covered_area * ink_grams_per_sqm
            total_ink[color] += ink_weight
            
            print(f"{color}: %{coverage[color]*100:.2f} kaplama -> {ink_weight:.4f} gram")
        print("")
        
    print(f"=== TOPLAM SONUÇ (Tamamı {total_area:.4f} m² olan belge için) ===")
    print(f"Hesaplama Kriteri: %100 dolu alan için {ink_grams_per_sqm} gr/m²")
    for color, weight in total_ink.items():
        print(f"Toplam {color} Mürekkebi: {weight:.4f} gram")

# Kullanım:
# Kendi PDF dosyanızın yolunu aşağıya yazın.
pdf_dosya_yolu = "ornek_baski_dosyasi.pdf" 
# calculate_ink_consumption(pdf_dosya_yolu, ink_grams_per_sqm=5.0)