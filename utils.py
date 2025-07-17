"""
utils.py
OCR y extractores de:
  • Espacios Confinados
  • Trabajo en Alturas  (robusto)
  • Izaje de Cargas     (JPEG / PDF)
exporta:
  ─ ocr_pdf(path|bytes)
  ─ ocr_img(path)            # JPEG-only
  ─ extract_certificate(txt, mode='auto'|'alturas'|'confinados'|'izajes')
"""

from __future__ import annotations
import io, re, unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict

import fitz                   # PyMuPDF
import pytesseract
from PIL import Image
from unidecode import unidecode


# ───────────────────────── OCR ──────────────────────────
def ocr_pdf(src) -> str:
    """Devuelve todo el texto de un PDF (ruta Path/str o bytes)"""
    doc = fitz.open(stream=src, filetype="pdf") if not isinstance(src, (str, Path)) else fitz.open(str(src))
    out = []
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


def ocr_img(path: Path) -> str:
    """OCR para JPEG/PNG"""
    img = Image.open(path).convert("RGB")
    return pytesseract.image_to_string(img, lang="spa")


# ───────────────────────── Utils ─────────────────────────
def _norm(s: str) -> str:
    """Mayúsculas sin tildes para búsquedas flexibles"""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).upper()


# ╔════════ Espacios Confinados ══════════════════════════╗
def _extract_pdf_confinados(text: str) -> Dict[str, str]:
    t = _norm(text)
    m = re.search(r"CONFINADOS[:\s\n]+([A-ZÑ ]{5,})[\s\n]+(?:C[.]?C|CEDULA)", t)
    nombre = m.group(1).title() if m else ""
    m = re.search(r"C[.]?C\s*[:\-]?\s*([\d \.]{7,15})", t)
    cc = m.group(1).replace(".", "").replace(" ", "") if m else ""
    m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    nivel = m.group(1).replace("Í", "I").title() if m else ""
    m = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = m.group(1).replace("-", "/") if m else ""

    return {
        "NOMBRE": nombre,
        "CC": cc,
        "CURSO": "Espacios Confinados",
        "NIVEL": nivel,
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }


# ╔════════ Trabajo en Alturas ═══════════════════════════╗
_MESES = {m: i for i, m in enumerate(
    "ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE".split(), 1)}

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
    re.S | re.I)

def _extract_pdf_alturas(txt: str) -> Dict[str, str]:
    m = _ALT_RE.search(txt)
    if not m:
        return {}
    g = m.groupdict()
    fexp = _fecha_larga_a_ddmmaa(g["ff"])
    try:
        fven = datetime.strptime(fexp, "%d/%m/%Y").replace(
            year=datetime.strptime(fexp, "%d/%m/%Y").year + 2).strftime("%d/%m/%Y")
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


# ╔════════ Izaje de Cargas ═══════════════════════════════╗
_IZAJ_RE = {
    "nombre":   re.compile(r"NOMBRES?[:\s]+([A-ZÑÁÉÍÓÚ ]{2,})", re.I),
    "apellido": re.compile(r"APELLIDOS?[:\s]+([A-ZÑÁÉÍÓÚ ]{2,})", re.I),
    "cc":       re.compile(r"CEDULA?[:\s]+([\d\. ]{7,15})", re.I),
    "consec":   re.compile(r"CONSECUTIVO[:\s]+([A-Z\d\- ]{4,})", re.I),
    "cert":     re.compile(r"CERTIFICADO[:\s]+([A-Z\d]{6,})", re.I),
    "fexp":     re.compile(r"EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", re.I),
    "fven":     re.compile(r"VENCIM(?:IEN)?TO[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})", re.I),
}

def _extract_izajes(texto: str) -> Dict[str, str]:
    t = unidecode(texto).upper()
    data = {}
    for k, rx in _IZAJ_RE.items():
        m = rx.search(t)
        if not m:
            return {}
        data[k] = m.group(1).strip()

    nombre_completo = f"{data['nombre'].title()} {data['apellido'].title()}"
    return {
        "NOMBRE": nombre_completo,
        "CC": data["cc"].replace(".", "").replace(" ", ""),
        "CURSO": "Izaje de Cargas",
        "NIVEL": data["consec"].title(),
        "FECHA_EXP": data["fexp"].replace("-", "/"),
        "FECHA_VEN": data["fven"].replace("-", "/"),
    }


# ╔════════ Router general ════════════════════════════════╗
def extract_certificate(text: str, mode: str = "auto") -> Dict[str, str]:
    if mode == "alturas":
        return _extract_pdf_alturas(text)
    if mode == "confinados":
        return _extract_pdf_confinados(text)
    if mode == "izajes":
        return _extract_izajes(text)

    t = _norm(text)
    if "TRABAJO EN ALTURAS" in t:
        d = _extract_pdf_alturas(text)
        if d:
            return d
    if "CONFINADOS" in t:
        d = _extract_pdf_confinados(text)
        if d:
            return d
    if "IZAJ" in t or "APAREJADOR" in t:
        d = _extract_izajes(text)
        if d:
            return d
    return {}
