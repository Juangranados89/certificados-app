"""
Flask app completa: acepta PDF/ZIP, extrae datos y clasifica.
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

# ───────── Configuración ─────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB


# ───────── Helpers ─────────
def allowed_file(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(file_storage, dest: Path) -> List[Path]:
    """Guarda ZIP y devuelve lista de PDF extraídos."""
    z_tmp = dest / secure_filename(file_storage.filename)
    file_storage.save(z_tmp)

    pdfs: list[Path] = []
    with zipfile.ZipFile(z_tmp) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdfs.append(out)
    z_tmp.unlink()
    return pdfs


def classify_folder(info: Dict[str, str]) -> Path:
    nivel = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    target = OUTPUT_DIR / nivel
    target.mkdir(exist_ok=True)
    return target


# ───────── Rutas ─────────
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
        flash(f"Máximo {MAX_UPLOADS} archivos a la vez", "danger")
        return redirect(url_for("index"))

    tmpdir = Path(tempfile.mkdtemp())
    all_pdfs: list[Path] = []

    # 1) guardar / descomprimir
    for fs in uploads:
        if not allowed_file(fs.filename):
            flash(f"Tipo no permitido: {fs.filename}", "danger")
            continue
        if fs.filename.lower().endswith(".zip"):
            all_pdfs.extend(save_and_extract_zip(fs, tmpdir))
        else:
            p = tmpdir / secure_filename(fs.filename)
            fs.save(p)
            all_pdfs.append(p)

    # 2) procesar
    rows: list[Dict[str, str]] = []
    for pdf in all_pdfs:
        try:
            text = ocr_pdf(pdf)
            info = extract_certificate(text)
        except Exception as e:
            flash(f"Error en {pdf.name}: {e}", "danger")
            continue

        new_name = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
        destino = classify_folder(info) / new_name
        shutil.copy2(pdf, destino)

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


# ───────── Main local ─────────
if __name__ == "__main__":
    app.run(debug=True)
