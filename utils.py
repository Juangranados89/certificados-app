"""
utils.py
---------

OCR y renombrado de certificados:

• PDF de espacios confinados  (ENTRANTE / VIGÍA / SUPERVISOR …)
• JPEG/PNG de C&C            (SUPERVISOR / APAREJADOR / OPERADOR)
• Convierte imágenes a PDF con el nombre final.
• Clasifica carpetas por cargo/nivel.
"""

from __future__ import annotations

import os, re, shutil, unicodedata
from pathlib import Path

import fitz            # PyMuPDF
import pytesseract
from PIL import Image, ImageOps, ImageFilter


# ─────────────────────── Helpers básicos ────────────────────────
def _norm(t: str) -> str:
    """Mayúsculas sin tildes para búsquedas insensibles."""
    return ''.join(c for c in unicodedata.normalize('NFKD', t)
                   if not unicodedata.combining(c)).upper()


def _ocr(img: Image.Image) -> str:
    """OCR español con Tesseract."""
    return pytesseract.image_to_string(
        img,
        lang="spa",
        config="--oem 3 --psm 6"
    )


# ─────────────────────── Heurísticas PDF STC ─────────────────────
def _prev_line(t: str, span):
    start = t.rfind('\n', 0, span[0]) + 1
    cand = t[start:span[0]].strip()
    return cand if re.fullmatch(r'[A-ZÑ ]{5,60}', cand) else ''


def _between_blocks(t: str):
    m = re.search(r'CONFINADOS:\s*([\s\S]{0,160}?)C[.]?C', t)
    if not m:
        return ''
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if re.fullmatch(r'[A-ZÑ ]{5,60}', ln):
            return ln
    return ''


def _name_between_markers(text: str) -> str:
    """
    Devuelve la PRIMERA línea no vacía que aparece DESPUÉS del encabezado
    'ESPACIOS CONFINADOS:' y ANTES de la primera 'C.C.'.
    La línea debe tener al menos dos palabras y solo letras / espacios.
    """
    norm = _norm(text)

    # 1) Localiza encabezado y 'C.C.'
    ini = norm.find('ESPACIOS CONFINADOS:')
    if ini == -1:
        return ''
    end = norm.find('C.C.', ini)
    if end == -1:
        return ''

    # 2) Recorre las líneas que hay entre ambos límites
    lines = norm[ini:end].splitlines()
    passed_header = False
    for ln in lines:
        ln = ln.strip()
        if not passed_header:
            # saltamos las líneas hasta la PRIMERA vacía tras el encabezado
            if not ln:            # línea en blanco → hemos superado header
                passed_header = True
            continue

        if not ln:                # líneas vacías extra → sigue buscando
            continue

        # 3) Patrón de nombre: 2-4 palabras mayúsculas, ≥3 caracteres c/u
        if re.fullmatch(r'(?:[A-ZÑ ]{3,}\s+){1,3}[A-ZÑ ]{3,}', ln) and len(ln.split()) >= 2:
            return ln

        # Si aparece algo con 'CERTIFICACION' o 'ENTRENAMIENTO', aborta
        if 'CERTIFICACION' in ln or 'ENTRENAMIENTO' in ln:
            break

    return ''



    # empezamos en la línea siguiente
    rest = norm[pos:].splitlines()[1:]   # todo lo que sigue
    for ln in rest:
        ln = ln.strip()
        if not ln:                   # línea vacía → continúa
            continue
        # patrón: mayúsculas + al menos 2 palabras
        if re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and len(ln.split()) >= 2:
            return ln
        # si llega a 'C.C.' sin encontrar nombre, aborta
        if 'C.C.' in ln:
            break
    return ''

    # palabras que invalidan (propias del encabezado)
    bad = re.compile(r'\b(CERTIFICACION|CAPACITACION|ENTRENAMIENTO|'
                     r'TRABAJO|SEGURO|ESPACIOS|CONFINADOS)\b')

    for ln in norm[start:end].splitlines():
        ln = ln.strip()
        if (
            re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and
            len(ln.split()) >= 2 and
            not bad.search(ln)
        ):
            return ln
    return ''


