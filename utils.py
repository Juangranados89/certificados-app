"""
utils.py
========
OCR + extractores de certificados (Confinados, Alturas, Izajes)
"""

from __future__ import annotations
import io, re, unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict

import fitz                 # PyMuPDF
import pytesseract
from PIL import Image

# ─── OCR ──────────────────────────────────────────────────
def ocr_pdf(src) -> str:
    """
    src: ruta Path/str o bytes. Devuelve texto completo.
    """
    doc = fitz.open(stream=src, filetype="pdf") if not isinstance(src, (str, Path)) else fitz.open(str(src))
    out: list[str] = []
    for page in doc:
        txt = page.get_text("text")
        if txt.strip():
            out.append(txt)
        else:                              # rasterizar + Tesseract
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(out)

# ─── Normalizador ─────────────────────────────────────────
def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).upper()

# ╔════════ Espacios Confinados ════════════════════════════╗
def _extract_pdf(text: str) -> Dict[str, str]:
    t = _norm(text)
    m = re.search(r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)", t)
    nombre = m.group(1).strip() if m else ""
    cc = ""
    m = re.search(r"C[.]?C\s*[:\-]?\s*([\d \.]{7,15})", t)
    if m: cc = m.group(1).replace(".", "").replace(" ", "")
    nivel = ""
    m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    if m: nivel = m.group(1).replace("Í", "I").title()
    fexp = ""
    m = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    if m: fexp = m.group(1).replace("-", "/")
    return {"NOMBRE": nombre.title(), "CC": cc, "CURSO": "ESPACIOS CONFINADOS",
            "NIVEL": nivel, "FECHA_EXP": fexp, "FECHA_VEN": ""}

# ╔════════ Trabajo en Alturas ═════════════════════════════╗
MESES = {"ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,
         "JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}
def _fecha_larga(frase:str)->str:
    m = re.match(r"(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", _norm(frase))
    return f"{int(m.group(1)):02d}/{MESES[m.group(2)] :02d}/{m.group(3)}" if m else ""

_ALT_RE = re.compile(
    r"CURSO[:\s]+TRABAJO\s+EN\s+ALTURAS.*?"
    r"NIVEL[:\s]+(?P<nivel>[A-ZÁÉÍÓÚ ]+).*?"
    r"(?:C[. ]?C|CEDULA)[:\s]*?(?P<cc>[\d\.]{7,15}).*?"
    r"NOMBRE[:\s]+(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,})"
    r".*?DEL\s+(?P<fi>\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})"
    r".*?AL\s+(?P<ff>\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})",
    re.S|re.I)

def _extract_pdf_alturas(txt:str)->Dict[str,str]:
    m=_ALT_RE.search(txt)
    if not m: return {}
    g=m.groupdict()
    fexp=_fecha_larga(g["ff"])
    try:  fven=datetime.strptime(fexp,"%d/%m/%Y").replace(year=lambda y:y+2).strftime("%d/%m/%Y")
    except: fven=""
    return {"NOMBRE":g["nombre"].title(),"CC":g["cc"].replace('.',''),
            "CURSO":"Trabajo En Alturas","NIVEL":g["nivel"].title(),
            "FECHA_EXP":fexp,"FECHA_VEN":fven}

# ╔════════ Izajes ═════════════════════════════════════════╗
_IZAJE_RE = re.compile(
    r"CURSO[:\s]+(?P<curso>IZAJ[EA]S?).*?"
    r"NIVEL[:\s]+(?P<nivel>[A-ZÁÉÍÓÚ ]+).*?"
    r"(?:C[. ]?C|CEDULA)[:\s]*(?P<cc>[\d\.]{7,15}).*?"
    r"NOMBRE[:\s]+(?P<nombre>[A-ZÑÁÉÍÓÚ ]{5,}).*?"
    r"FECHA EXP[:\s]+(?P<fexp>\d{2}[/-]\d{2}[/-]\d{4}).*?"
    r"FECHA VEN[:\s]+(?P<fven>\d{2}[/-]\d{2}[/-]\d{4})",
    re.S|re.I)

def _extract_pdf_izajes(txt:str)->Dict[str,str]:
    m=_IZAJE_RE.search(txt)
    if not m:return {}
    g=m.groupdict()
    return {"NOMBRE":g["nombre"].title(),"CC":g["cc"].replace('.',''),
            "CURSO":g["curso"].title(),"NIVEL":g["nivel"].title(),
            "FECHA_EXP":g["fexp"].replace('-','/'),"FECHA_VEN":g["fven"].replace('-','/')}

# ╔════════ Router general ════════════════════════════════╗
def extract_certificate(text:str, mode:str="auto")->Dict[str,str]:
    t=_norm(text)
    if mode=="alturas":       return _extract_pdf_alturas(text)
    if mode=="confinados":    return _extract_pdf(text)
    if mode=="izajes":        return _extract_pdf_izajes(text)

    if "TRABAJO EN ALTURAS" in t:
        d=_extract_pdf_alturas(text);  return d if d else {}
    if "CONFINADOS" in t:
        return _extract_pdf(text)
    if "IZAJ" in t:
        d=_extract_pdf_izajes(text);   return d if d else {}
    return {}
