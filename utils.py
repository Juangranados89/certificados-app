"""
utils.py – OCR y renombrado de certificados (PDF y JPEG/PNG)

* PDF ➜ extrae campos, copia/renombra PDF.
* JPEG/PNG ➜ extrae campos, genera PDF con nombre final, devuelve ruta.
"""

from __future__ import annotations
import os, shutil, zipfile, re, unicodedata
from pathlib import Path
import fitz, pytesseract, pandas as pd
from PIL import Image, ImageOps, ImageFilter


# ───────────────────────────── helpers de texto ───────────────────────────── #
def _norm(txt: str) -> str:
    """Mayúsculas y sin tildes."""
    return ''.join(c for c in unicodedata.normalize('NFKD', txt)
                   if not unicodedata.combining(c)).upper()


# ───────────────────────────── OCR para PDFs STC ───────────────────────────── #
def _guess_prev_line(t: str, span: tuple[int, int]) -> str:
    start = t.rfind('\n', 0, span[0]) + 1
    cand  = t[start:span[0]].strip()
    return cand if re.fullmatch(r'[A-ZÑ ]{5,60}', cand) else ''

def _guess_between(t: str) -> str:
    m = re.search(r'CONFINADOS:\s*([\s\S]{0,120}?)C[.]?C', t)
    if not m: return ''
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if re.fullmatch(r'[A-ZÑ ]{5,60}', ln):
            return ln
    return ''

def _extract_pdf(txt: str) -> dict[str, str]:
    t = _norm(txt)
    nom = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    cc  = re.search(r'(?:C[.]?C[.]?|CEDULA(?: DE CIUDADANIA)?|N[.ºO])\s*[:\-]?\s*([\d \.]{7,15})', t)

    nombre = nom.group(1).strip() if nom else (_guess_prev_line(t, cc.span()) if cc else '') or _guess_between(t)

    nivel = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)

    return {
        "NOMBRE": nombre,
        "CC": cc.group(1).replace('.', '').replace(' ', '') if cc else '',
        "NIVEL": nivel.group(1).replace('Í', 'I') if nivel else '',
        "FECHA": fecha.group(1).replace('-', '/') if fecha else '',
    }


# ───────────────────────────── OCR para JPEG C&C ───────────────────────────── #
def _extract_cc_img(txt: str) -> dict[str, str]:
    t = _norm(txt)
    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ''

    cc = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)
    cert = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    fexp = re.search(r'FECHA DE EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fven = re.search(r'FECHA DE VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)

    return {
        "NOMBRE": nombre,
        "CC": cc.group(1).replace('.', '') if cc else '',
        "CERTIFICADO": cert.group(1).strip() if cert else '',
        "FECHA_EXP": fexp.group(1).replace('-', '/') if fexp else '',
        "FECHA_VEN": fven.group(1).replace('-', '/') if fven else '',
        "NIVEL": cert.group(1).strip() if cert else ''  # usamos el título como nivel/carpeta
    }


# ───────────────────────────── OCR engines ───────────────────────────── #
def _page_image(pdf: str, dpi: int) -> Image.Image:
    page = fitz.open(pdf)[0]
    pix  = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def _ocr_pil(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang="spa", config="--oem 3 --psm 6")


# ───────────────────────────── PDF path parsers ───────────────────────────── #
def parse_pdf(pdf_path: str):
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        im = _page_image(pdf_path, dpi)
        if prep:
            im = ImageOps.autocontrast(ImageOps.grayscale(im).filter(ImageFilter.SHARPEN))
        txt = _ocr_pil(im)
        campos = _extract_pdf(txt)
        if all(campos.values()):
            return campos, txt
    return campos, txt


def parse_image(img_path: str):
    im = Image.open(img_path).convert("RGB")
    txt = _ocr_pil(im)
    campos = _extract_cc_img(txt)
    return campos, txt, img_path  # devuelve ruta original de la imagen


# selector
def parse_file(path: str):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        campos, raw = parse_pdf(path)
        return campos, raw, path
    elif ext in (".jpg", ".jpeg", ".png"):
        return parse_image(path)
    else:
        raise ValueError("Tipo de archivo no soportado")


# ───────────────────────────── renombrado / almacenamiento ───────────────────────────── #
def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    nivel = campos.get("NIVEL") or "DESCONOCIDO"
    slug  = f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}_{nivel}_".upper()
    fn    = f"{slug}.pdf"

    dest_dir = os.path.join(out_root, nivel)
    os.makedirs(dest_dir, exist_ok=True)

    dst = os.path.join(dest_dir, fn)
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)


def save_image_as_pdf_renamed(img_path: str, out_root: str, campos: dict[str, str]) -> str:
    """
    Convierte la imagen a PDF usando el nombre final correcto y devuelve
    la ruta relativa del PDF dentro de out_root.
    """
    nivel = campos.get("NIVEL") or "DESCONOCIDO"
    slug  = f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}_{campos.get('CERTIFICADO','')}_".upper()
    filename = f"{slug}.pdf"

    dest_dir = os.path.join(out_root, nivel)
    os.makedirs(dest_dir, exist_ok=True)

    dest_pdf = os.path.join(dest_dir, filename)
    Image.open(img_path).convert("RGB").save(dest_pdf, "PDF", resolution=150.0)
    return os.path.relpath(dest_pdf, out_root)