# ─────────────────────── Extractor PDF STC ───────────────────────
def _extract_pdf(text: str) -> dict[str, str]:
    t = _norm(text)

    # CC
    cc_m = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)
    cc = cc_m.group(1).replace('.', '').replace(' ', '') if cc_m else ''

    # ---------- NOMBRE (planes A–E) ----------
    nom_m = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    if nom_m:
        nombre = nom_m.group(1).strip()
    else:
        nombre = ''
        if cc_m:
            # Plan B: línea justo antes de la cédula
            nombre = _prev_line(t, cc_m.span())

            # Plan C: hasta 3 líneas previas
            if not nombre:
                prev = t[:cc_m.span()[0]].splitlines()[-4:-1]
                for ln in reversed(prev):
                    ln = ln.strip()
                    if re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and len(ln.split()) >= 2:
                        nombre = ln
                        break

        # Plan E: bloque entre encabezado y 'C.C.'
        if not nombre:
            nombre = _name_between_markers(text)

        # Plan F: bloque genérico entre 'CONFINADOS:' y 'C.C.'
        if not nombre:
            nombre = _between_blocks(t)

    # Nivel
    niv_m = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    nivel = niv_m.group(1).replace('Í', 'I') if niv_m else ''

    # Fecha de expedición (primera fecha como reserva)
    fexp_m = re.search(r'FECHA DE EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fany_m = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fexp = (fexp_m or fany_m).group(1).replace('-', '/') if (fexp_m or fany_m) else ''

    return {
        "NOMBRE": nombre,
        "CC": cc,
        "NIVEL": nivel,
        "CERTIFICADO": '',
        "FECHA_EXP": fexp,
        "FECHA_VEN": ''
    }


# ─────────────────────── Extractor JPEG/PNG C&C ───────────────────
def _extract_cc_img(text: str) -> dict[str, str]:
    t = _norm(text)

    # Nombre completo
    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ''

    # CC
    cc_m = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)
    cc = cc_m.group(1).replace('.', '') if cc_m else ''

    # Encabezado amarillo
    cert_m = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    cert = cert_m.group(1).strip() if cert_m else ''

    # Fechas
    fexp_m = re.search(r'EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fven_m = re.search(r'VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fexp = fexp_m.group(1).replace('-', '/') if fexp_m else ''
    fven = fven_m.group(1).replace('-', '/') if fven_m else ''

    # Nivel
    nivel = ''
    for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
        if key in t:
            nivel = key
            break
    if not nivel and cert:
        for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
            if key in cert:
                nivel = key
                break

    return {
        "NOMBRE": nombre,
        "CC": cc,
        "CERTIFICADO": cert,
        "FECHA_EXP": fexp,
        "FECHA_VEN": fven,
        "NIVEL": nivel or cert
    }


# ─────────────────────── OCR wrappers ─────────────────────────────
def _page_image(pdf: str, dpi: int):
    doc = fitz.open(pdf)
    pix = doc.load_page(0).get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    doc.close()
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def parse_pdf(path: str):
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        img = _page_image(path, dpi)
        if prep:
            img = ImageOps.autocontrast(ImageOps.grayscale(img).filter(ImageFilter.SHARPEN))
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


# ─────────────────────── Renombrado / guardado ────────────────────
def _cargo(campos):
    c = (campos.get("NIVEL") or campos.get("CERTIFICADO") or '').upper()
    if "APAREJADOR" in c:
        return "APAREJADOR"
    if "OPERADOR" in c:
        return "OPERADOR"
    if "SUPERVISOR" in c:
        return "SUPERVISOR"
    return c or "OTROS"


def _slug(campos):
    return f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}_{_cargo(campos)}_".upper()


def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    dest_dir = os.path.join(out_root, _cargo(campos))
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, f"{_slug(campos)}.pdf")
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)


def save_image_as_pdf_renamed(img_path: str, out_root: str, campos: dict[str, str]) -> str:
    dest_dir = os.path.join(out_root, _cargo(campos))
    os.makedirs(dest_dir, exist_ok=True)
    pdf_out = os.path.join(dest_dir, f"{_slug(campos)}.pdf")
    Image.open(img_path).convert("RGB").save(pdf_out, "PDF", resolution=150.0)
    return os.path.relpath(pdf_out, out_root)
