"""app.py – Flask entry-point con selector de tipo."""

from __future__ import annotations
import os, shutil, tempfile, zipfile
from pathlib import Path
from typing import Dict, List

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, send_from_directory)
from werkzeug.utils import secure_filename

from utils import ocr_pdf, extract_certificate

# Config
BASE_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"; OUTPUT_DIR.mkdir(exist_ok=True)
ALLOWED_EXT={".pdf",".zip"}; MAX_UPLOADS=10; MAX_MB=25

app=Flask(__name__)
app.secret_key=os.getenv("SECRET_KEY","dev-secret")
app.config["MAX_CONTENT_LENGTH"]=MAX_MB*1024*1024

def allowed(fn:str)->bool: return Path(fn).suffix.lower() in ALLOWED_EXT

def unzip(fs,dest:Path)->List[Path]:
    z=dest/secure_filename(fs.filename); fs.save(z)
    pdfs=[];    with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():
            if Path(m).suffix.lower()==".pdf":
                out=dest/secure_filename(Path(m).name)
                with zf.open(m) as s, open(out,"wb") as d: shutil.copyfileobj(s,d)
                pdfs.append(out)
    z.unlink(); return pdfs

def folder(info:Dict[str,str])->Path:
    p=OUTPUT_DIR/info.get("NIVEL","OTROS").upper().replace(" ","_")
    p.mkdir(exist_ok=True); return p

@app.get("/")
def index(): return render_template("index.html")

@app.post("/start")
def start():
    tipo=request.form.get("tipo_cert","auto")
    up=request.files.getlist("files")
    if not up: flash("Sin archivos","warning"); return redirect(url_for("index"))
    if len(up)>MAX_UPLOADS: flash("Límite excedido","danger"); return redirect(url_for("index"))

    tmp=Path(tempfile.mkdtemp()); pdfs=[]
    for fs in up:
        if not allowed(fs.filename):
            flash(f"No permitido: {fs.filename}","danger"); continue
        if fs.filename.lower().endswith(".zip"):
            pdfs.extend(unzip(fs,tmp))
        else:
            dst=tmp/secure_filename(fs.filename); fs.save(dst); pdfs.append(dst)

    rows=[]
    for p in pdfs:
        info={"ORIG":p.name}
        try:
            text=ocr_pdf(p)
            extra=extract_certificate(text,mode=tipo)
            if not extra: raise ValueError("Patrón no reconocido")
            info.update(extra); info["ESTADO"]="OK"
        except Exception as e:
            info.update({"NOMBRE":"","CC":"","CURSO":"","NIVEL":"",
                         "FECHA_EXP":"","FECHA_VEN":"",
                         "ESTADO":f"FALLÓ: {e}"})

        if info["ESTADO"]=="OK":
            new=f"{info['NOMBRE'].replace(' ','_')}_{info['CC']}.pdf".upper()
            shutil.copy2(p, folder(info)/new); info["ARCHIVO"]=new
        else:
            info["ARCHIVO"]=p.name
        rows.append(info)

    shutil.rmtree(tmp,ignore_errors=True)
    return render_template("resultado.html", rows=rows)

@app.get("/download/<path:fname>")
def download(fname:str):
    fp=OUTPUT_DIR/fname
    if not fp.exists(): flash("Archivo no encontrado","danger"); return redirect(url_for("index"))
    return send_from_directory(fp.parent, fp.name, as_attachment=True)

if __name__=="__main__":
    app.run(debug=True)
