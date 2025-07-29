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

# Configuración global
# Configuración global
BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "salida"
OUT_DIR.mkdir(exist_ok=True)
ALLOWED = {".pdf", ".zip", ".jpg", ".jpeg", ".png"}
MAX_UP = 10

# --- NUEVO: límite de subida configurable ---
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))      # hasta 100 MB por defecto
# ---------------------------------------------

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


# Almacén de jobs
JOBS: dict[str, dict] = {}

# Helpers
def allowed(fn: str) -> bool:
    return Path(fn).suffix.lower() in ALLOWED

def unzip(fs, dest: Path) -> List[Path]:
    ztmp = dest / secure_filename(fs.filename)
    fs.save(ztmp)
    outs = []
    with zipfile.ZipFile(ztmp) as zf:
        for m in zf.namelist():
            if Path(m).suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"):
                out = dest / secure_filename(Path(m).name)
                with zf.open(m) as s, open(out, "wb") as d:
                    shutil.copyfileobj(s, d)
                outs.append(out)
    ztmp.unlink()
    return outs

def folder_for(info: Dict[str, str]) -> Path:
    p = OUT_DIR / info.get("NIVEL", "OTROS").upper().replace(" ", "_")
    p.mkdir(exist_ok=True)
    return p

def write_zip(rows):
    with zipfile.ZipFile(OUT_DIR / "certificados_clasificados.zip", "w") as zf:
        for r in rows:
            if r["ESTADO"] == "OK":
                zf.write(OUT_DIR / r["ARCHIVO"], arcname=r["ARCHIVO"])

def write_excel(rows):
    pd.DataFrame(rows).to_excel(OUT_DIR / "certificados.xlsx", index=False)

# Worker
def process_job(jid: str, paths: List[Path], modo: str):
    job = JOBS[jid]
    total = len(paths)
    job.update(pct=5, msg="Leyendo archivos…")

    rows = []
    step = 60 / total if total else 0
    for idx, p in enumerate(paths, 1):
        try:
            txt = ocr_img(p) if p.suffix.lower() in (".jpg", ".jpeg", ".png") else ocr_pdf(p)
            job.update(pct=5 + idx * step * 0.5, msg=f"OCR {idx}/{total}")

            extra = extract_certificate(txt, mode=modo)
            if not extra:
                raise ValueError("Patrón no reconocido")
            info = {"ORIG": p.name, **extra, "ESTADO": "OK"}
        except Exception as e:
            info = {"ORIG": p.name, "NOMBRE": "", "CC": "", "CURSO": "",
                    "NIVEL": "", "FECHA_EXP": "", "FECHA_VEN": "",
                    "ESTADO": f"FALLÓ: {e}"}

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
        job["done"] = idx
        job["pct"] = 5 + idx * step

    job.update(pct=80, msg="Generando ZIP y Excel…")
    write_zip(rows)
    write_excel(rows)

    job.update(pct=100, msg="Completo", rows=rows, finished=True)

# Rutas
@app.get("/")
def index():
    return render_template("index.html")

@app.post("/start")
def start():
    modo = request.form.get("tipo_cert", "auto")
    ups = request.files.getlist("files")
    if not ups:
        flash("Sin archivos", "warning")
        return redirect(url_for("index"))
    if len(ups) > MAX_UP:
        flash("Demasiados archivos", "danger")
        return redirect(url_for("index"))
    tmp = Path(tempfile.mkdtemp())
    paths = []
    for fs in ups:
        if not allowed(fs.filename):
            flash(f"No permitido: {fs.filename}", "danger")
            continue
        if fs.filename.lower().endswith(".zip"):
            paths += unzip(fs, tmp)
        else:
            dst = tmp / secure_filename(fs.filename)
            fs.save(dst)
            paths.append(dst)

    jid = uuid.uuid4().hex
    JOBS[jid] = {"total": len(paths), "done": 0, "pct": 0, "msg": "Pendiente…", "rows": None, "finished": False}
    threading.Thread(target=process_job, args=(jid, paths, modo), daemon=True).start()
    return redirect(url_for("progreso", job_id=jid))

@app.get("/progress/<job_id>")
def progreso(job_id):
    if job_id not in JOBS:
        flash("Job inexistente", "danger")
        return redirect(url_for("index"))
    return render_template("progreso.html", jid=job_id)

@app.get("/events/<job_id>")
def events(job_id):
    def stream():
        while True:
            job = JOBS.get(job_id)
            time.sleep(0.3)
            if not job:
                break
            data = json.dumps({"pct": int(job["pct"]), "msg": job["msg"]})
            yield f"data:{data}\n\n"
            if job.get("finished"):
                break
    return Response(stream(), mimetype="text/event-stream")

@app.get("/resultado/<job_id>")
def resultado(job_id):
    job = JOBS.get(job_id)
    if not job or not job.get("finished") or not job.get("rows"):
        flash("Aún procesando", "warning")
        return redirect(url_for("progreso", job_id=job_id))
    return render_template("resultado.html", rows=job["rows"])

# Descargas
@app.get("/download/file/<path:rel>")
def download_file(rel):
    fp = OUT_DIR / rel
    if not fp.exists():
        flash("Archivo no encontrado", "danger")
        return redirect(url_for("index"))
    return send_from_directory(fp.parent, fp.name, as_attachment=True)

@app.get("/download/zip")
def download_zip():
    return send_from_directory(OUT_DIR, "certificados_clasificados.zip", as_attachment=True)

@app.get("/download/excel")
def download_excel():
    return send_from_directory(OUT_DIR, "certificados.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
