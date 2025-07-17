"""
utils.py
========
• ocr_pdf()                     -> OCR (texto embebido o escaneado)
• _extract_pdf()                -> Espacios Confinados
• _extract_pdf_alturas()        -> Trabajo en Alturas
• _extract_pdf_izajes()         -> Izajes
• extract_certificate(..., mode)→ router ('auto' | alturas | confinados | izajes)
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

# ─── OCR ────────────────────────────────────────────────
def ocr_pdf(pdf_src) -> str:
    """Devuelve el texto de un PDF (ruta Path/str o bytes)."""
    if isinstance(pdf_src, (str, Path)):
        doc = fitz.open(str(pdf_src))
    else:  # bytes
        doc = fitz.open(stream=pdf_src, filetype="pdf")

    out: list[str] = []
    for page in doc:
        txt = page.get_text("text")
        if txt.strip():
            out.append(txt)
        else:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(out)


# ─── helpers ─────────────────────────────────────────────
def _norm(t: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)
    ).upper()


# ╔════════ Espacios Confinados ════════╗
def _extract_pdf(text: str) -> Dict[str, str]:
    t = _norm(text)
    # nombre entre 'CONFINADOS' y 'C.C.'
    m = re.search(
        r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)",
        t,
    )
    nombre = m.group(1).strip() if m else ""

    cc = ""
    cc_m = re.search(r"C[.]?C\s*[:\-]?\s*([\d \.]{7,15})", t)
    if cc_m:
        cc = cc_m.group(1).replace(".", "").replace(" ", "")

    nivel = ""
    niv_m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    if niv_m:
        nivel = niv_m.group(1).replace("Í", "I").title()

    fexp = ""
    f_m = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    if f_m:
        fexp = f_m.group(1).replace("-", "/")

    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "CURSO": "ESPACIOS CONFINADOS",
        "NIVEL": nivel,
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }


# ╔════════ Trabajo en Alturas ═════════╗
MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}

def _fecha_larga(frase: str) -> str:
    m = re.match(r"(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", _norm(frase))
    if not m:
        return ""
    d, mes, a = m.groups()
    return f"{int(d):02d}/{MESES[mes]:02d}/{a}"

_ALTURAS_RE = re.compile(
    r"CERTIFICA QUE[:\s]+"
    r"(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,})[\s\n]+"
    r"C[.]?C\s*(?P<cc>[\d\.]{7,15})[\s\n]+"
    r"Cursó.+?[:\s\n]+(?P<curso>[A-ZÁÉÍÓÚ ]+)[\s\n]+"
    r"(?P<nivel>TRABAJADOR(?:ES)?\s+[A-ZÁÉÍÓÚ ]+)[\s\n]+"
    r"del\s+(?P<fi>\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})"
    r"\s+al\s+(?P<ff>\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})",
    re.I,
)

def _extract_pdf_alturas(tex: str) -> Dict[str, str]:
    m = _ALTURAS_RE.search(tex)
    if not m:
        return {}
    g = m.groupdict()
    f_exp = _fecha_larga(g["ff"])
    try:
        f_ven = datetime.strptime(f_exp, "%d/%m/%Y").replace(year=lambda y: y + 2).strftime("%d/%m/%Y")
    except Exception:
        f_ven = ""
    return {
        "NOMBRE": g["nombre"].title(),
        "CC": g["cc"].replace(".", ""),
        "CURSO": g["curso"].title(),
        "NIVEL": g["nivel"].title(),
        "FECHA_EXP": f_exp,
        "FECHA_VEN": f_ven,
    }


# ╔════════ Izajes ═════════╗
_IZAJE_RE = re.compile(
    r"CERTIFICA[:\s]+QUE[:\s]+"
    r"(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,})[\s\n]+"
    r"C[.]?C\s*(?P<cc>[\d\.]{7,15})[\s\n]+"
    r"CURSO[:\s]+(?P<curso>IZAJ[EA]S?)[\s\n]+"
    r"NIVEL[:\s]+(?P<nivel>[A-ZÁÉÍÓÚ ]+)[\s\n]+"
    r"FECHA EXP[:\s]+(?P<fexp>\d{2}[/-]\d{2}[/-]\d{4})"
    r".+?FECHA VEN[:\s]+(?P<fven>\d{2}[/-]\d{2}[/-]\d{4})",
    re.S | re.I,
)

def _extract_pdf_izajes(tex: str) -> Dict[str, str]:
    m = _IZAJE_RE.search(tex)
    if not m:
        return {}
    g = m.groupdict()
    return {
        "NOMBRE": g["nombre"].title(),
        "CC": g["cc"].replace(".", ""),
        "CURSO": g["curso"].title(),
        "NIVEL": g["nivel"].title(),
        "FECHA_EXP": g["fexp"].replace("-", "/"),
        "FECHA_VEN": g["fven"].replace("-", "/"),
    }


# ╔════════ Router general ═════════╗
def extract_certificate(text: str, mode: str = "auto") -> Dict[str, str]:
    """mode = 'auto' | 'alturas' | 'confinados' | 'izajes'"""
    t = _norm(text)

    if mode == "alturas":
        return _extract_pdf_alturas(text)
    if mode == "confinados":
        return _extract_pdf(text)
    if mode == "izajes":
        return _extract_pdf_izajes(text)

    # modo auto
    if "TRABAJO EN ALTURAS" in t:
        d = _extract_pdf_alturas(text)
        if d:
            return d
    if "CONFINADOS" in t:
        return _extract_pdf(text)
    if "IZAJ" in t:
        d = _extract_pdf_izajes(text)
        if d:
            return d
    return {}
