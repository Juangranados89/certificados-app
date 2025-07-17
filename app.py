"""
app.py  –  Flask entry-point
============================

• Subida de PDF o ZIP (máx. 10 archivos – 25 MB).
• Selector de tipo de certificado:  auto | alturas | confinados | izajes.
• OCR con utils.ocr_pdf()  →  extracción con utils.extract_certificate().
• Renombra a  NOMBRE_CC.pdf  y lo coloca en /salida/<NIVEL>/.
• Tabla de resultados con estado OK / FALLÓ.
• Descarga individual (/download/<fname>).
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

from utils import ocr_pdf, extract_certificate

# ─── Configuración ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10
MAX_CONTENT_MB = 25

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024  # 25 MB


# ─── Helpers ───────────────────────────────────────────────
def allowed_file(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED_EXT


def save_and_extract_zip(fs, dest: Path) -> List[Path]:
    """Guarda el ZIP y devuelve rutas de los PDF que contiene."""
    z_tmp = dest / secure_filename(fs.filename)
    fs.save(z_tmp)

    pdf_paths: list[Path] = []
    with zipfile.ZipFile(z_tmp) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdf_paths.append(out)
    z_tmp.unlink(missing_ok=True)
    return pdf_paths


def classify_folder(info: Dict[str, str]) -> Path:
    """Devuelve carpeta destino basada en el NIVEL."""
    nivel = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    folder = OUTPUT_DIR / nivel
    folder.mkdir(exist_ok=True)
    return folder


# ─── Rutas ─────────────────────────────────────────────────
@app.get("/")
def index():
    """Formulario de subida (con pestañas)."""
    return render_template("index.html")


@app.post("/start")
def start() -> str:
    """Procesa los archivos subidos y muestra la tabla final."""
    tipo = request.form.get("tipo_cert", "auto")  # auto | alturas | confinados | izajes
    uploads = request.files.getlist("files")

    if not uploads:
        flash("No se seleccionó ningún archivo", "warning")
        return redirect(url_for("index"))

    if len(uploads) > MAX_UPLOADS:
        flash(f"Máximo {MAX_UPLOADS} archivos por lote", "danger")
        return redirect(url_for("index"))

    tmpdir = Path(tempfile.mkdtemp())
    pdf_files: list[Path] = []

    # 1) Guardar PDF sueltos o descomprimir ZIP
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

    # 2) OCR + extracción + renombrado
    rows: list[Dict[str, str]] = []
    for pdf in pdf_files:
        info: Dict[str, str] = {"ORIG": pdf.name}  # nombre original siempre
        try:
            text = ocr_pdf(pdf)
            extra = extract_certificate(text, mode=tipo)
            if not extra:
                raise ValueError("Patrón no reconocido")
            info.update(extra)
            info["ESTADO"] = "OK"
        except Exception as err:
            # Registro fallido
            info.update(
                {
                    "NOMBRE": "",
                    "CC": "",
                    "CURSO": "",
                    "NIVEL": "",
                    "FECHA_EXP": "",
                    "FECHA_VEN": "",
                    "ESTADO": f"FALLÓ: {err}",
                }
            )

        # Si extracción fue correcta, se renombra y clasifica
        if info["ESTADO"] == "OK":
            new_name = (
                f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
            )
            shutil.copy2(pdf, classify_folder(info) / new_name)
            info["ARCHIVO"] = new_name
        else:
            info["ARCHIVO"] = pdf.name  # deja original

        rows.append(info)

    # 3) Limpieza de temporales
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 4) Tabla de resultados
    return render_template("resultado.html", rows=rows)


@app.get("/download/<path:fname>")
def download(fname: str):
    """Descarga individual del PDF renombrado."""
    fp = OUTPUT_DIR / fname
    if not fp.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fp.parent, fp.name, as_attachment=True)


# ─── Ejecución local ───────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
