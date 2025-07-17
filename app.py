"""
app.py  –  Flask entry-point con selector de tipo.
"""

from __future__ import annotations
import os, shutil, tempfile, zipfile
from pathlib import Path
from typing import Dict, List

from flask import (
    Flask, render_template, request, redirect, url_for, flash, send_from_directory
)
from werkzeug.utils import secure_filename

from utils import ocr_pdf, extract_certificate

BASE_DIR    = Path(__file__).resolve().parent
OUTPUT_DIR  = BASE_DIR / "salida"; OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".pdf", ".zip"}
MAX_UPLOADS = 10
MAX_MB      = 25

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

def allowed(fn:str)->bool: return Path(fn).suffix.lower() in ALLOWED_EXT

def unzip(fs, dest:Path)->List[Path]:
    ztmp = dest/secure_filename(fs.filename); fs.save(ztmp)
    pdfs=[]
    with zipfile.ZipFile(ztmp) as zf:
        for m in zf.namelist():
            if Path(m).suffix.lower()==".pdf":
                out = dest/secure_filename(Path(m).name)
                with zf.open(m) as src, open(out,"wb") as dst: shutil.copyfileobj(src,dst)
                pdfs.append(out)
    ztmp.unlink(missing_ok=True); return pdfs

def folder(info:Dict[str,str])->Path:
    p = OUTPUT_DIR / info.get("NIVEL","OTROS").upper().replace(" ","_")
    p.mkdir(exist_ok=True); return p

@app.get("/")
def index(): return render_template("index.html")

@app.post("/start")
def start():
    tipo = request.form.get("tipo_cert","auto")        # ← pestaña elegida
    up   = request.files.getlist("files")
    if not up: flash("Sin archivos", "warning"); return redirect(url_for("index"))
    if len(up)>MAX_UPLOADS: flash("Demasiados archivos","danger"); return redirect(url_for("index"))

    tmp   = Path(tempfile.mkdtemp())
    pdfs: list[Path] = []
    for fs in up:
        if not allowed(fs.filename):
            flash(f"No permitido: {fs.filename}", "danger"); continue
        pdfs.extend(unzip(fs,tmp) if fs.filename.lower().endswith(".zip") else
                    [tmp/secure_filename(fs.filename)])
        if pdfs[-1].suffix.lower()==".pdf": fs.save(pdfs[-1])

    rows=[]
    for p in pdfs:
        try:
            txt  = ocr_pdf(p)
            info = extract_certificate(txt, mode=tipo)
            info["ESTADO"]="OK"
        except Exception as e:
            info = {"NOMBRE":"", "CC":"", "CURSO":"", "NIVEL":"", "FECHA_EXP":"",
                    "FECHA_VEN":"", "ESTADO":str(e)}
        info["ORIG"]    = p.name
        new_name        = f"{info['NOMBRE'].replace(' ','_')}_{info['CC']}.pdf".upper()
        if info["ESTADO"]=="OK":
            shutil.copy2(p, folder(info)/new_name)
        info["ARCHIVO"] = new_name
        rows.append(info)

    shutil.rmtree(tmp,ignore_errors=True)
    return render_template("resultado.html", rows=rows)

@app.get("/download/<path:fname>")
def download(fname:str):
    fp=OUTPUT_DIR/fname
    if not fp.exists(): flash("Archivo no encontrado","danger"); return redirect(url_for("index"))
    return send_from_directory(fp.parent, fp.name, as_attachment=True)

if __name__=="__main__": app.run(debug=True)
