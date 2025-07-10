import os
import re
import zipfile
import shutil
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageOps, ImageFilter
import unicodedata

def normalize(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()

def preprocess_image(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=2)
    bw = gray.point(lambda x: 0 if x < 160 else 255, '1')
    return bw.filter(ImageFilter.MedianFilter(size=3))

def extract_info_from_image(img: Image.Image):
    config = (
        r'--psm 6 '
        r'-c tessedit_char_whitelist='
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789./-'
    )
    text = pytesseract.image_to_string(img, lang='spa', config=config)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    nombre = cc = nivel = fecha = ""
    for line in lines:
        ln = normalize(line)

        if not nivel:
            if 'ENTRANTE' in ln:
                nivel = 'ENTRANTE'; continue
            if 'VIGIA' in ln or 'VIGILANTE' in ln:
                nivel = 'VIGIA'; continue
            if 'SUPERVISOR' in ln:
                nivel = 'SUPERVISOR'; continue

        if not cc:
            m = re.search(r'\bC\.?C\.?[:\s]*([0-9]{6,15})\b', line, re.I)
            if m:
                cc = m.group(1).strip(); continue

        if not nombre:
            m = re.search(r'\bNOMBRE[:\s]*([A-Z ]{4,})\b', ln, re.I)
            if m:
                nombre = m.group(1).title().strip(); continue

        if not fecha:
            m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', ln)
            if m:
                fecha = m.group(1); continue

    # Fallbacks simples
    if not cc:
        m2 = re.search(r'\b([0-9]{7,15})\b', text)
        cc = m2.group(1) if m2 else "NODETECT"
    if not nombre:
        nombre = "NODETECT"
    if not nivel:
        nivel = "DESCONOCIDO"

    return nombre, cc, nivel, fecha

def process_single_pdf(pdf_path: str, output_dir: str) -> dict:
    images = convert_from_path(pdf_path, dpi=300)
    img = images[0]
    proc = preprocess_image(img)
    nombre, cc, nivel, fecha = extract_info_from_image(proc)

    # Renombrado UPPERCASE y underscores
    slug = f"{nombre}_{cc}".replace(" ", "_").upper()
    new_name = f"{slug}.PDF"

    folder = nivel if nivel != "DESCONOCIDO" else "SIN_NIVEL"
    dest_dir = os.path.join(output_dir, f"NIVEL_{folder}")
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, new_name)
    shutil.copy2(pdf_path, dest_path)

    return {
        "CC": cc,
        "NOMBRE": nombre,
        "NIVEL": nivel,
        "FECHA": fecha,
        "ARCHIVO": f"NIVEL_{folder}/{new_name}"
    }

def process_pdfs(pdf_paths: list[str], output_dir: str):
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    registros = [ process_single_pdf(p, output_dir) for p in pdf_paths ]

    zip_path = os.path.join(output_dir, "CERTIFICADOS_ORGANIZADOS.ZIP")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _, files in os.walk(output_dir):
            for f in files:
                if f.upper().endswith(".PDF"):
                    absf = os.path.join(root, f)
                    relf = os.path.relpath(absf, output_dir)
                    zf.write(absf, arcname=relf)

    df = pd.DataFrame(registros)
    return df, zip_path
