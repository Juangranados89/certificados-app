# Usa una imagen oficial de Python como base
# python:3.11-slim es una versión ligera y eficiente
FROM python:3.11-slim

# Instala las dependencias del sistema operativo para Tesseract OCR
# Esto permite que tu aplicación pueda "leer" el texto de las imágenes
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa && \
    rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo dentro del contenedor
# Todas las operaciones siguientes se ejecutarán desde /app
WORKDIR /app

# Copia el archivo de requerimientos y los instala
# Esto se hace en un paso separado para aprovechar el caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación al contenedor
COPY . .

# ------------------- PRUEBA DE DIAGNÓSTICO -------------------
# Esta línea intenta importar tu app. Si falla, el log de construcción
# de Render mostrará el error real que está ocurriendo.
# Si el despliegue es exitoso, puedes comentar o eliminar esta línea.
RUN python -c "import app"
# -------------------------------------------------------------

# Expone el puerto que tu app usará.
# Debe coincidir con el puerto en tu render.yaml y en el comando CMD.
EXPOSE 10000

# El comando para iniciar la aplicación de producción con Gunicorn.
# app:app significa: en el archivo "app.py", encuentra y ejecuta la variable "app".
# --workers 2: Inicia 2 procesos para manejar peticiones en paralelo.
# --bind 0.0.0.0:10000: Escucha en el puerto 10000 en todas las interfaces de red.
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:10000", "app:app"]
