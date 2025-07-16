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
# Añade gunicorn a los requerimientos y luego instala todo
RUN echo "gunicorn==22.0.0" >> requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación
COPY . .

# Expone el puerto que Render usará (definido en render.yaml)
EXPOSE 10000

# El comando para iniciar la aplicación de forma robusta con Gunicorn.
# Le dice a Gunicorn que busque la variable 'app' en el archivo 'app.py'.
# Respeta automáticamente la variable de entorno PORT que Render proporciona.
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:10000", "app:app"]
