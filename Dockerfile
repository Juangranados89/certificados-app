# Dockerfile para FastAPI + OCR en Render.com

# 1) Imagen base ligera de Python
FROM python:3.11-slim

# 2) Instalamos Tesseract, datos de español y Poppler
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \          # motor OCR
      tesseract-ocr-spa \      # datos de idioma español
      poppler-utils \          # para pdf2image \
 && rm -rf /var/lib/apt/lists/* \
 \
 # 3) Creamos el path que Tesseract espera y copiamos los .traineddata
 && mkdir -p /usr/share/tesseract-ocr/5/tessdata \
 && cp /usr/share/tessdata/*.traineddata /usr/share/tesseract-ocr/5/tessdata/

# 4) Ajustamos dónde buscar los datos de idioma
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# 5) Directorio de trabajo
WORKDIR /app

# 6) Instalamos dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7) Copiamos el resto del código
COPY . .

# 8) Arrancamos Uvicorn en el puerto que Render expone
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]

