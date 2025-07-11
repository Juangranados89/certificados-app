from flask import (Flask, render_template, request, redirect, url_for,
                   send_file, flash, abort)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, zipfile
from utils import parse_pdf, process_pdfs, _copiar_renombrar

app = Flask(__name__)
app.secret_key = "super-secret-key"

ALLOWED_PDF  = {'.pdf'}
ALLOWED_ZIP  = {'.zip'}
OUTPUT_ROOT  = "/tmp/certificados_out"
os.makedirs(OUTPUT_ROOT, exist_ok=True)


def _ext_ok(fname, allowed): return os.path.splitext(fname)[1].lower() in allowed


# -------------------------------------------------------------------- #
# Home (botones)                                                       #
# -------------------------------------------------------------------- #
@app.route("/")
def home():
    return render_template("index.html")


# -------------------------------------------------------------------- #
# 1. Un solo PDF                                                       #
# -------------------------------------------------------------------- #
@app.route("/single", methods=["POST"])
def single():
    f = request.files.get("pdf")
    if not f or not _ext_ok(f.filename, ALLOWED_PDF):
        flash("Adjunta un PDF válido"); return redirect(url_for("home"))

    tmp = tempfile.mkdtemp()
    in_path = os.path.join(tmp, f.filename); f.save(in_path)

    batch = uuid.uuid4().hex[:8]
    outdir = os.path.join(OUTPUT_ROOT, batch)
    os.makedirs(outdir, exist_ok=True)

    campos, _ = parse_pdf(in_path)
    rel = _copiar_renombrar(in_path, outdir, campos)
    zip_path = _zip_dir(outdir)

    rows = [{
        "orig": f.filename,
        "new": os.path.basename(rel),
        "rel": rel
    }]

    shutil.rmtree(tmp)
    return render_template("progreso.html", rows=rows,
                           zip_url=url_for("download_zip", batch=batch))


# -------------------------------------------------------------------- #
# 2. Múltiples PDF (máx 10)                                            #
# -------------------------------------------------------------------- #
@app.route("/multi", methods=["POST"])
def multi():
    files = request.files.getlist("pdfs")
    if not files or len(files) == 0 or len(files) > 10:
        flash("Adjunta entre 1 y 10 PDFs"); return redirect(url_for("home"))

    tmp = tempfile.mkdtemp()
    paths = []
    for f in files:
        if _ext_ok(f.filename, ALLOWED_PDF):
            p = os.path.join(tmp, f.filename); f.save(p); paths.append(p)

    batch = uuid.uuid4().hex[:8]
    outdir = os.path.join(OUTPUT_ROOT, batch)

    df, _ = process_pdfs(paths, outdir)
    zip_path = _zip_dir(outdir)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "orig": r["ARCHIVO"].split("/")[-1].split("_", 1)[-1],
            "new" : os.path.basename(r["ARCHIVO"]),
            "rel" : r["ARCHIVO"]
        })

    shutil.rmtree(tmp)
    return render_template("progreso.html", rows=rows,
                           zip_url=url_for("download_zip", batch=batch))


# -------------------------------------------------------------------- #
# 3. ZIP con muchos PDF                                                #
# -------------------------------------------------------------------- #
@app.route("/zipbatch", methods=["POST"])
def zipbatch():
    zf = request.files.get("zipfile")
    if not zf or not _ext_ok(zf.filename, ALLOWED_ZIP):
        flash("Adjunta un ZIP válido"); return redirect(url_for("home"))

    tmp_ext = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_ext, zf.filename); zf.save(zip_path)

    extract_dir = os.path.join(tmp_ext, "unzipped")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as inzip:
        inzip.extractall(extract_dir)

    # Recorre PDFs encontrados
    pdf_paths = []
    for root, _, files in os.walk(extract_dir):
        for fn in files:
            if _ext_ok(fn, ALLOWED_PDF):
                pdf_paths.append(os.path.join(root, fn))

    if not pdf_paths:
        flash("El ZIP no contenía PDFs"); return redirect(url_for("home"))

    batch = uuid.uuid4().hex[:8]
    outdir = os.path.join(OUTPUT_ROOT, batch)
    df, _ = process_pdfs(pdf_paths, outdir)
    _zip_dir(outdir)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "orig": r["ARCHIVO"].split("/")[-1].split("_", 1)[-1],
            "new" : os.path.basename(r["ARCHIVO"]),
            "rel" : r["ARCHIVO"]
        })

    shutil.rmtree(tmp_ext)
    return render_template("progreso.html", rows=rows,
                           zip_url=url_for("download_zip", batch=batch))


# -------------------------------------------------------------------- #
# Utilidades download                                                  #
# -------------------------------------------------------------------- #
def _zip_dir(directory):
    """Zip recursivamente un directorio y devuelve la ruta del zip creado"""
    zip_path = os.path.join(directory, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    z.write(abs_f, arcname=os.path.relpath(abs_f, directory))
    return zip_path


@app.route("/download/<path:relpath>")
def download_file(relpath):
    abs_path = safe_join(OUTPUT_ROOT, relpath)
    return send_file(abs_path, as_attachment=True) if abs_path and os.path.exists(abs_path) else abort(404)


@app.route("/zip/<batch>")
def download_zip(batch):
    zp = safe_join(OUTPUT_ROOT, batch, "certificados_organizados.zip")
    return send_file(zp, as_attachment=True, download_name="certificados_organizados.zip") if zp and os.path.exists(zp) else abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
