"""
app.py
======
Flask app para subir, procesar y clasificar certificados PDF/ZIP.

Flujo:
1.  GET  /            → formulario (index.html)
2.  POST /start       → OCR + extracción → renombra y guarda por carpeta
3.  GET  /resultado   → tabla con los datos extraídos
4.  GET  /download/<fname> → descarga directa de un PDF renombrado
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
)
from werkzeug.utils import secure_filename

from utils import extract_certificate, ocr_pdf

# ───────────────────── Config ─────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10           # máx. archivos en un lote
MAX_CONTENT_MB = 25        # límite total de request

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024


# ───────────────────── Helpers ─────────────────────
def allowed_file(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(file_storage, dest: Path) -> List[Path]:
    """Guarda el ZIP y devuelve la lista de PDF extraídos."""
    zip_tmp = dest / secure_filename(file_storage.filename)
    file_storage.save(zip_tmp)

    pdfs: list[Path] = []
    with zipfile.ZipFile(zip_tmp) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdfs.append(out)
    zip_tmp.unlink(missing_ok=True)
    return pdfs


def classify_folder(info: Dict[str, str]) -> Path:
    """
    Devuelve carpeta destino tomando 'NIVEL':
    - SUPERVISOR, OPERADOR, APAREJADOR, TRABAJADOR AUTORIZADO …
    """
    nivel = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    folder = OUTPUT_DIR / nivel
    folder.mkdir(exist_ok=True)
    return folder


# ───────────────────── Rutas ─────────────────────
@app.get("/")
def index():
    """Muestra formulario de subida."""
    return render_template("index.html")


@app.post("/start")
def start():
    """Procesa los PDF/ZIP subidos y genera la vista de resultados."""
    uploads = request.files.getlist("files")
    if not uploads:
        flash("No se seleccionó ningún archivo", "warning")
        return redirect(url_for("index"))

    if len(uploads) > MAX_UPLOADS:
        flash(f"Máximo {MAX_UPLOADS} archivos por lote", "danger")
        return redirect(url_for("index"))

    # Carpeta temporal para trabajo
    tmpdir = Path(tempfile.mkdtemp())
    pdf_files: list[Path] = []

    # 1. Guardar PDF directos o extraer ZIP
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

    # 2. Procesar cada PDF
    registros: list[Dict[str, str]] = []
    for pdf in pdf_files:
        try:
            texto = ocr_pdf(pdf)
            info = extract_certificate(texto)
        except Exception as err:
            flash(f"Error en {pdf.name}: {err}", "danger")
            continue

        # Renombrar: NOMBRE_CC.pdf
        new_name = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
        destino = classify_folder(info) / new_name
        shutil.copy2(pdf, destino)

        info["ARCHIVO"] = new_name
        registros.append(info)

    # 3. Limpieza
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 4. Mostrar resultados
    return render_template("resultado.html", rows=registros)


@app.get("/download/<path:fname>")
def download(fname: str):
    """Descargar un PDF renombrado desde /salida/*."""
    fpath = OUTPUT_DIR / fname
    if not fpath.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fpath.parent, fpath.name, as_attachment=True)


# ───────────────────── Main local ─────────────────────
if __name__ == "__main__":
    app.run(debug=True)
