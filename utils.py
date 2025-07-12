"""
utils.py – OCR, renombrado y conversión imagen→PDF
Compatible con:
  • Certificados PDF (ENTRANTE / VIGÍA / SUPERVISOR…)
  • Certificados JPEG/PNG C&C  (Aparejador / Supervisor / Operador)
"""

from __future__ import annotations
import os, shutil, re, unicodedata, fitz, pytesseract, zipfile
from pathlib import Path
import pandas as pd
from PIL import Image, ImageOps, ImageFilter

# ──────────── texto helpers ────────────
def _norm(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', t)
                   if not unicodedata.combining(c)).upper()

# ──────────── cargo helper ────────────
def cargo_from_campos(c: dict[str, str]) -> str:
    cert  = c.get("CERTIFICADO", "").upper()
    nivel = c.get("NIVEL", "").upper()
    if "APAREJADOR" in cert:     return "APAREJADOR"
    if "OPERADOR"   in cert:     return "OPERADOR"
    if "SUPERVISOR" in cert or "SUPERVISOR" in nivel: return "SUPERVISOR"
    return nivel or "OTROS"

# ──────────── extracción PDF STC ────────────
def _guess_prev_line(t: str, span):
    start = t.rfind('\n', 0, span[0])+1
    cand  = t[start:span[0]].strip()
    return cand if re.fullmatch(r'[A-ZÑ ]{5,60}', cand) else ''

def _guess_between(t: str):
    m = re.search(r'CONFINADOS:\s*([\s\S]{0,120}?)C[.]?C', t)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if re.fullmatch(r'[A-ZÑ ]{5,60}', ln):
                return ln
    return ''

def _extract_pdf(text: str):
    t = _norm(text)
    nom = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    cc  = re.search(r'C[.]?C[.]?|CEDULA.+?([\d \.]{7,15})', t)
    nombre = nom.group(1).strip() if nom else ( _guess_prev_line(t, cc.span()) if cc else _guess_between(t) )
    nivel  = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    fecha  = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)
    return {
        "NOMBRE": nombre,
        "CC": cc.group(1).replace('.', '').replace(' ', '') if cc else '',
        "NIVEL": nivel.group(1).replace('Í','I') if nivel else '',
        "FECHA_EXP": fecha.group(1).replace('-', '/') if fecha else '',
        "FECHA_VEN": '',
        "CERTIFICADO": '',
    }

# ──────────── extracción JPEG C&C ────────────
def _extract_cc_img(text: str) -> dict[str, str]:
    t = _norm(text)

    # Nombre y apellidos
    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ''

    # Cédula
    cc = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)

    # Texto del encabezado amarillo
    cert = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    cert_val = cert.group(1).strip() if cert else ''

    # Fechas
    fexp = re.search(r'EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fven = re.search(r'VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)

    # ------- NUEVO: detectar cargo en todo el OCR -------
    nivel = ''
    for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
        if key in t:
            nivel = key
            break
    # si no lo encontró en el texto, usa lo del encabezado (por compatibilidad)
    if not nivel and cert_val:
        for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
            if key in cert_val:
                nivel = key
                break

    return {
        "NOMBRE": nombre,
        "CC": cc.group(1).replace('.', '') if cc else '',
        "CERTIFICADO": cert_val,
        "FECHA_EXP": fexp.group(1).replace('-', '/') if fexp else '',
        "FECHA_VEN": fven.group(1).replace('-', '/') if fven else '',
        "NIVEL": nivel or cert_val  # para que cargo_from_campos lo lea
    }

# ──────────── OCR engines ────────────
def _page_img(pdf, dpi):
    pg = fitz.open(pdf)[0]
    pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
def _ocr(img): return pytesseract.image_to_string(img, lang='spa', config='--oem 3 --psm 6')

def parse_pdf(path):
    for dpi,pre in [(200,False),(300,True),(400,True)]:
        im=_page_img(path,dpi)
        if pre: im=ImageOps.autocontrast(ImageOps.grayscale(im).filter(ImageFilter.SHARPEN))
        txt=_ocr(im); c=_extract_pdf(txt)
        if c["NOMBRE"] and c["CC"]: return c, txt
    return c, txt

def parse_image(path):
    txt=_ocr(Image.open(path).convert("RGB")); c=_extract_cc_img(txt)
    return c, txt, path

def parse_file(path):
    ext=Path(path).suffix.lower()
    if ext=='.pdf':
        c,raw=parse_pdf(path); return c, raw, path
    if ext in('.jpg','.jpeg','.png'):
        return parse_image(path)
    raise ValueError("tipo no soportado")

# ──────────── renombrado ────────────
def _copiar_renombrar(pdf, out_root, campos):
    cargo = cargo_from_campos(campos)
    slug  = f"{campos['NOMBRE'].replace(' ','_')}_{campos['CC']}_{cargo}_".upper()
    dest  = os.path.join(out_root, cargo); os.makedirs(dest, exist_ok=True)
    dst   = os.path.join(dest, f"{slug}.pdf"); shutil.copy2(pdf, dst)
    return os.path.relpath(dst, out_root)

def save_image_as_pdf_renamed(img, out_root, campos):
    cargo = cargo_from_campos(campos)
    slug  = f"{campos['NOMBRE'].replace(' ','_')}_{campos['CC']}_{cargo}_".upper()
    dest  = os.path.join(out_root, cargo); os.makedirs(dest, exist_ok=True)
    pdf   = os.path.join(dest, f"{slug}.pdf")
    Image.open(img).convert("RGB").save(pdf, "PDF", resolution=150.0)
    return os.path.relpath(pdf, out_root)
