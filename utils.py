# utils.py

import os
import re
import zipfile
import shutil
import unicodedata

import pandas as pd
import pytesseract
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
import wordninja
from pytesseract import Output

def normalize(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()

def split_name(concat: str) -> str:
    parts = wordninja.split(concat.lower())
    return " ".join(p.upper() for p in parts)

def extract_text_fast(pdf_path: str) -> str:
    """Extrae texto directo si el PDF tiene capa."""
    doc = fitz.open(pdf_path)
    txt = ""
    for p in doc:
        txt += p.get_text()
    return txt

def ocr_text(pdf_path: str, dpi: int = 150) -> str:
    """OCR de respaldo sobre imagen binarizada."""
    img = convert_from_path(pdf_path, dpi=dpi)[0]
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x < 180 else 255, '1')
    return pytesseract.image_to_string(bw, lang='spa', config='--oem 1 --psm 6')

def extract_fields_label(text: str):
    """
    Extrae CC y Nombre si están etiquetados con 'C.C.' o 'NOMBRE:'.
    Devuelve (nombre, cc, nivel, fecha) o (None,None,...).
    """
    # C.C.
    mcc = re.search(r'\bC\.?C\.?[:\s]*([0-9]{6,15})\b', text, re.I) \
       or re.search(r'\bCEDULA[:\s]*([0-9]{6,15})\b', text, re.I)
    cc = mcc.group(1) if mcc else None

    # Nombre etiquetado
    mna = re.search(r'\bNOMBRE[:\s]*([A-Za-zÁÉÍÓÚÑ ]{4,})', text, re.I)
    nombre = None
    if mna:
        raw = mna.group(1).strip().upper().replace(" ", "")
        nombre = split_name(raw)

    # Nivel
    tu = normalize(text)
    if 'ENTRANTE' in tu:
        nivel = 'ENTRANTE'
    elif 'VIGIA' in tu or 'VIGILANTE' in tu:
        nivel = 'VIGIA'
    elif 'SUPERVISOR' in tu:
        nivel = 'SUPERVISOR'
    else:
        nivel = 'DESCONOCIDO'

    # Fecha
    mfe = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', text)
    fecha = mfe.group(1) if mfe else ""

    return nombre, cc, nivel, fecha

def extract_name_cc_via_roi(pdf_path: str, dpi: int = 200):
    """
    Detecta la caja de 'C.C.' con image_to_data y recorta solo esa franja
    (con margen), luego recorta justo encima para extraer el Nombre.
    """
    pil = convert_from_path(pdf_path, dpi=dpi)[0]
    gray = pil.convert("L")
    bw = gray.point(lambda x: 0 if x < 160 else 255, '1')

    data = pytesseract.image_to_data(bw, lang='spa', output_type=Output.DICT)
    w_page, h_page = bw.size

    name = cc = None

    for i, txt in enumerate(data['text']):
        if txt.strip().upper().startswith('C.C'):
            x, y, wi, hi = (
                data['left'][i],
                data['top'][i],
                data['width'][i],
                data['height'][i]
            )
            # Recorte preciso de CC
            margin_x = int(wi * 0.5)
            x0 = max(0, x - margin_x)
            x1 = min(w_page, x + wi + margin_x)
            y0 = max(0, y - int(hi * 0.2))
            y1 = min(h_page, y + hi + int(hi * 0.2))
            cc_roi = bw.crop((x0, y0, x1, y1))
            txt_cc = pytesseract.image_to_string(cc_roi, lang='spa', config='--psm 7')
            mcc = re.search(r'([0-9]{6,15})', txt_cc.replace('.', ''))
            if mcc:
                cc = mcc.group(1)

            # Recorte preciso del Nombre justo encima
            nombre_y0 = max(0, y0 - 3 * hi)
            nombre_y1 = y0
            name_roi = bw.crop((x0, nombre_y0, x1, nombre_y1))
            txt_name = pytesseract.image_to_string(name_roi, lang='spa', config='--psm 6')
            candidates = [
                L.strip().upper()
                for L in txt_name.splitlines()
                if re.fullmatch(r'[A-ZÁÉÍÓÚÑ ]{4,}', L.strip().upper())
            ]
            if candidates:
                best = max(candidates, key=len).replace(" ", "")
                name = split_name(best)
            break

    return name, cc

def process_single_pdf(pdf_path: str, output_dir: str) -> dict:
    # 1) Intento extracción rápida
    text = extract_text_fast(pdf_path)
    nombre, cc, nivel, fecha = extract_fields_label(text)

    # 2) Si falta alguno, fallback a ROI+OCR
    if not nombre or not cc:
        roi_name, roi_cc = extract_name_cc_via_roi(pdf_path)
        if roi_name and roi_cc:
            nombre, cc = roi_name, roi_cc
            # para nivel y fecha seguimos usando `text`
            _, _, nivel, fecha = extract_fields_label(text)

    # 3) Renombrado en MAYÚSCULAS y underscores
    slug = f"{nombre}_{cc}".replace(" ", "_").upper()
    new_name = f"{slug}.PDF"

    # 4) Carpeta por nivel
    folder = nivel if nivel != "DESCONOCIDO" else "SIN_NIVEL"
    dest_dir = os.path.join(output_dir, f"NIVEL_{folder}")
    os.makedirs(dest_dir, exist_ok=True)

    # 5) Copia renombrada
    dst = os.path.join(dest_dir, new_name)
    shutil.copy2(pdf_path, dst)

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

    records = [process_single_pdf(p, output_dir) for p in pdf_paths]

    # ZIP final
    zip_path = os.path.join(output_dir, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _, files in os.walk(output_dir):
            for fn in files:
                if fn.upper().endswith(".PDF"):
                    absf = os.path.join(root, fn)
                    relf = os.path.relpath(absf, output_dir)
                    zf.write(absf, arcname=relf)

    df = pd.DataFrame(records)
    return df, zip_path
