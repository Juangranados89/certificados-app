"""
app.py – Flask app
• Selector de tipo (alturas | confinados | izajes | auto)
• ZIP global con subcarpetas por NIVEL
• Excel de los datos extraídos
• Descarga individual correcta
"""

from __future__ import annotations
import os, shutil, tempfile, zipfile
from pathlib import Path
from typing import Dict, List

import pandas as pd
from flask import (Flask, flash, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename
from utils import ocr_pdf, extract_certificate

# ─── Config ──────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"; OUTPUT_DIR.mkdir(exist_ok=True)
ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10
MAX_MB      = 25

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


# ─── Helpers ─────────────────────────────────────────────
def allowed(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED_EXT


def unzip(fs, dest: Path) -> List[Path]:
    """Guarda ZIP y devuelve Paths de los PDF extraídos."""
    z_tmp = dest / secure_filename(fs.filename)
    fs.save(z_tmp)

    pdfs: list[Path] = []
    with zipfile.ZipFile(z_tmp) as zf:
        for member in zf.namelist():
            if Path(member).suffix.lower() == ".pdf":
                out = dest / secure_filename(Path(member).name)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pdfs.append(out)
    z_tmp.unlink(missing_ok=True)
    return pdfs


def folder_for(info: Dict[str, str]) -> Path:
    lvl = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    p = OUTPUT_DIR / lvl
    p.mkdir(exist_ok=True)
    return p


def make_global_zip(rows: List[Dict[str, str]]) -> Path:
    zpath = OUTPUT_DIR / "certificados_clasificados.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for r in rows:
            if r["ESTADO"] != "OK":
                continue
            zf.write(OUTPUT_DIR / r["ARCHIVO"], arcname=r["ARCHIVO"])
    return zpath


def make_excel(rows: List[Dict[str, str]]) -> Path:
    xls = OUTPUT_DIR / "certificados.xlsx"
    pd.DataFrame(rows).to_excel(xls, index=False)
    return xls


# ─── Rutas ───────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/start")
def start():
    modo = request.form.get("tipo_cert", "auto")
    uploads = request.files.getlist("files")

    if not uploads:
        flash("No se seleccionó ningún archivo", "warning")
        return redirect(url_for("index"))
    if len(uploads) > MAX_UPLOADS:
        flash(f"Máximo {MAX_UPLOADS} archivos por lote", "danger")
        return redirect(url_for("index"))

    tmp = Path(tempfile.mkdtemp())
    pdf_files: list[Path] = []

    # 1) Guardar y/o descomprimir
    for fs in uploads:
        if not allowed(fs.filename):
            flash(f"Tipo no permitido: {fs.filename}", "danger")
            continue
        if fs.filename.lower().endswith(".zip"):
            pdf_files.extend(unzip(fs, tmp))
        else:
            dst = tmp / secure_filename(fs.filename)
            fs.save(dst)
            pdf_files.append(dst)

    # 2) Procesar
    rows: list[Dict[str, str]] = []
    for pdf in pdf_files:
        info = {"ORIG": pdf.name}
        try:
            txt = ocr_pdf(pdf)
            extra = extract_certificate(txt, mode=modo)
            if not extra:
                raise ValueError("Patrón no reconocido")
            info.update(extra)
            info["ESTADO"] = "OK"
        except Exception as e:
            info.update(
                {
                    "NOMBRE": "",
                    "CC": "",
                    "CURSO": "",
                    "NIVEL": "",
                    "FECHA_EXP": "",
                    "FECHA_VEN": "",
                    "ESTADO": f"FALLÓ: {e}",
                }
            )

        # Renombrar si es OK
        if info["ESTADO"] == "OK":
            new_name = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
            target = folder_for(info) / new_name
            shutil.copy2(pdf, target)
            info["ARCHIVO"] = str(target.relative_to(OUTPUT_DIR))
        else:
            info["ARCHIVO"] = ""

        rows.append(info)

    # 3) ZIP y Excel
    make_global_zip(rows)
    make_excel(rows)

    shutil.rmtree(tmp, ignore_errors=True)
    return render_template("resultado.html", rows=rows)


@app.get("/download/file/<path:relpath>")
def download_file(relpath: str):
    fp = OUTPUT_DIR / relpath
    if not fp.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fp.parent, fp.name, as_attachment=True)


@app.get("/download/zip")
def download_zip():
    return send_from_directory(OUTPUT_DIR, "certificados_clasificados.zip", as_attachment=True)


@app.get("/download/excel")
def download_excel():
    return send_from_directory(OUTPUT_DIR, "certificados.xlsx", as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
