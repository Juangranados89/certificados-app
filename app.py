"""app.py  —  Flask application completa
================================================
Esta versión integra el nuevo router `extract_certificate` para reconocer
tanto certificados de **Espacios Confinados** como de **Trabajo en Alturas**
sin modificar el resto del flujo.

▪ Rutas:
   • GET  /          → formulario de subida (index.html)
   • POST /start     → procesa PDF/ZIP, extrae campos, clasifica, genera tabla
   • GET  /download/<fname>  → descarga archivos de salida

Nota: Si tu proyecto tenía funciones auxiliares (p.ej. generar Excel, ZIP
clasificado, barra de progreso SSE), colócalas donde indiqué con “TODO”.
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

from utils import extract_certificate, ocr_pdf  # ocr_pdf ya existía en utils

# ───────────────────── Configuración ─────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10  # número máximo de PDF que aceptaremos en un lote

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB por request


# ───────────────────── Helpers ───────────────────────────

def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(file_storage, dest: Path) -> List[Path]:
    """Guarda el ZIP subido y devuelve la lista de PDF extraídos."""
    z_tmp = dest / secure_filename(file_storage.filename)
    file_storage.save(z_tmp)

    pdf_paths: List[Path] = []
    with zipfile.ZipFile(z_tmp) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out_path = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdf_paths.append(out_path)
    z_tmp.unlink()  # elimina ZIP temporal
    return pdf_paths


def classify_folder(info: Dict[str, str]) -> Path:
    """Devuelve la carpeta de clasificación según el NIVEL."""
    nivel = (info.get("NIVEL", "OTROS").upper().replace(" ", "_"))
    target = OUTPUT_DIR / nivel
    target.mkdir(exist_ok=True)
    return target


# ───────────────────── Rutas ─────────────────────────────
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
    all_pdfs: List[Path] = []

    # 1) Guardar archivos y extraer ZIPs
    for f in uploads:
        if not allowed_file(f.filename):
            flash(f"Tipo de archivo no permitido: {f.filename}", "danger")
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix == ".zip":
            all_pdfs.extend(save_and_extract_zip(f, tmpdir))
        else:  # .pdf
            pdf_path = tmpdir / secure_filename(f.filename)
            f.save(pdf_path)
            all_pdfs.append(pdf_path)

    # 2) Procesar cada PDF
    rows: List[Dict[str, str]] = []
    for pdf in all_pdfs:
        try:
            text = ocr_pdf(pdf)
            info = extract_certificate(text)
        except Exception as e:
            flash(f"Error procesando {pdf.name}: {e}", "danger")
            continue

        # Renombrar y mover
        nuevo_nombre = (
            f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
        )
        destino = classify_folder(info) / nuevo_nombre
        shutil.copy2(pdf, destino)

        info["ARCHIVO"] = nuevo_nombre
        rows.append(info)

    # TODO: generar_excel(rows)   --> si tu proyecto lo hace
    # TODO: crear_zip_salida()    --> idem

    # Limpiar temporales
    shutil.rmtree(tmpdir, ignore_errors=True)

    return render_template("resultado.html", rows=rows)


@app.get("/download/<path:fname>")
def download(fname: str):
    """Permite descargar un archivo desde la carpeta salida."""
    path = OUTPUT_DIR / fname
    if not path.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(path.parent, path.name, as_attachment=True)


# ───────────────────── Main local ────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
