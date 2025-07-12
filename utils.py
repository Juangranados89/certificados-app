"""
utils.py  –  OCR, clasificación y renombrado de certificados

• PDFs de espacios confinados  (ENTRANTE / VIGÍA / SUPERVISOR …)
• JPEG/PNG de C&C (SUPERVISOR / APAREJADOR / OPERADOR)
• Convierte imágenes a PDF con el nombre final y estructura carpetas por cargo
"""

from __future__ import annotations
import os, shutil, re, unicodedata, fitz, pytesseract, zipfile
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter

# ───────────────────────── helpers de texto ──────────────────────────
def _norm(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', t)
                   if not unicodedata.combining(c)).upper()

# ───────────── cargo / nivel (para la carpeta final) ───────────────
def cargo_from_campos(c: dict[str, str]) -> str:
    cert  = c.get("CERTIFICADO", "").upper()
    nivel = c.get("NIVEL", "").upper()
    if "APAREJADOR" in (cert or nivel): return "APAREJADOR"
    if "OPERADOR"   in (cert or nivel): return "OPERADOR"
    if "SUPERVISOR" in (cert or nivel): return "SUPERVISOR"
    return nivel or "OTROS"

# ───────────── helpers de línea previa / entre bloques ─────────────
def _guess_prev_line(t: str, span):
    """Devuelve la línea justo antes de span."""
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

# ───────────── extractor PDF (espacios confinados) ─────────────
def _extract_pdf(text: str) -> dict[str, str]:
    t = _norm(text)

    # --- Nombre y CC ---
    nom = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    cc  = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)

    # Plan A: después de la palabra NOMBRE
    if nom:
        nombre = nom.group(1).strip()
    else:
        nombre = ''
        # Plan B: línea justo antes de la cédula
        if cc:
            nombre = _guess_prev_line(t, cc.span())

            # Plan C: busca hasta 3 líneas previas a la CC con 2+ palabras
            if not nombre:
                before = t[:cc.span()[0]].splitlines()[-4:-1]  # máx 3 previas
                for ln in reversed(before):
                    ln = ln.strip()
                    if re.fullmatch(r'[A-ZÑ ]{5,60}', ln) and len(ln.split()) >= 2:
                        nombre = ln
                        break

        # Si todo fa
