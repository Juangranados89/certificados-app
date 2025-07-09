import os
import zipfile
import shutil
import fitz      # PyMuPDF
import re
import unicodedata
import pandas as pd
import time
from PIL import Image, ImageOps, ImageFilter
import pytesseract
import ace_tools as tools

# === FUNCIONES AUXILIARES ===

def normalize(text: str) -> str:
    """Quita tildes y pasa a mayúsculas."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()

def preprocess(img: Image.Image) -> Image.Image:
    """Escala a gris, binariza y filtra ruido."""
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=2)
    bw = gray.point(lambda x: 0 if x < 160 else 255, '1')
    return bw.filter(ImageFilter.MedianFilter(size=3))

def ocr_text(pdf_path: str, dpi: int = 200) -> str:
    """Renderiza la primera página y devuelve el texto OCR."""
    doc = fitz.open(pdf_path)
    pix = doc.load_page(0).get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    proc = preprocess(img)
    # --psm 6 agrupa líneas, whitelist reduce errores
    config = r'--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÁÉÍÓÚÑáéíóúñ0123456789./-'
    return pytesseract.image_to_string(proc, lang='spa', config=config)

def extract_info(text: str):
    """
    Busca línea a línea Nivel, Nombre, CC y (opcional) Fecha.
    Devuelve tupla: (nombre, cc, nivel, fecha)
    """
    nombre = cc = nivel = fecha = ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        ln = normalize(line)
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
        if not cc:
            m = re.search(r'\b(?:CC|CEDULA)[:\s]*([0-9\.]{6,15})\b', ln, re.I)
            if m:
                cc = m.group(1).replace('.', '')
                continue
        if not nombre:
            m = re.search(r'\bNOMBRE[:\s]*([A-ZÁÉÍÓÚÑ ]{4,})\b', ln, re.I)
            if m:
                nombre = m.group(1).title()
                continue
        if not fecha:
            m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', ln)
            if m:
                fecha = m.group(1)
                continue
    return nombre or "NoDetectado", cc or "NoDetectado", nivel or "DESCONOCIDO", fecha

# === PARÁMETROS ===
zip_path    = '/mnt/data/confinados_batch1_renamed.zip'
workspace   = '/mnt/data/organized_batch1'
extract_dir = os.path.join(workspace, 'extract')
level_dirs = {
    'ENTRANTE': os.path.join(workspace, 'Nivel_Entrante'),
    'VIGIA':    os.path.join(workspace, 'Nivel_Vigia'),
    'SUPERVISOR': os.path.join(workspace, 'Nivel_Supervisor'),
}
unknown_dir = os.path.join(workspace, 'Nivel_Desconocido')

# === PREPARAR ESPACIOS ===
if os.path.exists(workspace):
    shutil.rmtree(workspace)
for d in level_dirs.values():
    os.makedirs(d, exist_ok=True)
os.makedirs(unknown_dir, exist_ok=True)
os.makedirs(extract_dir, exist_ok=True)

# === EXTRAER PDFs DEL ZIP ===
with zipfile.ZipFile(zip_path, 'r') as zf:
    pdf_files = [n for n in zf.namelist() if n.lower().endswith('.pdf')]
    zf.extractall(path=extract_dir)

# === PROCESAR CADA PDF ===
records = []
start = time.time()
for file in pdf_files:
    src = os.path.join(extract_dir, file)
    text = ocr_text(src, dpi=200)
    nombre, cc, nivel, fecha = extract_info(text)

    # Carpeta destino
    dest_dir = level_dirs.get(nivel, unknown_dir)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{nombre}_{cc}.pdf")

    # Evitar colisiones
    base, ext = os.path.splitext(dest_path)
    i = 1
    while os.path.exists(dest_path):
        dest_path = f"{base}_{i}{ext}"
        i += 1

    shutil.copy(src, dest_path)
    records.append({
        "PDF": file,
        "Nivel": nivel,
        "Nombre": nombre,
        "CC": cc,
        "Fecha": fecha
    })

elapsed = time.time() - start

# === GENERAR RESUMEN & ZIP ===
df = pd.DataFrame(records)
tools.display_dataframe_to_user(name="Resumen Batch 1", dataframe=df)

summary_excel = os.path.join(workspace, 'summary_batch1.xlsx')
df.to_excel(summary_excel, index=False)

zip_output = '/mnt/data/batch1_by_level.zip'
with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zout:
    for lvl, dirpath in list(level_dirs.items()) + [('DESCONOCIDO', unknown_dir)]:
        for root, _, files in os.walk(dirpath):
            for f in files:
                absf = os.path.join(root, f)
                relf = os.path.relpath(absf, workspace)
                zout.write(absf, arcname=relf)

print(f"Procesados {len(records)} PDFs en {elapsed:.1f}s")
print("Excel resumen:", summary_excel)
print("ZIP organizado:", zip_output)

