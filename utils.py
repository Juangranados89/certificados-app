"""
Funciones de OCR y extracción de datos para certificados.

• _extract_pdf(...)            → extractor original (Espacios Confinados)
• _extract_pdf_alturas(...)    → extractor nuevo (Trabajo en Alturas)
• extract_certificate(...)     → router que decide qué extractor usar
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Dict

# ───────────────────────── Helpers ──────────────────────────
def _norm(text: str) -> str:
    """Mayúsculas sin tildes (útil para búsquedas insensibles)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).upper()


# ╔═════════════════ 1 · EXTRACTOR ESPACIOS CONFINADOS ═════════════════╗
def _extract_pdf(text: str) -> Dict[str, str]:
    """Extractor original para certificados de espacios confinados."""
    t = _norm(text)
    nombre = ""

    # Estrategia prioritaria — entre CONFINADOS y C.C.
    pat_directo = (
        r"CONFINADOS[:\s\n]+([A-ZÑ ]{2,}(?:\s+[A-ZÑ ]{2,}){1,4})[\s\n]+(?:C[.]?C|CEDULA)"
    )
    m = re.search(pat_directo, t)
    if m:
        nombre = m.group(1).strip()

    # Fallbacks
    if not nombre:
        nom_m = re.search(r"NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})", t)
        if nom_m:
            nombre = nom_m.group(1).strip()
        else:
            cc_m = re.search(
                r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t
            )
            if cc_m:
                lineas = t[: cc_m.span()[0]].splitlines()
                if lineas:
                    nombre = lineas[-1].strip()

    cc_m = re.search(r"(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})", t)
    cc = cc_m.group(1).replace(".", "").replace(" ", "") if cc_m else ""

    niv_m = re.search(r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    nivel = niv_m.group(1).replace("Í", "I") if niv_m else ""

    f_any = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)
    fexp = f_any.group(1).replace("-", "/") if f_any else ""

    return {
        "NOMBRE": nombre.title(),
        "CC": cc,
        "CURSO": "ESPACIOS CONFINADOS",
        "NIVEL": nivel.title(),
        "FECHA_EXP": fexp,
        "FECHA_VEN": "",
    }


# ╔══════════════ 2 · EXTRACTOR TRABAJO EN ALTURAS ══════════════╗
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
    """'14 de julio de 2025'  →  '14/07/2025'."""
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
    """Devuelve {} si el patrón no encaja."""
    m = _ALTURAS_RE.search(texto)
    if not m:
        return {}

    g = m.groupdict()
    f_exp = _fecha_larga_a_ddmmaa(g["ff"])

    # Validez estándar: 2 años
    try:
        dt_exp = datetime.strptime(f_e)
