"""
utils.py
========
• ocr_pdf()                    → OCR de PDF (texto embebido o escaneado)
• _extract_pdf()               → certificados de Espacios Confinados
• _extract_pdf_alturas()       → certificados de Trabajo en Alturas
• extract_certificate()        → router que decide qué extractor usar
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict

import fitz                 # PyMuPDF
import pytesseract
from PIL import Image

# ───────────────────── OCR ──────────────────────
def ocr_pdf(pdf_src) -> str:
    """
    Devuelve el texto completo de un PDF.
    • pdf_src puede ser ruta (str/Path) o bytes de Flask FileStorage.
    """
    if isinstance(pdf_src, (str, Path)):
        doc = fitz.open(str(pdf_src))
    else:  # bytes
        doc = fitz.open(stream=pdf_src, filetype="pdf")

    text_out: list[str] = []
    for page in doc:
        txt = page.get_text("text")
        if txt.strip():                # texto incrustado
            text_out.append(txt)
        else:                          # imagen → OCR
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text_out.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(text_out)


# ───────────────────── Utilidades ──────────────────────
def _norm(t: str) -> str:
    """Mayúsculas sin tildes para búsquedas insensibles."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)
    ).upper()


# ╔════════════ 1 · EXTRACTOR ESPACIOS CONFINADOS ════════════╗
def _extract_pdf(text: str) -> Dict[str, str]:
    t = _norm(text)
    nombre = ""

    # Estrategia prioritaria — entre CONFINADOS y C.C.
    m = re.search(
        r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)",
        t,
    )
    if m:
        nombre = m.group(1).strip()

    if not nombre:
        nom_m = re.search(r"NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})", t)
        if nom_m:
            nombre = nom_m.group(1).strip()
        else:
            cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
            if cc_m:
                nombre = t[: cc_m.span()[0]].splitlines()[-1].strip()

    cc = ""
    cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
    if cc_m:
        cc = cc_m.group(1).replace(".", "").replace(" ", "")

    nivel = ""
    niv_m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    if niv_m:
        nivel = niv_m.group(1).replace("Í", "I").title()

    f_any = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = f_any.group(1).replace("-", "/") if f_any else ""

    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "CURSO": "ESPACIOS CONFINADOS",
        "NIVEL": nivel,
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }


# ╔══════════ 2 · EXTRACTOR TRABAJO EN ALTURAS ══════════╗
MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def _fecha_larga_a_ddmmaa(frase: str) -> str:
    m = re.match(r"(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", _norm(frase))
    if not m:
        return ""
    d, mes, anio = m.groups()
    return f"{int(d):02d}/{MESES[mes]:02d}/{anio}"


_ALTURAS_RE = re.compile(
    r"CERTIFICA QUE[:\s]+"
    r"(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,})[\s\n]+"
    r"C[.]?C\s*(?P<cc>[\d\.]{7,15})[\s\n]+"
    r"Cursó.+?[:\s\n]+(?P<curso>[A-ZÁÉÍÓÚ ]+)[\s\n]+"
    r"(?P<nivel>TRABAJADOR(?:ES)?\s+[A-ZÁÉÍÓÚ ]+)[\s\n]+"
    r"del\s+(?P<fi>\d{1,2}\s+de\s+[a-záéíóú]+?\s+de\s+\d{4})"
    r"\s+al\s+(?P<ff>\d{1,2}\s+de\s+[a-záéíóú]+?\s+de\s+\d{4})",
    flags=re.IGNORECASE,
)


def _extract_pdf_alturas(texto: str) -> Dict[str, str]:
    m = _ALTURAS_RE.search(texto)
    if not m:
        return {}

    g = m.groupdict()
    f_exp = _fecha_larga_a_ddmmaa(g["ff"])

    try:
        dt_exp = datetime.strptime(f_exp, "%d/%m/%Y")
        dt_ven = dt_exp.replace(year=dt_exp.year + 2)
        f_ven = dt_ven.strftime("%d/%m/%Y")
    except ValueError:
        f_ven = ""

    return {
        "NOMBRE": g["nombre"].title(),
        "CC": g["cc"].replace(".", ""),
        "CURSO": g["curso"].title(),
        "NIVEL": g["nivel"].title(),
        "FECHA_EXP": f_exp,
        "FECHA_VEN": f_ven,
    }


# ╔══════════════ 3 · ROUTER GENERAL ═══════════════╗
def extract_certificate(text: str) -> Dict[str, str]:
    if "TRABAJO EN ALTURAS" in _norm(text):
        data = _extract_pdf_alturas(text)
        if data:
            return data
    return _extract_pdf(text)
