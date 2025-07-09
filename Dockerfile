# 1) Imagen base ligera de Python
FROM python:3.11-slim

# 2) Instalamos paquetes de sistema necesarios:
#    - tesseract-ocr: motor OCR
#    - poppler-utils: para convertir PDF en imágenes
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      poppler-utils \
 && rm -rf /var/lib/apt/lists/*

# 3) Directorio de trabajo dentro del contenedor
WORKDIR /app

# 4) Copiamos y instalamos las dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) Copiamos todo el código del proyecto
COPY . .

# 6) Orden por defecto para arrancar la app:
#    - Uvicorn escucha en 0.0.0.0 (todas las interfaces)
#    - Puerto en $PORT (Render lo define)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
