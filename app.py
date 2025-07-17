"""
app.py – Flask con:
  • Selector de tipo (alturas / confinados / izajes / auto)
  • ZIP agrupado por NIVEL
  • Excel con filas de la tabla
  • Descarga individual que localiza el PDF dentro de la sub-carpeta
"""

from __future__ import annotations
import os, shutil, tempfile, zipfile, io
from pathlib import Path
from typing import Dict, List

import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, send_file)
from werkzeug.utils import secure_filename
from utils import ocr_pdf, extract_certificate

# ───── Config ───────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "salida"; OUTPUT_DIR.mkdir(exist_ok=True)
ALLOWED_EXT={".pdf",".zip"}; MAX_UPLOADS=10; MAX_MB=25

app=Flask(__name__)
app.secret_key=os.getenv("SECRET_KEY","dev-secret")
app.config["MAX_CONTENT_LENGTH"]=MAX_MB*1024*1024

# ───── Helpers ──────────────────────────────────────────
def allowed(fn:str)->bool: return Path(fn).suffix.lower() in ALLOWED_EXT

def unzip(fs, dest:Path)->List[Path]:
    z=dest/secure_filename(fs.filename); fs.save(z)
    pdfs=[];  with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():
            if Path(m).suffix.lower()==".pdf":
                out=dest/secure_filename(Path(m).name)
                with zf.open(m) as s, open(out,"wb") as d: shutil.copyfileobj(s,d)
                pdfs.append(out)
    z.unlink(); return pdfs

def folder_for(info:Dict[str,str])->Path:
    lvl = info.get("NIVEL","OTROS").upper().replace(" ","_")
    p = OUTPUT_DIR/lvl; p.mkdir(exist_ok=True); return p

def make_global_zip(rows:List[Dict[str,str]])->Path:
    zpath = OUTPUT_DIR / "certificados_clasificados.zip"
    with zipfile.ZipFile(zpath,"w") as zf:
        for r in rows:
            if r["ESTADO"]!="OK": continue
            lvl = r["NIVEL"].upper().replace(" ","_")
            p   = OUTPUT_DIR/lvl/r["ARCHIVO"]
            zf.write(p, arcname=f"{lvl}/{r['ARCHIVO']}")
    return zpath

def make_excel(rows:List[Dict[str,str]])->Path:
    xls = OUTPUT_DIR / "certificados.xlsx"
    pd.DataFrame(rows).to_excel(xls,index=False)
    return xls

# ───── Rutas ────────────────────────────────────────────
@app.get("/")
def index(): return render_template("index.html")

@app.post("/start")
def start():
    modo = request.form.get("tipo_cert","auto")
    files = request.files.getlist("files")
    if not files: flash("Sin archivos","warning"); return redirect(url_for("index"))
    if len(files)>MAX_UPLOADS: flash("Demasiados archivos","danger"); return redirect(url_for("index"))

    tmp = Path(tempfile.mkdtemp()); pdfs=[]
    for fs in files:
        if not allowed(fs.filename):
            flash(f"No permitido: {fs.filename}","danger"); continue
        pdfs += unzip(fs,tmp) if fs.filename.lower().endswith(".zip") else \
               [tmp/secure_filename(fs.filename)]
        if not fs.filename.lower().endswith(".zip"):
            pdfs[-1].write_bytes(fs.read())   # guarda el PDF suelto

    rows=[]
    for p in pdfs:
        info={"ORIG":p.name}
        try:
            txt  = ocr_pdf(p)
            extra= extract_certificate(txt, mode=modo)
            if not extra: raise ValueError("Patrón no reconocido")
            info.update(extra); info["ESTADO"]="OK"
        except Exception as e:
            info.update({k:"" for k in
                        ("NOMBRE","CC","CURSO","NIVEL","FECHA_EXP","FECHA_VEN")})
            info["ESTADO"]=f"FALLÓ: {e}"

        if info["ESTADO"]=="OK":
            new = f"{info['NOMBRE'].replace(' ','_')}_{info['CC']}.pdf".upper()
            level_folder = folder_for(info)
            shutil.copy2(p, level_folder/new)
            info["ARCHIVO"] = f"{level_folder.name}/{new}"   # ruta relativa
        else:
            info["ARCHIVO"] = ""

        rows.append(info)

    # Generar ZIP y Excel
    zip_path   = make_global_zip(rows)
    excel_path = make_excel(rows)

    shutil.rmtree(tmp,ignore_errors=True)
    return render_template("resultado.html", rows=rows,
                           zip_name=zip_path.name, xls_name=excel_path.name)

@app.get("/download/file/<path:relpath>")
def download_file(relpath:str):
    fp = OUTPUT_DIR/relpath
    if not fp.exists():
        flash("Archivo no encontrado","danger"); return redirect(url_for("index"))
    return send_file(fp, as_attachment=True)

@app.get("/download/zip")
def download_zip():
    return send_file(OUTPUT_DIR/"certificados_clasificados.zip", as_attachment=True)

@app.get("/download/excel")
def download_excel():
    return send_file(OUTPUT_DIR/"certificados.xlsx", as_attachment=True)

if __name__=="__main__":
    app.run(debug=True)
