"""
utils.py – OCR robusto + procesado masivo de certificados
"""
from __future__ import annotations
import fitz, pytesseract, re, unicodedata, os, shutil, zipfile, pandas as pd
from PIL import Image, ImageOps, ImageFilter


# --------------------------------------------------------------------------- #
# Helpers de normalización y regex                                            #
# --------------------------------------------------------------------------- #
def _norm(txt: str) -> str:
    """Devuelve texto en MAYÚSCULAS y sin tildes."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", txt)
        if not unicodedata.combining(c)
    ).upper()


def _extract(text: str) -> dict[str, str]:
    """Extrae NOMBRE, CC, NIVEL y FECHA del texto OCR normalizado."""
    t = _norm(text)

    nombre = (
        re.search(r"NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})", t)
        or re.search(r"DE\s*:\s*([A-ZÑ ]{5,})", t)
        or re.search(r"FUNCIONARIO\s*[:\-]?\s*([A-ZÑ ]{5,})", t)
    )
    cc = re.search(
        r"(?:C[.]?C[.]?|CEDULA(?: DE CIUDADANIA)?|N[.ºO])\s*[:\-]?\s*([\d\.\s]{7,15})",
        t)
    nivel = re.search(
        r"\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b", t)
    fecha = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", t)

    return {
        "NOMBRE": nombre.group(1).strip() if nombre else "",
        "CC": (cc.group(1).replace(".", "").replace(" ", "")
               if cc else ""),
        "NIVEL": (nivel.group(1).replace("Í", "I") if nivel else ""),
        "FECHA": fecha.group(1).replace("-", "/") if fecha else "",
    }


# --------------------------------------------------------------------------- #
# OCR de una sola página (se asume la primera del PDF)                        #
# --------------------------------------------------------------------------- #
def _page_image(pdf_path: str, dpi: int) -> Image.Image:
    page = fitz.open(pdf_path)[0]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(
        img,
        lang="spa",
        config="--oem 3 --psm 6"      # LSTM + layout sencillo
    )


def parse_pdf(pdf_path: str) -> tuple[dict[str, str], str]:
    """
    Procesa un PDF y retorna:
        - campos  (dict con NOMBRE, CC, NIVEL, FECHA)
        - texto_raw (string completo OCR)

    Hace reintentos con más DPI y binarizado si falta alguno de los campos.
    """
    for dpi, prep in [(200, False), (300, True), (400, True)]:
        im = _page_image(pdf_path, dpi)
        if prep:                                 # filtros solo en 2º y 3º intento
            im = ImageOps.grayscale(im).filter(ImageFilter.SHARPEN)
            im = ImageOps.autocontrast(im)
        txt = _ocr(im)
        campos = _extract(txt)
        if all(campos.values()):
            return campos, txt                   # éxito perfecto
    return campos, txt                           # devuelve lo mejor obtenido


# --------------------------------------------------------------------------- #
# Procesado masivo: renombrar, clasificar y zip                               #
# --------------------------------------------------------------------------- #
def _copiar_renombrar(pdf_path: str, out_root: str, campos: dict[str, str]) -> str:
    # ── 1. Preparar cada parte ────────────────────────────────────────────────
    nombre = campos["NOMBRE"].strip().replace(" ", "_")
    cc     = campos["CC"]
    nivel  = campos["NIVEL"]

    # ── 2. Construir el nombre final ──────────────────────────────────────────
    filename = f"{nombre}_{cc}_{nivel}_".upper() + ".pdf"

    # ── 3. Carpeta por nivel (opcional) ───────────────────────────────────────
    dest_dir = os.path.join(out_root, nivel or "DESCONOCIDO")
    os.makedirs(dest_dir, exist_ok=True)

    # ── 4. Copiar ─────────────────────────────────────────────────────────────
    dst = os.path.join(dest_dir, filename)
    shutil.copy2(pdf_path, dst)
    return os.path.relpath(dst, out_root)



def process_pdfs(pdf_paths: list[str], out_dir: str):
    """
    Procesa una lista de PDFs, genera estructura de carpetas/zip y
    devuelve:
        - DataFrame con los registros
        - ruta del zip resultante
    """
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    registros = []
    for p in pdf_paths:
        campos, _ = parse_pdf(p)
        ruta_rel = _copiar_renombrar(p, out_dir, campos)
        campos["ARCHIVO"] = ruta_rel
        registros.append(campos)

    # Crear ZIP
    zip_path = os.path.join(out_dir, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _, files in os.walk(out_dir):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    zf.write(abs_f, arcname=os.path.relpath(abs_f, out_dir))

    df = pd.DataFrame(registros)
    return df, zip_path
