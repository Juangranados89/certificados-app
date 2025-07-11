# --- certificados-app Dockerfile ---
FROM python:3.11-slim

# ---------- SO ----------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

# ---------- Python ----------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Código ----------
COPY . .

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["flask", "run", "--host=0.0.0.0", "--port=8000"]
