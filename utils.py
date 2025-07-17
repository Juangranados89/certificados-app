"""
utils.py
========
• ocr_pdf()                       → OCR (texto embebido o imagen)
• _extract_pdf()                  → Espacios Confinados
• extract_alturas()               → Trabajo en Alturas (nuevo, robusto)
• _extract_pdf_izajes()           → Izajes
• extract_certificate(..., mode)  → router
"""

from __future__ import annotations
import io, re, unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict

import fitz                 # PyMuPDF
import pytesseract
from PIL import Image

# ───────────────────────── OCR ──────────────────────────
def ocr_pdf(src) -> str:
    """src = ruta Path/str o bytes.  Devuelve texto OCR completo."""
    doc = fitz.open(stream=src, filetype="pdf") if not isinstance(src, (str, Path)) else fitz.open(str(src))
    out: list[str] = []
    for p in doc:
        t = p.get_text("text")
        if t.strip():
            out.append(t)
        else:
            pix = p.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(out)

# ─────────────────── helpers ────────────────────────────
def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).upper()

# ╔════════ Espacios Confinados ══════════════════════════╗
def _extract_pdf(text: str) -> Dict[str, str]:
    t = _norm(text)
    m = re.search(r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)", t)
    nombre = m.group(1).strip() if m else ""
    cc = ""
    m = re.search(r"C[.]?C\s*[:\-]?\s*([\d \.]{7,15})", t)
    if m:
        cc = m.group(1).replace(".", "").replace(" ", "")
    nivel = ""
    m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    if m:
        nivel = m.group(1).replace("Í", "I").title()
    fexp = ""
    m = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    if m:
        fexp = m.group(1).replace("-", "/")
    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "CURSO": "Espacios Confinados",
        "NIVEL": nivel,
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }

# ╔════════ Trabajo en Alturas  (robusto) ════════════════╗
_MESES = {m: i for i, m in enumerate(
    "ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE".split(), 1)
}
def _fecha_larga_a_ddmmaa(f: str) -> str:
    m = re.match(r"(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", _norm(f))
    return f"{int(m.group(1)):02d}/{_MESES[m.group(2)]:02d}/{m.group(3)}" if m else ""

_ALT_RE = re.compile(
    r"CERTIFICA QUE[:\s]+(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,}).+?"
    r"(?:C[. ]?C|CEDULA)[:\s]*(?P<cc>[\d\. ]{7,15}).+?"
    r"TRABAJO\s+EN\s+ALTURAS.+?"
    r"(?P<nivel>TRABAJADOR(?:ES)?\s+[A-ZÁÉÍÓÚ ]+).+?"
    r"DEL\s+(?P<fi>\d{1,2}\s+de\s+\w+\s+de\s+\d{4}).+?"
    r"AL\s+(?P<ff>\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    re.S | re.I
)

def extract_alturas(raw: str) -> Dict[str, str]:
    m = _ALT_RE.search(raw)
    if not m:
        return {}
    g = m.groupdict()
    fexp = _fecha_larga_a_ddmmaa(g["ff"])
    try:
        ven = datetime.strptime(fexp, "%d/%m/%Y").replace(year=datetime.strptime(fexp, "%d/%m/%Y").year + 2)
        fven = ven.strftime("%d/%m/%Y")
    except Exception:
        fven = ""
    return {
        "NOMBRE": g["nombre"].title(),
        "CC": g["cc"].replace(".", "").replace(" ", ""),
        "CURSO": "Trabajo En Alturas",
        "NIVEL": g["nivel"].title(),
        "FECHA_EXP": fexp,
        "FECHA_VEN": fven,
    }

# ╔════════ Izajes ════════════════════════════════════════╗
_IZAJE_RE = re.compile(
    r"CURSO[:\s]+(?P<curso>IZAJ[EA]S?).+?"
    r"NIVEL[:\s]+(?P<nivel>[A-ZÁÉÍÓÚ ]+).+?"
    r"(?:C[. ]?C|CEDULA)[:\s]*(?P<cc>[\d\. ]{7,15}).+?"
    r"NOMBRE[:\s]+(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,}).+?"
    r"FECHA EXP[:\s]+(?P<fexp>\d{2}[/-]\d{2}[/-]\d{4}).+?"
    r"FECHA VEN[:\s]+(?P<fven>\d{2}[/-]\d{2}[/-]\d{4})",
    re.S | re.I
)
def _extract_pdf_izajes(txt: str) -> Dict[str, str]:
    m = _IZAJE_RE.search(txt)
    if not m:
        return {}
    g = m.groupdict()
    return {
        "NOMBRE": g["nombre"].title(),
        "CC": g["cc"].replace(".", "").replace(" ", ""),
        "CURSO": g["curso"].title(),
        "NIVEL": g["nivel"].title(),
        "FECHA_EXP": g["fexp"].replace("-", "/"),
        "FECHA_VEN": g["fven"].replace("-", "/"),
    }

# ╔════════ Router general ════════════════════════════════╗
def extract_certificate(text: str, mode: str = "auto") -> Dict[str, str]:
    """
    mode: 'auto' | 'alturas' | 'confinados' | 'izajes'
    """
    if mode == "alturas":
        return extract_alturas(text)
    if mode == "confinados":
        return _extract_pdf(text)
    if mode == "izajes":
        return _extract_pdf_izajes(text)

    t = _norm(text)  # detección automática
    if "TRABAJO EN ALTURAS" in t:
        d = extract_alturas(text)
        if d:
            return d
    if "CONFINADOS" in t:
        d = _extract_pdf(text)
        if d:
            return d
    if "IZAJ" in t:
        d = _extract_pdf_izajes(text)
        if d:
            return d
    return {}
