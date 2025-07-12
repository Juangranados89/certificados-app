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


def _name_before_cc(text: str) -> str:
    """
    Retrocede desde la línea con 'C.C.' y devuelve la primera
    línea que parece un nombre (2-4 palabras mayúsculas, ≥3 letras,
    sin números ni palabras del encabezado).
    """
    norm_lines = _norm(text).splitlines()

    try:
        idx_cc = next(i for i, ln in enumerate(norm_lines) if 'C.C.' in ln)
    except StopIteration:
        return ''

    stop = {'CERTIFICACION', 'CAPACITACION', 'ENTRENAMIENTO',
            'TRABAJO', 'SEGURO', 'ESPACIOS', 'CONFINADOS'}

    pat = re.compile(r'(?:[A-ZÑ]{3,}\s+){1,3}[A-ZÑ]{3,}$')

    for j in range(idx_cc - 1, max(-1, idx_cc - 16), -1):
        ln = norm_lines[j].strip()
        if not ln or any(word in ln for word in stop):
            continue
        if pat.fullmatch(ln) and len(ln.split()) in (3, 4):
            return ln
    return ''


# ─────────────────────── Extractor PDF STC ───────────────────────
def _extract_pdf(text: str) -> dict[str, str]:
    t = _norm(text)

    # CC
    cc_m = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)
    cc = cc_m.group(1).replace('.', '').replace(' ', '') if cc_m else ''

    # ---------- NOMBRE ----------
    nom_m = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    if nom_m:
        nombre = nom_m.group(1).strip()
    else:
        nombre = ''
        if cc_m:
            # línea justo antes de la cédula
            nombre = _prev_line(t, cc_m.span())

            # hasta 3 líneas previas
            if not nombre:
                prev = t[:cc_m.span()[0]].splitlines()[-4:-1]
                for ln in reversed(prev):
                    ln = ln.strip()
                    if re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and len(ln.split()) >= 2:
                        nombre = ln
                        break

        # Retroceso desde 'C.C.' (plan definitivo)
        if not nombre:
            nombre = _name_before_cc(text)

        # Último recurso
        if not nombre:
            nombre = _between_blocks(t)

    # Nivel
    niv_m = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    nivel = niv_m.group(1).replace('Í', 'I') if niv_m else ''

    # Fecha expedición (primera fecha como reserva)
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

    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ''

    cc_m = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)
    cc = cc_m.group(1).replace('.', '') if cc_m else ''

    cert_m = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    cert = cert_m.group(1).strip() if cert_m else ''

    fexp_m = re.search(r'EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fven_m = re.search(r'VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fexp = fexp_m.group(1).replace('-', '/') if fexp_m else ''
    fven = fven_m.group(1).replace('-', '/') if fven_m else ''

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


# ───────────────── OCR wrappers (PDF híbrido) ────────────────────
def _page_image(pdf: str, dpi: int):
    doc = fitz.open(pdf)
    pix = doc.load_page(0).get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    doc.close()
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _pdf_to_text_hybrid(path: str) -> str:
    doc = fitz.open(path)
    page = doc.load_page(0)
    txt = page.get_text("text")
    doc.close()
    if txt.strip():      # texto embebido
        return txt
    # fallback OCR
    pix = page.get_pixmap(dpi=300, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img = ImageOps.autocontrast(ImageOps.grayscale(img).filter(ImageFilter.SHARPEN))
    return _ocr(img)


def parse_pdf(path: str):
    txt = _pdf_to_text_hybrid(path)
    campos = _extract_pdf(txt)
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
