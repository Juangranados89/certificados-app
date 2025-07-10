# utils.py
import os, re, zipfile, shutil, unicodedata
import pandas as pd
import pytesseract
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image, ImageOps, ImageFilter
import wordninja

def normalize(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()

def split_name(concat: str) -> str:
    parts = wordninja.split(concat.lower())
    return " ".join(p.upper() for p in parts)

def extract_text_fast(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    txt = ""
    for p in doc:
        txt += p.get_text()
    return txt

def ocr_text(pdf_path: str, dpi: int = 150) -> str:
    img = convert_from_path(pdf_path, dpi=dpi)[0]
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x < 180 else 255, "1")
    return pytesseract.image_to_string(bw, lang="spa", config="--oem 1 --psm 6")

def extract_fields(text: str):
    tu = normalize(text)
    # Cédula
    m = (re.search(r'\bC\.?C\.?[:\s]*([0-9]{6,15})\b', text, re.I)
         or re.search(r'\bCEDULA[:\s]*([0-9]{6,15})\b', text, re.I)
         or re.search(r'\b([0-9]{7,15})\b', text))
    cc = m.group(1) if m else "NODETECT"
    # Nombre
    m2 = re.search(r'\bNOMBRE[:\s]*([A-Za-zÁÉÍÓÚÑ ]{4,})', text, re.I)
    if m2:
        raw = m2.group(1).strip().upper().replace(" ", "")
        nombre = split_name(raw)
    else:
        # fallback: línea más larga de solo mayúsculas
        lines = [l for l in tu.splitlines() if re.fullmatch(r'[A-ZÁÉÍÓÚÑ ]{8,}', l)]
        nombre = split_name(max(lines, key=len)) if lines else "NODETECT"
    # Nivel
    nivel = ("ENTRANTE" if "ENTRANTE" in tu else
             "VIGIA" if "VIGIA" in tu or "VIGILANTE" in tu else
             "SUPERVISOR" if "SUPERVISOR" in tu else
             "DESCONOCIDO")
    # Fecha
    mf = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b', text)
    fecha = mf.group(1) if mf else ""
    return nombre, cc, nivel, fecha

def process_single_pdf(pdf_path: str, output_dir: str) -> dict:
    txt = extract_text_fast(pdf_path)
    if "NODETECT" in normalize(txt) or len(txt) < 30:
        txt = ocr_text(pdf_path)
    nombre, cc, nivel, fecha = extract_fields(txt)

    slug = f"{nombre}_{cc}".replace(" ", "_").upper()
    new_name = f"{slug}.PDF"

    folder = nivel if nivel!="DESCONOCIDO" else "SIN_NIVEL"
    dest = os.path.join(output_dir, f"NIVEL_{folder}")
    os.makedirs(dest, exist_ok=True)

    dst = os.path.join(dest, new_name)
    shutil.copy2(pdf_path, dst)
    return {"CC": cc, "NOMBRE": nombre, "NIVEL": nivel, "FECHA": fecha,
            "ARCHIVO": f"NIVEL_{folder}/{new_name}"}

def process_pdfs(paths: list[str], output_dir: str):
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)
    records = [process_single_pdf(p, output_dir) for p in paths]

    zip_path = os.path.join(output_dir, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for r,d,f in os.walk(output_dir):
            for fn in f:
                if fn.upper().endswith(".PDF"):
                    full = os.path.join(r, fn)
                    rel  = os.path.relpath(full, output_dir)
                    zf.write(full, arcname=rel)
    df = pd.DataFrame(records)
    return df, zip_path
