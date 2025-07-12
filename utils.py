"""
utils.py
---------

• OCR para certificados PDF de espacios confinados.
• OCR para certificados JPEG/PNG de C&C (Supervisor, Aparejador, Operador).
• Conversión de imágenes a PDF con nombre final.
• Estructura de carpetas final basada en cargo/nivel.
"""

# ============================================================================
# 1. IMPORTACIONES
# ============================================================================

from __future__ import annotations

# Estándar / terceros
import os
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path

import fitz                      # PyMuPDF
import pytesseract
from PIL import Image, ImageOps, ImageFilter

# ============================================================================
# 2. FUNCIONES UTILITARIAS BÁSICAS
# ============================================================================

def _norm(text: str) -> str:
    """
    Convierte un texto a MAYÚSCULAS sin tildes para búsquedas insensibles
    a acentos y case.
    """
    return ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    ).upper()


def _ocr(img: Image.Image) -> str:
    """Ejecuta Tesseract (español) sobre una imagen PIL."""
    return pytesseract.image_to_string(
        img,
        lang="spa",
        config="--oem 3 --psm 6"
    )

# ============================================================================
# 3. EXTRACCIÓN DE CAMPOS PARA PDF STC (Espacios confinados)
# ============================================================================

# --- heurísticas auxiliares ---
def _prev_line(full: str, span: tuple[int, int]) -> str:
    start = full.rfind('\n', 0, span[0]) + 1
    candidate = full[start:span[0]].strip()
    if re.fullmatch(r'[A-ZÑ ]{5,60}', candidate):
        return candidate
    return ''


def _between_blocks(full: str) -> str:
    """
    Busca un nombre en el bloque que suele estar entre
    'CONFINADOS:' y 'C.C.'.
    """
    m = re.search(r'CONFINADOS:\s*([\s\S]{0,160}?)C[.]?C', full)
    if not m:
        return ''
    for line in m.group(1).splitlines():
        line = line.strip()
        if re.fullmatch(r'[A-ZÑ ]{5,60}', line):
            return line
    return ''


def _extract_pdf(text: str) -> dict[str, str]:
    """
    Extrae campos de los PDFs (espacios confinados).
    Claves devueltas:
        NOMBRE, CC, NIVEL, FECHA_EXP, FECHA_VEN (vacío), CERTIFICADO (vacío)
    """
    t = _norm(text)

    # --- CC ---
    cc_match = re.search(
        r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t
    )
    cc_val = (
        cc_match.group(1).replace('.', '').replace(' ', '')
        if cc_match else ''
    )

    # --- NOMBRE (planes A, B, C) ---
    nombre = ''
    nom_match = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)

    if nom_match:
        nombre = nom_match.group(1).strip()
    elif cc_match:
        # Plan B: línea justo antes de la cédula
        nombre = _prev_line(t, cc_match.span())

        # Plan C: hasta 3 líneas antes, con ≥ 2 palabras
        if not nombre:
            prev_lines = t[:cc_match.span()[0]].splitlines()[-4:-1]
            for ln in reversed(prev_lines):
                ln = ln.strip()
                if (
                    re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and
                    len(ln.split()) >= 2
                ):
                    nombre = ln
                    break
    if not nombre:
        nombre = _between_blocks(t)

    # --- NIVEL ---
    nivel_match = re.search(
        r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t
    )
    nivel_val = (
        nivel_match.group(1).replace('Í', 'I')
        if nivel_match else ''
    )

    # --- Fecha expedición (primera fecha encontrada como reserva) ---
    fexp_match = re.search(
        r'FECHA DE EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t
    )
    fany_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)

    fexp_val = (
        (fexp_match or fany_match).group(1).replace('-', '/')
        if (fexp_match or fany_match) else ''
    )

    return {
        "NOMBRE": nombre,
        "CC": cc_val,
        "NIVEL": nivel_val,
        "CERTIFICADO": '',
        "FECHA_EXP": fexp_val,
        "FECHA_VEN": '',
    }

# ============================================================================
# 4. EXTRACCIÓN DE CAMPOS PARA JPEG/PNG C&C
# ============================================================================

def _extract_cc_img(text: str) -> dict[str, str]:
    t = _norm(text)

    # Nombre completo
    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = (
        f"{n.group(1).strip()} {a.group(1).strip()}"
        if n and a else ''
    )

    # CC
    cc_match = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)
    cc_val = cc_match.group(1).replace('.', '') if cc_match else ''

    # Encabezado amarillo
    cert_match = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    cert_val = cert_match.group(1).strip() if cert_match else ''

    # Fechas
    fexp_match = re.search(
        r'EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t
    )
    fven_match = re.search(
        r'VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t
    )

    fexp_val = (
        fexp_match.group(1).replace('-', '/') if fexp_match else ''
    )
    fven_val = (
        fven_match.group(1).replace('-', '/') if fven_match else ''
    )

    # Cargo/nivel explícito
    nivel_val = ''
    for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
        if key in t:
            nivel_val = key
            break
    if not nivel_val and cert_val:
        for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
            if key in cert_val:
                nivel_val = key
                break

    return {
        "NOMBRE": nombre,
        "CC": cc_val,
        "CERTIFICADO": cert_val,
        "FECHA_EXP": fexp_val,
        "FECHA_VEN": fven_val,
        "NIVEL": nivel_val or cert_val,
    }

# ============================================================================
# 5. OCR wrappers
# ============================================================================

def _page_image(pdf_path: str, dpi: int) -> Image.Image:
    page = fitz.open(pdf_path)[0]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def parse_pdf(path: str):
    """
    Devuelve (campos, txt)   –   campos siempre contiene FECHA_EXP.
    """
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        img = _page_image(path, dpi)
        if prep:
            img = ImageOps.autocontrast(
                ImageOps.grayscale(img).filter(ImageFilter.SHARPEN)
            )
        txt = _ocr(img)
        campos = _extract_pdf(txt)
        if campos["NOMBRE"] and campos["CC"]:
            return campos, txt
    return campos, txt


def parse_image(path: str):
    txt = _ocr(Image.open(path).convert("RGB"))
    campos = _extract_cc_img(txt)
    return campos, txt, path


def parse_file(path: str):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        campos, raw = parse_pdf(path)
        return campos, raw, path
    if ext in (".jpg", ".jpeg", ".png"):
        return parse_image(path)
    raise ValueError("Tipo de archivo no soportado")

# ============================================================================
#
