from flask import Flask, render_template, request, redirect, url_for, \
                  jsonify, send_file, abort
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, threading, zipfile, pandas as pd
from utils import parse_file, _copiar_renombrar, save_image_as_pdf_renamed

app = Flask(__name__)
app.secret_key = "secret-key"

ALLOWED_PDF = {'.pdf'}
ALLOWED_IMG = {'.jpg', '.jpeg', '.png'}
ALLOWED_ZIP = {'.zip'}

DATA_DIR = "/tmp/cert_jobs"
os.makedirs(DATA_DIR, exist_ok=True)
jobs = {}   # job_id -> dict

def _ext(fname, allowed): return os.path.splitext(fname)[1].lower() in allowed

def _zip_dir(d):
    zp=os.path.join(d,"certificados_organizados.zip")
    with zipfile.ZipFile(zp,"w") as z:
        for root,_,fs in os.walk(d):
            for f in fs:
                if f.lower().endswith(".pdf"):
                    z.write(os.path.join(root,f),arcname=os.path.relpath(os.path.join(root,f),d))
    return zp

def _worker(job,paths):
    out=os.path.join(DATA_DIR,job);os.makedirs(out,exist_ok=True)
    for i,p in enumerate(paths):
        ext=os.path.splitext(p)[1].lower()
        campos,_,src=parse_file(p)
        if ext in ALLOWED_IMG:
            rel=save_image_as_pdf_renamed(src,out,campos)
        else:
            rel=_copiar_renombrar(src,out,campos)

        row=jobs[job]["rows"][i]
        row.update({
            "new":os.path.basename(rel),
            "cargo":campos.get("NIVEL") or campos.get("CERTIFICADO"),
            "fexp":campos.get("FECHA_EXP",""),
            "fven":campos.get("FECHA_VEN",""),
            "rel":rel,"progress":100
        })

    # Excel
    df=pd.DataFrame(jobs[job]["rows"])
    xlsx=os.path.join(out,"listado.xlsx"); df.to_excel(xlsx,index=False)
    jobs[job]["zip"]=_zip_dir(out)
    jobs[job]["excel"]=xlsx
    jobs[job]["done"]=True

@app.route("/")
def home(): return render_template("index.html")

@app.route("/start",methods=["POST"])
def start():
    files=request.files.getlist("files")
    if not files: return redirect(url_for("home"))
    tmp=tempfile.mkdtemp(); paths=[]
    for f in files:
        ext=os.path.splitext(f.filename)[1].lower()
        if ext in ALLOWED_PDF|ALLOWED_IMG:
            p=os.path.join(tmp,f.filename);f.save(p);paths.append(p)
        elif ext in ALLOWED_ZIP:
            zp=os.path.join(tmp,f.filename);f.save(zp)
            with zipfile.ZipFile(zp) as z:z.extractall(tmp)
            for r,_,fs in os.walk(tmp):
                for fn in fs:
                    if _ext(fn,ALLOWED_PDF|ALLOWED_IMG):
                        paths.append(os.path.join(r,fn))
    if not paths:return "Sin archivos válidos",400
    job=uuid.uuid4().hex[:8]
    jobs[job]={"rows":[{"orig":os.path.basename(p),"new":"","cargo":"","fexp":"","fven":"","progress":0,"rel":""} for p in paths],
               "zip":None,"excel":None,"done":False}
    threading.Thread(target=_worker,args=(job,paths),daemon=True).start()
    return redirect(url_for("progress_page",job=job))

@app.route("/progress/<job>"); 
def progress_page(job): return render_template("progreso.html",job=job) if job in jobs else abort(404)

@app.route("/status/<job>");       def status(job):      return jsonify(jobs.get(job) or abort(404))
@app.route("/download/<job>/<path:rel>");  
def dl(job,rel): return send_file(safe_join(DATA_DIR,job,rel),as_attachment=True) if job in jobs else abort(404)
@app.route("/zip/<job>");          def zip_dl(job): return send_file(jobs[job]["zip"],as_attachment=True) if job in jobs else abort(404)
@app.route("/excel/<job>");        def xls(job):   return send_file(jobs[job]["excel"],as_attachment=True,download_name="listado.xlsx") if job in jobs else abort(404)

if __name__=="__main__":
    port=int(os.environ.get("PORT",8000))
    app.run(host="0.0.0.0",port=port,debug=True)
