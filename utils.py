"""
utils.py – OCR robusto y renombrado/clasificación de certificados
"""
from __future__ import annotations
import fitz, pytesseract, re, unicodedata, os, shutil, zipfile, pandas as pd
from PIL import Image, ImageOps, ImageFilter


# ───────────────────────── helpers ───────────────────────── #
def _norm(txt: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', txt)
                   if not unicodedata.combining(c)).upper()


def _extract(text: str) -> dict[str, str]:
    t = _norm(text)
    nombre = (re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
              or re.search(r'DE\s*:\s*([A-ZÑ ]{5,})', t)
              or re.search(r'FUNCIONARIO\s*[:\-]?\s*([A-ZÑ ]{5,})', t))
    cc     = re.search(r'(?:C[.]?C[.]?|CEDULA(?: DE CIUDADANIA)?|N[.ºO])\s*[:\-]?\s*([\d\.\s]{7,15})', t)
    nivel  = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    fecha  = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)

    return {
        "NOMBRE": nombre.group(1).strip() if nombre else '',
        "CC"    : cc.group(1).replace('.', '').replace(' ', '') if cc else '',
        "NIVEL" : nivel.group(1).replace('Í', 'I') if nivel else '',
        "FECHA" : fecha.group(1).replace('-', '/') if fecha else '',
    }


# ───────────────────────── OCR ───────────────────────── #
def _page_image(pdf_path: str, dpi: int) -> Image.Image:
    pg = fitz.open(pdf_path)[0]
    pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang='spa', config='--oem 3 --psm 6')


def parse_pdf(pdf_path: str) -> tuple[dict[str, str], str]:
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        im = _page_image(pdf_path, dpi)
        if prep:
            im = ImageOps.grayscale(im).filter(ImageFilter.SHARPEN)
            im = ImageOps.autocontrast(im)
        txt = _ocr(im)
        campos = _extract(txt)
        if all(campos.values()):
            return campos, txt
    return campos, txt


# ──────────────────── renombrado & ZIP ──────────────────── #
def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    nombre = campos['NOMBRE'].strip().replace(' ', '_')
    cc     = campos['CC']
    nivel  = campos['NIVEL']
    filename = f"{nombre}_{cc}_{nivel}_".upper() + ".pdf"

    dest_dir = os.path.join(out_root, nivel or 'DESCONOCIDO')
    os.makedirs(dest_dir, exist_ok=True)

    dst = os.path.join(dest_dir, filename)
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)


def process_pdfs(pdf_paths: list[str], out_dir: str):
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    registros = []
    for p in pdf_paths:
        campos, _ = parse_pdf(p)
        rel = _copiar_renombrar(p, out_dir, campos)
        campos['ARCHIVO'] = rel
        registros.append(campos)

    zip_path = os.path.join(out_dir, 'certificados_organizados.zip')
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for root, _, files in os.walk(out_dir):
            for fn in files:
                if fn.lower().endswith('.pdf'):
                    abs_f = os.path.join(root, fn)
                    zf.write(abs_f, arcname=os.path.relpath(abs_f, out_dir))

    df = pd.DataFrame(registros)
    return df, zip_path

#  Exportamos la helper para uso en app.py
__all__ = ['parse_pdf', 'process_pdfs', '_copiar_renombrar']
