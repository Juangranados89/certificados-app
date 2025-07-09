# Dockerfile para FastAPI + OCR en Render.com con descarga manual de spa.traineddata

# 1) Imagen base ligera de Python
FROM python:3.11-slim

# 2) Instalamos Tesseract, Poppler y wget para descarga
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \         # motor OCR
      poppler-utils \         # para pdf2image
      wget \                  # para descargar spa.traineddata
    && rm -rf /var/lib/apt/lists/*

# 3) Creamos el directorio donde Tesseract busca los .traineddata
RUN mkdir -p /usr/share/tesseract-ocr/5/tessdata

# 4) Descargamos el spa.traineddata oficial
RUN wget -qO /usr/share/tesseract-ocr/5/tessdata/spa.traineddata \
      https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata

# 5) Apuntamos Tesseract a ese directorio
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# 6) Directorio de trabajo
WORKDIR /app

# 7) Instalamos dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8) Copiamos el código de la app
COPY . .

# 9) Comando de arranque
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]


