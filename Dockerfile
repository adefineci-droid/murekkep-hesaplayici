# Temel işletim sistemi ve Python sürümü
FROM python:3.11-slim

# Sisteme Ghostscript kurulumu (En kritik adım)
RUN apt-get update && apt-get install -y ghostscript && rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Kütüphaneleri kopyala ve kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodlarını (app.py) kopyala
COPY . .

# Streamlit'in çalışacağı portu dışa aç
EXPOSE 8501

# Uygulamayı başlat
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]