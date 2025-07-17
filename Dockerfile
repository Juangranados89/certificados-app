# Usa una imagen oficial de Python como base
FROM python:3.11-slim

# Instala las dependencias del sistema operativo para Tesseract
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa && \
    rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo
WORKDIR /app

# Copia e instala las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación
COPY . .

# ------------------- PRUEBA DE DIAGNÓSTICO -------------------
# Esta línea intenta importar tu app. Si falla, el log de construcción
# de Render mostrará el error real que está ocurriendo.
RUN python -c "import app"
# -------------------------------------------------------------

# Expone el puerto que tu app usará
EXPOSE 10000

# El comando para iniciar la aplicación de producción con Gunicorn
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:10000", "app:app"]
