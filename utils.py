"""
utils.py  –  OCR, clasificación y renombrado de certificados

• Procesa certificados PDF de espacios confinados.
• Procesa certificados JPEG/PNG de C&C (Supervisor, Aparejador, Operador).
• Convierte imágenes a PDF con el nombre final.
• Estructura de carpetas por cargo/nivel.
"""

from __future__ import annotations
import os, shutil, re, unicodedata, fitz, pytesseract, zipfile
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter

# ───────────────────────── helpers de texto ──────────────────────────
def _norm(t: str) -> str:
    """Mayúsculas y sin tildes para búsquedas case-insensitive."""
    return ''.join(c for c in unicodedata.normalize('NFKD', t)
                   if not unicodedata.combining(c)).upper()

# ───────────────────────── cargo / nivel ─────────────────────────────
def cargo_from_campos(c: dict[str, str]) -> str:
    cert  = c.get("CERTIFICADO", "").upper()
    nivel = c.get("NIVEL", "").upper()
    if "APAREJADOR" in (cert or nivel): return "APAREJADOR"
    if "OPERADOR"   in (cert or nivel): return "OPERADOR"
    if "SUPERVISOR" in (cert or nivel): return "SUPERVISOR"
    return nivel or "OTROS"

# ───────────────────────── heurísticas PDF STC ───────────────────────
def _guess_prev_line(t: str, span):
    start = t.rfind('\n', 0, span[0]) + 1
    cand  = t[start:span[0]].strip()
    return cand if re.fullmatch(r'[A-ZÑ ]{5,60}', cand) else ''

def _guess_between(t: str):
    m = re.search(r'CONFINADOS:\s*([\s\S]{0,120}?)C[.]?C', t)
    if not m: return ''
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if re.fullmatch(r'[A-ZÑ ]{5,60}', ln):
            return ln
    return ''

# ───────────────────────── extractor PDF STC ─────────────────────────
def _extract_pdf(text: str) -> dict[str, str]:
    t = _norm(text)

    # Nombre + CC
    nom = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    cc  = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)
    nombre = nom.group(1).strip() if nom else (
        _guess_prev_line(t, cc.span()) if cc else _guess_between(t)
    )

    # Nivel (VIGÍ A / SUPERVISOR / etc.)
    nivel = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)

    # Fechas
    f_exp = re.search(r'FECHA DE EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    f_any = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)  # fallback

    return {
        "NOMBRE": nombre,
        "CC": cc.group(1).replace('.', '').replace(' ', '') if cc else '',
        "NIVEL": nivel.group(1).replace('Í', 'I') if nivel else '',
        "CERTIFICADO": '',
        "FECHA_EXP": (f_exp or f_any).group(1).replace('-', '/') if (f_exp or f_any) else '',
        "FECHA_VEN": '',
    }

# ───────────────────────── extractor JPEG/PNG C&C ────────────────────
def _extract_cc_img(text: str) -> dict[str, str]:
    t = _norm(text)

    # Nombre completo
    n = re.search(r'NOMBRES[:\s]+([A-ZÑ ]+)', t)
    a = re.search(r'APELLIDOS[:\s]+([A-ZÑ ]+)', t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ''

    # Cédula
    cc = re.search(r'C[ÉE]DULA[:\s]+([\d\.]{6,15})', t)

    # Encabezado amarillo
    cert = re.search(r'CERTIFICADO DE\s+([A-ZÑ /]+)', t)
    cert_val = cert.group(1).strip() if cert else ''

    # Fechas
    fexp = re.search(r'EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    fven = re.search(r'VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)

    # Cargo detectado
    nivel = ''
    for key in ('SUPERVISOR', 'APAREJADOR', 'OPERADOR'):
        if key in t:
            nivel = key
            break
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
        "NIVEL": nivel or cert_val
    }

# ───────────────────────── OCR engines ───────────────────────────────
def _page_img(pdf: str, dpi: int):
    page = fitz.open(pdf)[0]
    pix  = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang="spa", config="--oem 3 --psm 6")

# ───────────────────────── parsers principales ───────────────────────
def parse_pdf(path: str):
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        im = _page_img(path, dpi)
        if prep:
            im = ImageOps.autocontrast(ImageOps.grayscale(im).filter(ImageFilter.SHARPEN))
        txt = _ocr(im)
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

# ───────────────────────── renombrado / guardado ─────────────────────
def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    cargo = cargo_from_campos(campos)
    slug  = f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}_{cargo}_".upper()
    dest_dir = os.path.join(out_root, cargo)
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, f"{slug}.pdf")
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)

def save_image_as_pdf_renamed(img_path: str, out_root: str, campos: dict[str, str]) -> str:
    cargo = cargo_from_campos(campos)
    slug  = f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}_{cargo}_".upper()
    dest_dir = os.path.join(out_root, cargo)
    os.makedirs(dest_dir, exist_ok=True)
    pdf_out = os.path.join(dest_dir, f"{slug}.pdf")
    Image.open(img_path).convert("RGB").save(pdf_out, "PDF", resolution=150.0)
    return os.path.relpath(pdf_out, out_root)
