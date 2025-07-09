import os
import zipfile
import shutil
import re
import unicodedata
import pandas as pd
import time
from PIL import Image, ImageOps, ImageFilter
from pdf2image import convert_from_path
import pytesseract

# === AUXILIARY FUNCTIONS ===

def normalize(text: str) -> str:
    """Remove accents and uppercase."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()

def preprocess(img: Image.Image) -> Image.Image:
    """Convert to grayscale, auto‐contrast, binarize and denoise."""
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=2)
    bw = gray.point(lambda x: 0 if x < 160 else 255, '1')
    return bw.filter(ImageFilter.MedianFilter(size=3))

def ocr_text(pdf_path: str, dpi: int = 200) -> str:
    """Render first page of PDF as image and run Tesseract OCR."""
    images = convert_from_path(pdf_path, dpi=dpi)
    img = images[0]
    proc = preprocess(img)
    config = (
        r'--psm 6 '
        r'-c tessedit_char_whitelist='
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwx' 
        'yzÁÉÍÓÚÑáéíóúñ0123456789./-'
    )
    return pytesseract.image_to_string(proc, lang='spa', config=config)

def extract_info(text: str):
    """
    From OCR’d text, extract:
      - nombre
      - cc
      - nivel (ENTRANTE, VIGIA, SUPERVISOR)
      - fecha (DD/MM/YYYY or similar)
    """
    nombre = cc = nivel = fecha = ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        ln = normalize(line)
        # Nivel
        if not nivel:
            if 'ENTRANTE' in ln:
                nivel = 'ENTRANTE'
                continue
            if 'VIGIA' in ln or 'VIGILANTE' in ln:
                nivel = 'VIGIA'
                continue
            if 'SUPERVISOR' in ln:
                nivel = 'SUPERVISOR'
                continue
        # Cédula
        if not cc:
            m = re.search(r'\b(?:CC|CEDULA)[:\s]*([\d\.]{6,15})\b', ln, re.I)
            if m:
                cc = m.group(1).replace('.', '')
                continue
        # Nombre
        if not nombre:
            m = re.search(r'\bNOMBRE[:\s]*([A-ZÁÉÍÓÚÑ ]{4,})\b', ln, re.I)
            if m:
                nombre = m.group(1).title()
                continue
        # Fecha
        if not fecha:
            m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', ln)
            if m:
                fecha = m.group(1)
                continue
    # Fallbacks
    return (
        nombre or "NoDetectado",
        cc or "NoDetectado",
        nivel or "DESCONOCIDO",
        fecha
    )

# === CONFIGURATION ===

zip_path    = '/mnt/data/confinados_batch1_renamed.zip'
workspace   = '/mnt/data/organized_batch1'
extract_dir = os.path.join(workspace, 'extract')

level_dirs = {
    'ENTRANTE':    os.path.join(workspace, 'Nivel_Entrante'),
    'VIGIA':       os.path.join(workspace, 'Nivel_Vigia'),
    'SUPERVISOR':  os.path.join(workspace, 'Nivel_Supervisor'),
}
unknown_dir = os.path.join(workspace, 'Nivel_Desconocido')

# === PREPARE WORKSPACE ===

if os.path.exists(workspace):
    shutil.rmtree(workspace)
for d in level_dirs.values():
    os.makedirs(d, exist_ok=True)
os.makedirs(unknown_dir, exist_ok=True)
os.makedirs(extract_dir, exist_ok=True)

# === EXTRACT PDFs FROM ZIP ===

with zipfile.ZipFile(zip_path, 'r') as zf:
    pdf_files = [fn for fn in zf.namelist() if fn.lower().endswith('.pdf')]
    zf.extractall(path=extract_dir)

# === PROCESS EACH PDF ===

records = []
start = time.time()

for filename in pdf_files:
    src = os.path.join(extract_dir, filename)
    text = ocr_text(src, dpi=200)
    nombre, cc, nivel, fecha = extract_info(text)

    # Determine destination folder
    dest_dir = level_dirs.get(nivel, unknown_dir)
    os.makedirs(dest_dir, exist_ok=True)

    # Build destination filename
    safe_name = f"{nombre}_{cc}.pdf".replace(" ", "_")
    dest_path = os.path.join(dest_dir, safe_name)

    # Avoid name collisions
    base, ext = os.path.splitext(dest_path)
    i = 1
    while os.path.exists(dest_path):
        dest_path = f"{base}_{i}{ext}"
        i += 1

    shutil.copy(src, dest_path)
    records.append({
        "PDF": filename,
        "Nivel": nivel,
        "Nombre": nombre,
        "CC": cc,
        "Fecha": fecha
    })

elapsed = time.time() - start

# === GENERATE SUMMARY EXCEL ===

df = pd.DataFrame(records)
summary_path = os.path.join(workspace, 'summary_batch1.xlsx')
df.to_excel(summary_path, index=False)
print(f"Resumen guardado en Excel: {summary_path}")

# === CREATE ORGANIZED ZIP ===

zip_output = '/mnt/data/batch1_by_level.zip'
if os.path.exists(zip_output):
    os.remove(zip_output)

with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zout:
    for lvl, dirpath in list(level_dirs.items()) + [('DESCONOCIDO', unknown_dir)]:
        for root, _, files in os.walk(dirpath):
            for f in files:
                absf = os.path.join(root, f)
                relf = os.path.relpath(absf, workspace)
                zout.write(absf, arcname=relf)

print(f"Procesados {len(records)} PDFs en {elapsed:.1f}s")
print(f"ZIP organizado creado en: {zip_output}")
