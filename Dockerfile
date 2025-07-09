# Dockerfile para FastAPI + OCR en Render.com (corregido)

# 1) Imagen base ligera de Python
FROM python:3.11-slim

# 2) Instalamos Tesseract, datos de español y Poppler, y preparamos el tessdata
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr \
      tesseract-ocr-spa \
      poppler-utils && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /usr/share/tesseract-ocr/5/tessdata && \
    cp /usr/share/tessdata/*.traineddata /usr/share/tesseract-ocr/5/tessdata

# 3) Ajustamos dónde buscar los datos de idioma
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# 4) Directorio de trabajo dentro del contenedor
WORKDIR /app

# 5) Copiamos e instalamos las dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6) Copiamos el resto del código de la aplicación
COPY . .

# 7) Comando por defecto para arrancar la app:
#    Uvicorn escucha en 0.0.0.0 (todas las interfaces) en el puerto que Render define
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]

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

