"""
app.py – Flask backend
• Procesa PDF, JPG/PNG o ZIP (mixto)
• Selector de tipo (auto / alturas / confinados / izajes)
• Trabajo en segundo plano con SSE (barra/progreso)
• Convierte imágenes a PDF real (img2pdf)
• Genera ZIP por nivel y Excel global
"""

from __future__ import annotations
import os, shutil, tempfile, zipfile, uuid, threading, time, json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import img2pdf
from flask import (
    Flask, flash, redirect, render_template, request, url_for,
    Response, send_from_directory
)
from werkzeug.utils import secure_filename

from utils import ocr_pdf, ocr_img, extract_certificate

# ─── Config ──────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
OUT_DIR   = BASE_DIR / "salida"; OUT_DIR.mkdir(exist_ok=True)
ALLOWED   = {".pdf", ".zip", ".jpg", ".jpeg", ".png"}
MAX_FILES = 10
MAX_MB    = 25

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024  # 25 MB

# ─── Almacén de tareas en memoria ────────────────────────
JOBS: dict[str, dict] = {}  # job_id → {total, done, pct, msg, rows, finished}

# ─── Helpers ─────────────────────────────────────────────
def allowed(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED


def unzip(fs, dest: Path) -> List[Path]:
    """Extrae los archivos válidos de un ZIP y devuelve sus rutas."""
    z_tmp = dest / secure_filename(fs.filename)
    fs.save(z_tmp)

    outs: list[Path] = []
    with zipfile.ZipFile(z_tmp) as zf:
        for m in zf.namelist():
            if Path(m).suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"):
                out = dest / secure_filename(Path(m).name)
                with zf.open(m) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                outs.append(out)
    z_tmp.unlink(missing_ok=True)
    return outs


def folder_for(info: Dict[str, str]) -> Path:
    lvl = info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    p = OUT_DIR / lvl
    p.mkdir(exist_ok=True)
    return p


def write_zip(rows: List[Dict[str, str]]) -> None:
    with zipfile.ZipFile(OUT_DIR / "certificados_clasificados.zip", "w") as zf:
        for r in rows:
            if r["ESTADO"] == "OK":
                zf.write(OUT_DIR / r["ARCHIVO"], arcname=r["ARCHIVO"])


def write_excel(rows: List[Dict[str, str]]) -> None:
    pd.DataFrame(rows).to_excel(OUT_DIR / "certificados.xlsx", index=False)

# ─── Worker de fondo ─────────────────────────────────────
def process_job(jid: str, paths: List[Path], modo: str) -> None:
    job = JOBS[jid]
    total = len(paths)
    job.update(pct=5, msg="Leyendo archivos…")

    rows: list[Dict[str, str]] = []
    step = 60 / total if total else 0  # 0-60 % durante OCR/parseo

    for idx, p in enumerate(paths, 1):
        try:
            text = ocr_img(p) if p.suffix.lower() in (".jpg", ".jpeg", ".png") else ocr_pdf(p)
            job.update(pct=5 + idx * step * 0.5, msg=f"OCR {idx}/{total}")

            extra = extract_certificate(text, mode=modo)
            if not extra:
                raise ValueError("Patrón no reconocido")
            info = {"ORIG": p.name, **extra, "ESTADO": "OK"}
        except Exception as err:
            info = {"ORIG": p.name, "NOMBRE": "", "CC": "", "CURSO": "",
                    "NIVEL": "", "FECHA_EXP": "", "FECHA_VEN": "",
                    "ESTADO": f"FALLÓ: {err}"}

        if info["ESTADO"] == "OK":
            new = f"{info['NOMBRE'].replace(' ', '_')}_{info['CC']}.pdf".upper()
            target = folder_for(info) / new
            if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                with open(target, "wb") as f:
                    f.write(img2pdf.convert(str(p)))
            else:
                shutil.copy2(p, target)
            info["ARCHIVO"] = str(target.relative_to(OUT_DIR))
        else:
            info["ARCHIVO"] = ""

        rows.append(info)
        job.update(done=idx, pct=5 + idx * step)

    job.update(pct=80, msg="Generando ZIP y Excel…")
    write_zip(rows)
    write_excel(rows)

    job.update(pct=100, msg="Completo", rows=rows, finished=True)

# ─── Rutas ───────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/start")
def start():
    modo = request.form.get("tipo_cert", "auto")
    uploads = request.files.getlist("files")

    if not uploads:
        flash("Sin archivos seleccionados", "warning")
        return redirect(url_for("index"))
    if len(uploads) > MAX_FILES:
        flash(f"Máximo {MAX_FILES} archivos", "danger")
        return redirect(url_for("index"))

    tmp = Path(tempfile.mkdtemp())
    paths: list[Path] = []

    for fs in uploads:
        if not allowed(fs.filename):
            flash(f"Tipo no permitido: {fs.filename}", "danger")
            continue
        if fs.filename.lower().endswith(".zip"):
            paths.extend(unzip(fs, tmp))
        else:
            dst = tmp / secure_filename(fs.filename)
            fs.save(dst)
            paths.append(dst)

    jid = uuid.uuid4().hex
    JOBS[jid] = {"total": len(paths), "done": 
