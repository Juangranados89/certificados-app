"""
utils.py
---------

— OCR robusto para certificados PDF de espacios confinados.
— OCR para certificados JPEG/PNG de C&C (Supervisor | Aparejador | Operador).
— Convierte las imágenes a PDF con el nombre final.
— Organiza la salida por carpeta de cargo/nivel.

Funciones exportadas y usadas en app.py
---------------------------------------
parse_file(path)                       → (campos, txt, src_path)
_copiar_renombrar(pdf_path, out_root, campos) -> rel_path
save_image_as_pdf_renamed(img_path, out_root, campos) -> rel_path
"""

from __future__ import annotations

import os, re, shutil, unicodedata
from pathlib import Path
import fitz, pytesseract
from PIL import Image, ImageOps, ImageFilter

# ─────────────────────────── utilidades base ────────────────────────────
def _norm(t: str) -> str:
    """Mayúsculas sin tildes."""
    return ''.join(c for c in unicodedata.normalize('NFKD', t)
                   if not unicodedata.combining(c)).upper()

def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang="spa",
                                       config="--oem 3 --psm 6")

# ─────────────────────────── heurísticas de nombre ───────────────────────
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

# ─────────────────────────── extractor PDF STC ───────────────────────────
def _extract_pdf(txt: str):
    t = _norm(txt)

    # CC
    cc_m = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)
    cc = cc_m.group(1).replace('.', '').replace(' ', '') if cc_m else ''

        # ---------- NOMBRE (planes A–D) ----------
    nom_m = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    if nom_m:
        nombre = nom_m.group(1).strip()
    elif cc_m:
        nombre = _prev_line(t, cc_m.span())          # plan B
        if not nombre:
            prev = t[:cc_m.span()[0]].splitlines()[-4:-1]  # plan C
            for ln in reversed(prev):
                ln = ln.strip()
                if re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and len(ln.split()) >= 2:
                    nombre = ln
                    break
    else:
        nombre = ''

    if not nombre and cc_m:                          # ← plan D nuevo
        lines = t.splitlines()
        idx_cc = next((i for i, ln in enumerate(lines)
                       if re.search(r'(?:C[.]?C[.]?|CEDULA)', ln)), None)
        if idx_cc is not None:
            for j in range(idx_cc - 1, max(-1, idx_cc - 9), -1):
                cand = lines[j].strip()
                if re.fullmatch(r'[A-ZÑ ]{5,60}', cand) and len(cand.split()) >= 2:
                    nombre = cand
                    break

    if not nombre:
        nombre = _between_blocks(t)                  # último recurso


    # Nivel
    niv_m = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)
    nivel = niv_m.group(1).replace('Í', 'I') if niv_m else ''

    # Fechas
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

# ─────────────────────────── extractor JPEG/PNG C&C ──────────────────────
def _extract_cc_img(txt: str):
    t = _norm(txt)

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

    # Nivel (palabras clave)
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

# ─────────────────────────── OCR wrappers ────────────────────────────────
def _page_image(pdf: str, dpi: int):
    page = fitz.open(pdf)[0]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
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
    return campos, txt  # devuelve lo mejor que pudo

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

# ─────────────────────────── renombrado / guardado ───────────────────────
def _cargo(campos):  # alias corto
    c = (campos.get("NIVEL") or campos.get("CERTIFICADO") or '').upper()
    if "APAREJADOR" in c: return "APAREJADOR"
    if "OPERADOR" in c: return "OPERADOR"
    if "SUPERVISOR" in c: return "SUPERVISOR"
    return c or "OTROS"

def _slug(campos):
    return f"{campos['NOMBRE'].replace(' ','_')}_{campos['CC']}_{_cargo(campos)}_".upper()

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
