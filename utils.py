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
import io, os, re, shutil, unicodedata
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, Tuple

import fitz            # PyMuPDF
import pytesseract
from PIL import Image, ImageOps, ImageFilter

# ───────────────────── Helpers básicos ────────────────────────
def _norm(t: str) -> str:
    """Mayúsculas sin tildes para búsquedas insensibles."""
    return "".join(c for c in unicodedata.normalize("NFKD", t)
                   if not unicodedata.combining(c)).upper()

def _ocr(img: Image.Image) -> str:
    """OCR español con Tesseract."""
    return pytesseract.image_to_string(img, lang="spa", config="--oem 3 --psm 6")

# ─────────────────── Helpers de Fecha ─────────────────────
MESES = {"ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,
         "JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

def _fecha_larga_a_ddmmaa(frase: str) -> str:
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

# ╔════════════ 1 · EXTRACTOR ALTURAS 'SAN GABRIEL' ══════════╗
_ALTURAS_SG_RE = re.compile(
    r"CERTIFICA QUE[:\s]+(?P<nombre>[A-ZÑÁÉÍÓÚ ]+)[\s\n]+"
    r"C[.]?C\s*(?P<cc>[\d\.]{7,15}).*?"
    r"TRABAJO EN ALTURAS[\s\n]+(?P<nivel>TRABAJADOR AUTORIZADO).*?"
    r"Expedido en.*?(?P<f_exp>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    flags=re.IGNORECASE | re.DOTALL,
)

def _extract_pdf_alturas_sangabriel(texto: str) -> Dict[str, str]:
    m = _ALTURAS_SG_RE.search(texto)
    if not m:
        return {}
    g = m.groupdict()
    f_exp = _fecha_larga_a_ddmmaa(g["f_exp"])
    f_ven = ""
    try:
        dt_exp = datetime.strptime(f_exp, "%d/%m/%Y")
        dt_ven = dt_exp + relativedelta(months=+18)
        f_ven = dt_ven.strftime("%d/%m/%Y")
    except Exception:
        pass
    return {
        "NOMBRE": g["nombre"].strip().title(),
        "CC": g["cc"].replace(".", "").replace(" ", ""),
        "NIVEL": g["nivel"].title(),
        "CERTIFICADO": "Trabajo en Alturas",
        "FECHA_EXP": f_exp,
        "FECHA_VEN": f_ven,
    }

# ╔════════════ 2 · EXTRACTOR ESPACIOS CONFINADOS ════════════╗
def _extract_pdf_confinados(text: str) -> Dict[str, str]:
    t = _norm(text)
    pat = r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)"
    m = re.search(pat, t)
    nombre = m.group(1).strip() if m else ""
    if not nombre:
        cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
        if cc_m:
            nombre = t[: cc_m.span()[0]].splitlines()[-1].strip()
    cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
    cc = cc_m.group(1).replace(".", "").replace(" ", "") if cc_m else ""
    niv_m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    nivel = niv_m.group(1).replace("Í", "I").title() if niv_m else ""
    f_any = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = f_any.group(1).replace("-", "/") if f_any else ""
    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "NIVEL": nivel,
        "CERTIFICADO": "Espacios Confinados",
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }

# ╔════════════ 3 · EXTRACTOR IMÁGENES C&C ═════════════╗
def _extract_cc_img(text: str) -> Dict[str, str]:
    t = _norm(text)
    nombres = re.search(r"NOMBRES[:\s]+([A-ZÑ ]+)", t)
    apellidos = re.search(r"APELLIDOS[:\s]+([A-ZÑ ]+)", t)
    nombre = f"{nombres.group(1)} {apellidos.group(1)}".title() if nombres and apellidos else ""
    cc_m = re.search(r"C[ÉE]DULA[:\s]+([\d\.]{6,15})", t)
    cc = cc_m.group(1).replace(".", "") if cc_m else ""
    cert_m = re.search(r"CERTIFICADO DE\s+([A-ZÑ /]+)", t)
    cert = cert_m.group(1).title() if cert_m else ""
    fexp_m = re.search(r"EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fven_m = re.search(r"VENCIMIENTO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", t)
    return {
        "NOMBRE": nombre,
        "CC": cc,
        "CERTIFICADO": cert,
        "FECHA_EXP": fexp_m.group(1).replace("-", "/") if fexp_m else "",
        "FECHA_VEN": fven_m.group(1).replace("-", "/") if fven_m else "",
        "NIVEL": cert or "",
    }

# ╔════════════ 4 · OCR PDF (híbrido) ═════════════╗
def _pdf_to_text_hybrid(path: str | Path | bytes) -> str:
    """Extrae texto de PDF; si no hay, aplica OCR a imagen rasterizada."""
    if isinstance(path, (str, Path)):
        doc = fitz.open(str(path))
    else:  # bytes
        doc = fitz.open(stream=path, filetype="pdf")

    texto: list[str] = []
    for page in doc:
        t = page.get_text()
        if t.strip():
            texto.append(t)
        else:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = ImageOps.autocontrast(ImageOps.grayscale(img).filter(ImageFilter.SHARPEN))
            texto.append(_ocr(img))
    doc.close()
    return "\n".join(texto)

# ╔════════════ 5 · API pública para app.py ═════════════╗
def ocr_pdf(pdf_src) -> str:
    """
    Wrapper público: app.py importará esta función.

    • Acepta ruta, Path o bytes.
    • Devuelve texto plano del PDF.
    """
    return _pdf_to_text_hybrid(pdf_src)

# ╔════════════ 6 · ROUTER principal ═════════════╗
def extract_certificate(texto: str) -> Dict[str, str]:
    if "ALTURAS SAN GABRIEL" in _norm(texto):
        data = _extract_pdf_alturas_sangabriel(texto)
        if data:
            return data
    return _extract_pdf_confinados(texto)

# (Se mantiene el resto de funciones de renombrado/guardado…)
