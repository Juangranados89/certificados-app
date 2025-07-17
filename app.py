"""
app.py  —  Entry-point WSGI para Flask / Render
==============================================

• Acepta PDF o ZIP desde un formulario (ruta /, plantilla index.html)
• OCR con utils.ocr_pdf()  →  decide extractor con utils.extract_certificate()
• Renombra y clasifica: /salida/<NIVEL>/<NOMBRE>_<CC>.pdf
• Muestra tabla de resultados en templates/resultado.html
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

# ─── IMPORTS DEL PROYECTO ─────────────────────────────────
# utils.py debe exponer:
#   • ocr_pdf()
#   • extract_certificate()
from utils import ocr_pdf, extract_certificate

# ─── CONFIG GLOBAL ───────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10          # máx. archivos por lote
MAX_CONTENT_MB = 25       # tamaño total request

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024  # 25 MB


# ─── HELPERS ─────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    """True si la extensión es .pdf o .zip."""
    return Path(filename).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(file_storage, dest: Path) -> List[Path]:
    """
    Guarda el ZIP subido y devuelve una lista de rutas PDF extraídos.
    Mantiene nombres seguros con secure_filename.
    """
    tmp_zip = dest / secure_filename(file_storage.filename)
    file_storage.save(tmp_zip)

    pdf_paths: list[Path] = []
    with zipfile.ZipFile(tmp_zip) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdf_paths.append(out)
    tmp_zip.unlink(missing_ok=True)
    return pdf_paths


def classify_folder(info: Dict[str, str]) -> Path:
    """Crea (si no existe) y devuelve carpeta de salida según NIVEL."""
    nivel = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    folder = OUTPUT_DIR / nivel
    folder.mkdir(exist_ok=True)
    return folder


# ─── RUTAS ───────────────────────────────────────────────
@app.get("/")
def index():
    """Formulario de subida."""
    return render_template("index.html")


@app.post("/start")
def start():
    """Procesa los archivos subidos y muestra la tabla de resultados."""
    uploads = request.files.getlist("files")
    if not uploads:
        flash("No se seleccionó ningún archivo", "warning")
        return redirect(url_for("index"))

    if len(uploads) > MAX_UPLOADS:
        flash(f"Máximo {MAX_UPLOADS} archivos por lote", "danger")
        return redirect(url_for("index"))

    tmpdir = Path(tempfile.mkdtemp())
    pdf_files: list[Path] = []

    # 1. Guardar PDFs y extraer ZIPs
    for fs in uploads:
        if not allowed_file(fs.filename):
            flash(f"Tipo no permitido: {fs.filename}", "danger")
            continue

        if fs.filename.lower().endswith(".zip"):
            pdf_files.extend(save_and_extract_zip(fs, tmpdir))
        else:
            dst = tmpdir / secure_filename(fs.filename)
            fs.save(dst)
            pdf_files.append(dst)

    # 2. OCR + extracción
    rows: list[Dict[str, str]] = []
    for pdf in pdf_files:
        try:
            text = ocr_pdf(pdf)
            info = extract_certificate(text)
        except Exception as err:
            flash(f"Error procesando {pdf.name}: {err}", "danger")
            continue

        new_name = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
        destino = classify_folder(info) / new_name
        shutil.copy2(pdf, destino)

        info["ARCHIVO"] = new_name
        rows.append(info)

    # 3. Limpiar temporales
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 4. Renderizar tabla de resultados
    return render_template(
        "resultado.html",
        rows=rows                     # lista de diccionarios
        # download_url=url_for("download_zip")  # ← si luego implementas ZIP global
    )


@app.get("/download/<path:fname>")
def download(fname: str):
    """Descarga directa de un PDF renombrado desde /salida/*."""
    fpath = OUTPUT_DIR / fname
    if not fpath.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fpath.parent, fpath.name, as_attachment=True)


# ─── MAIN LOCAL ───────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
