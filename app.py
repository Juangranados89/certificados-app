"""
app.py  —  entry-point WSGI para Render/Gunicorn
================================================
• Acepta PDF / ZIP desde un formulario
• Extrae texto con `ocr_pdf` y decide extractor con `extract_certificate`
• Renombra y clasifica en /salida/<NIVEL>/NOMBRE_CC.pdf
• Muestra tabla de resultados (templates/resultado.html)
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

# ─── IMPORTS DEL PROYECTO ────────────────────────────────────────────
# utils.py DEBE contener:
#   • ocr_pdf()
#   • extract_certificate()
from utils import ocr_pdf, extract_certificate

# ─── CONFIG GLOBAL ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10
MAX_CONTENT_MB = 25

app = Flask(__name__)               # ← *******   OBJETO WSGI  *******
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024

# ─── HELPERS ─────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(file_storage, dest: Path) -> List[Path]:
    """Guarda el ZIP y devuelve la lista de PDF extraídos."""
    tmp_zip = dest / secure_filename(file_storage.filename)
    file_storage.save(tmp_zip)

    pdfs: list[Path] = []
    with zipfile.ZipFile(tmp_zip) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdfs.append(out)
    tmp_zip.unlink(missing_ok=True)
    return pdfs


def classify_folder(info: Dict[str, str]) -> Path:
    nivel = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    folder = OUTPUT_DIR / nivel
    folder.mkdir(exist_ok=True)
    return folder


# ─── RUTAS ───────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/start")
def start():
    uploads = request.files.getlist("files")
    if not uploads:
        flash("No se seleccionó ningún archivo", "warning")
        return redirect(url_for("index"))

    if len(uploads) > MAX_UPLOADS:
        flash(f"Máximo {MAX_UPLOADS} archivos por lote", "danger")
        return redirect(url_for("index"))

    tmpdir = Path(tempfile.mkdtemp())
    pdfs: list[Path] = []

    # 1. Guardar y descomprimir
    for fs in uploads:
        if not allowed_file(fs.filename):
            flash(f"Tipo no permitido: {fs.filename}", "danger")
            continue

        if fs.filename.lower().endswith(".zip"):
            pdfs.extend(save_and_extract_zip(fs, tmpdir))
        else:
            dst = tmpdir / secure_filename(fs.filename)
            fs.save(dst)
            pdfs.append(dst)

    # 2. Procesar
    rows: list[Dict[str, str]] = []
    for pdf in pdfs:
        try:
            text = ocr_pdf(pdf)
            info = extract_certificate(text)
        except Exception as e:
            flash(f"Error en {pdf.name}: {e}", "danger")
            continue

        new_name = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
        shutil.copy2(pdf, classify_folder(info) / new_name)
        info["ARCHIVO"] = new_name
        rows.append(info)

    shutil.rmtree(tmpdir, ignore_errors=True)

    return render_template("resultado.html", rows=rows)


@app.get("/download/<path:fname>")
def download(fname: str):
    fpath = OUTPUT_DIR / fname
    if not fpath.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fpath.parent, fpath.name, as_attachment=True)


# ─── SOLO PARA EJECUCIÓN LOCAL ───────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
