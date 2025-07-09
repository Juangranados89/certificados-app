# 1) Imagen base ligera de Python
FROM python:3.11-slim

# 2) Instalamos Tesseract, Poppler y wget (para descargar el modelo)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        wget && \
    rm -rf /var/lib/apt/lists/*

# 3) Creamos el directorio donde Tesseract buscará los datos
RUN mkdir -p /usr/share/tesseract-ocr/5/tessdata

# 4) Descargamos el modelo de español directamente del repositorio oficial
RUN wget -qO /usr/share/tesseract-ocr/5/tessdata/spa.traineddata \
    https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata

# 5) Indicamos a Tesseract dónde están los datos
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# 6) Directorio de trabajo
WORKDIR /app

# 7) Instalamos dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8) Copiamos el código de la aplicación
COPY . .

# 9) Comando por defecto para arrancar la app en el puerto que Render asigna
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
