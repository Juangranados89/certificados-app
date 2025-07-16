# utils.py
"""
utils.py
---------

OCR y renombrado de certificados:

• PDF de espacios confinados
• PDF de Trabajo en Alturas (San Gabriel)
• JPEG/PNG de C&C
• Convierte imágenes a PDF con el nombre final.
• Clasifica carpetas por cargo/nivel.
"""

from __future__ import annotations
import os, re, shutil, unicodedata
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps, ImageFilter

# ─────────────────────── Helpers básicos ────────────────────────
def _norm(t: str) -> str:
    """Mayúsculas sin tildes para búsquedas insensibles."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)
    ).upper()

def _ocr(img: Image.Image) -> str:
    """OCR español con Tesseract."""
    return pytesseract.image_to_string(img, lang="spa", config="--oem 3 --psm 6")

# ─────────────────── Helpers de Fecha ─────────────────────
MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}

def _fecha_larga_a_ddmmaa(frase: str) -> str:
    """Convierte '14 de julio de 2025' a '14/07/2025'."""
    norm_frase = _norm(frase)
    for nombre_mes, num_mes in MESES.items():
        if nombre_mes in norm_frase:
            norm_frase = norm_frase.replace(nombre_mes, str(num_mes))
            break
            
    m = re.search(r"(\d{1,2}) DE (\d{1,2}) DE (\d{4})", norm_frase)
    if not m:
        return ""
    d, mes, anio = m.groups()
    return f"{int(d):02d}/{int(mes):02d}/{anio}"

# ╔════════════ 1 · EXTRACTOR ALTURAS 'SAN GABRIEL' ════════════╗
_ALTURAS_SG_RE = re.compile(
    r"CERTIFICA QUE[:\s]+"
    r"(?P<nombre>[A-ZÑÁÉÍÓÚ ]+)[\s\n]+"
    r"C[.]?C\s*(?P<cc>[\d\.]{7,15}).*?"
    r"TRABAJO EN ALTURAS[\s\n]+"
    r"(?P<nivel>TRABAJADOR AUTORIZADO).*?"
    r"Expedido en.*?(?P<f_exp>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    flags=re.IGNORECASE | re.DOTALL,
)

def _extract_pdf_alturas_sangabriel(texto: str) -> dict[str, str]:
    """Extractor específico para certificados de Alturas San Gabriel."""
    m = _ALTURAS_SG_RE.search(texto)
    if not m:
        return {}

    g = m.groupdict()
    f_exp_str = _fecha_larga_a_ddmmaa(g["f_exp"])
    f_ven_str = ""
    
    try:
        dt_exp = datetime.strptime(f_exp_str, "%d/%m/%Y")
        # Vigencia de 18 meses según Res. 4272 de 2021
        dt_ven = dt_exp + relativedelta(months=+18)
        f_ven_str = dt_ven.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        pass

    return {
        "NOMBRE": g["nombre"].strip().title(),
        "CC": g["cc"].replace(".", "").replace(" ", ""),
        "NIVEL": g["nivel"].strip().title(),
        "CERTIFICADO": "Trabajo en Alturas",
        "FECHA_EXP": f_exp_str,
        "FECHA_VEN": f_ven_str,
    }

# ╔════════════ 2 · EXTRACTOR ESPACIOS CONFINADOS ════════════╗
def _extract_pdf_confinados(text: str) -> dict[str, str]:
    """Extractor para certificados de Espacios Confinados (y otros por defecto)."""
    t = _norm(text)
    nombre = ""
    pat_directo = r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)"
    nom_directo_m = re.search(pat_directo, t)
    if nom_directo_m:
        nombre = nom_directo_m.group(1).strip()

    if not nombre:
        cc_m_check = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
        if cc_m_check:
            linea_anterior = t[: cc_m_check.span()[0]].splitlines()[-1].strip()
            if re.fullmatch(r"[A-ZÑ ]{5,60}", linea_anterior) and len(linea_anterior.split()) >= 2:
                nombre = linea_anterior

    cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
    cc = cc_m.group(1).replace(".", "").replace(" ", "") if cc_m else ""

    niv_m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    nivel = niv_m.group(1).replace("Í", "I").title() if niv_m else ""
    
    fany_m = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = fany_m.group(1).replace("-", "/") if fany_m else ""

    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "NIVEL": nivel,
        "CERTIFICADO": "Espacios Confinados",
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }

# ╔═══════════ 3 · EXTRACTOR IMÁGENES C&C ═══════════╗
def _extract_cc_img(text: str) -> dict[str, str]:
    t = _norm(text)
    n = re.search(r"NOMBRES[:\s]+([A-ZÑ ]+)", t)
    a = re.search(r"APELLIDOS[:\s]+([A-ZÑ ]+)", t)
    nombre = f"{n.group(1).strip()} {a.group(1).strip()}" if n and a else ""

    cc_m = re.search(r"C[ÉE]DULA[:\s]+([\d\.]{6,15})", t)
    cc = cc_m.group(1).replace(".", "") if cc_m else ""

    cert_m = re.search(r"CERTIFICADO DE\s+([A-ZÑ /]+)", t)
    cert = cert_m.group(1).strip() if cert_m else ""

    fexp_m = re.search(r"EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fven_m = re.search(r"VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = fexp_m.group(1).replace("-", "/") if fexp_m else ""
    fven = fven_m.group(1).replace("-", "/") if fven_m else ""

    nivel = ""
    for key in ("SUPERVISOR", "APAREJADOR", "OPERADOR"):
        if key in t:
            nivel = key
            break

    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "CERTIFICADO": cert.title(),
        "FECHA_EXP": fexp,
        "FECHA_VEN": fven,
        "NIVEL": nivel.title() or cert.title(),
    }

# ╔═══════════ ROUTER Y PROCESADORES DE ARCHIVO ════════════╗
def _pdf_to_text_hybrid(path: str) -> str:
    """Extrae texto de un PDF, usando OCR como fallback si es una imagen."""
    try:
        doc = fitz.open(path)
        txt = "".join(page.get_text() for page in doc)
        if txt.strip():
            doc.close()
            return txt
        
        # Fallback a OCR si no hay texto
        pix = doc.load_page(0).get_pixmap(dpi=300, colorspace=fitz.csRGB)
        doc.close()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = ImageOps.autocontrast(ImageOps.grayscale(img).filter(ImageFilter.SHARPEN))
        return _ocr(img)
    except Exception:
        return ""

def parse_image(path: str):
    """Procesa un archivo de imagen."""
    txt = _ocr(Image.open(path).convert("RGB"))
    campos = _extract_cc_img(txt)
    return campos, txt, path

def parse_file(path: str):
    """Función principal que actúa como router."""
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png"):
        return parse_image(path)

    if ext == ".pdf":
        txt = _pdf_to_text_hybrid(path)
        norm_txt = _norm(txt)
        campos = {}

        # --- Lógica del Router ---
        # 1. Intenta con el extractor más específico primero.
        if "ALTURAS SAN GABRIEL" in norm_txt:
            campos = _extract_pdf_alturas_sangabriel(txt)
        
        # 2. Si no funciona, usa el extractor por defecto (Confinados).
        if not campos:
            campos = _extract_pdf_confinados(txt)
            
        return campos, txt, path

    raise ValueError("Tipo de archivo no soportado")

# ─────────────────── Renombrado y Guardado ────────────────────
def _cargo(campos):
    """Determina el cargo/nivel para nombrar la carpeta."""
    c = str(campos.get("NIVEL") or campos.get("CERTIFICADO") or "").upper()
    for key in ["APAREJADOR", "OPERADOR", "SUPERVISOR", "ENTRANTE", "VIGIA", "TRABAJADOR AUTORIZADO"]:
        if key in c:
            # Simplifica 'TRABAJADOR AUTORIZADO' a 'ALTURAS' para la carpeta
            return "ALTURAS" if key == "TRABAJADOR AUTORIZADO" else key
    return c or "OTROS"

def _slug(campos):
    """Crea el nombre base del archivo."""
    nombre = str(campos.get("NOMBRE", "")).replace(" ", "_")
    cc = str(campos.get("CC", ""))
    cargo = _cargo(campos)
    return f"{nombre}_{cc}_{cargo}_".upper()

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
