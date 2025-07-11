"""
utils.py – OCR robusto, extracción de campos, renombrado y empaquetado
"""
from __future__ import annotations
import fitz, pytesseract, re, unicodedata, os, shutil, zipfile, pandas as pd
from PIL import Image, ImageOps, ImageFilter


# ───────────────────────── Utilidades de texto ───────────────────────── #
def _norm(txt: str) -> str:
    """Mayúsculas y sin tildes (NFKD)."""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', txt)
        if not unicodedata.combining(c)
    ).upper()


def _guess_name_prev_line(text_norm: str, cc_span: tuple[int, int]) -> str:
    """Línea inmediatamente anterior al patrón de CC."""
    ln_start = text_norm.rfind('\n', 0, cc_span[0]) + 1
    candidate = text_norm[ln_start:cc_span[0]].strip()
    if 5 <= len(candidate) <= 60 and re.fullmatch(r'[A-ZÑ ]+', candidate):
        return candidate
    return ''


def _guess_name_confinados(text_norm: str) -> str:
    """Primera línea mayúscula entre 'CONFINADOS:' y 'C.C.'."""
    m_block = re.search(r'CONFINADOS:\s*([\s\S]{0,120}?)C[.]?C', text_norm)
    if not m_block:
        return ''
    for line in m_block.group(1).splitlines():
        line = line.strip()
        if 5 <= len(line) <= 60 and re.fullmatch(r'[A-ZÑ ]+', line):
            return line
    return ''


# ───────────────────────── Extracción principal ───────────────────────── #
def _extract(text: str) -> dict[str, str]:
    t = _norm(text)

    # --- patrones directos ---
    nombre_re = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    cc_re = re.search(r'(?:C[.]?C[.]?|CEDULA(?: DE CIUDADANIA)?|N[.ºO])'
                      r'\s*[:\-]?\s*([\d\.\s]{7,15})', t)
    nivel_re = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    fecha_re = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)

    # --- resolver nombre con cascada de métodos ---
    nombre_val = nombre_re.group(1).strip() if nombre_re else ''
    if not nombre_val and cc_re:
        nombre_val = _guess_name_prev_line(t, cc_re.span())
    if not nombre_val:
        nombre_val = _guess_name_confinados(t)

    return {
        "NOMBRE": nombre_val,
        "CC": cc_re.group(1).replace('.', '').replace(' ', '') if cc_re else '',
        "NIVEL": nivel_re.group(1).replace('Í', 'I') if nivel_re else '',
        "FECHA": fecha_re.group(1).replace('-', '/') if fecha_re else '',
    }


# ───────────────────────── OCR ───────────────────────── #
def _page_image(pdf_path: str, dpi: int) -> Image.Image:
    page = fitz.open(pdf_path)[0]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang='spa', config='--oem 3 --psm 6')


def parse_pdf(pdf_path: str) -> tuple[dict[str, str], str]:
    """Devuelve (campos extraídos, texto OCR bruto)."""
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        img = _page_image(pdf_path, dpi)
        if prep:
            img = ImageOps.grayscale(img).filter(ImageFilter.SHARPEN)
            img = ImageOps.autocontrast(img)
        text = _ocr(img)
        campos = _extract(text)
        if all(campos.values()):
            return campos, text
    return campos, text


# ─────────────────── Renombrado, clasificación y ZIP ─────────────────── #
def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    nombre_slug = campos['NOMBRE'].replace(' ', '_')
    cc = campos['CC']
    nivel = campos['NIVEL'] or 'DESCONOCIDO'
    filename = f"{nombre_slug}_{cc}_{nivel}_".upper() + ".pdf"

    dest_dir = os.path.join(out_root, nivel)
    os.makedirs(dest_dir, exist_ok=True)

    dst = os.path.join(dest_dir, filename)
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)


def process_pdfs(pdf_paths: list[str], out_dir: str):
    """Procesa varios PDFs; devuelve DataFrame y ruta del ZIP."""
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


__all__ = ['parse_pdf', 'process_pdfs', '_copiar_renombrar']
