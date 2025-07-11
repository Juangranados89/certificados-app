from flask import (
    Flask, render_template, request, redirect, url_for,
    send_file, flash, abort, safe_join
)
import os, tempfile, shutil
from tabulate import tabulate
from utils import parse_pdf, process_pdfs, _copiar_renombrar

app = Flask(__name__)
app.secret_key = "super-secret-key-change-me"

ALLOWED_EXT = {'.pdf'}
OUTPUT_DIR = "/tmp/certificados_renombrados"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _allowed(fn: str) -> bool:
    return os.path.splitext(fn)[1].lower() in ALLOWED_EXT


# ------------ 1 PDF ------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        pdf = request.files.get("pdf")
        if not pdf or not _allowed(pdf.filename):
            flash("Sube un PDF válido", "error")
            return redirect(request.url)

        tmpdir = tempfile.mkdtemp()
        inpath = os.path.join(tmpdir, pdf.filename)
        pdf.save(inpath)

        campos, _ = parse_pdf(inpath)
        rel_path = _copiar_renombrar(inpath, OUTPUT_DIR, campos)
        download_url = url_for("download_file", relpath=rel_path)

        shutil.rmtree(tmpdir)

        tabla_md = tabulate([campos.values()], headers=campos.keys(), tablefmt="github")
        return render_template("resultado.html",
                               tabla_markdown=tabla_md,
                               download_url=download_url)
    return render_template("index.html")


# ------------ varios PDFs ------------
@app.route("/lote", methods=["POST"])
def lote():
    pdfs = request.files.getlist("pdfs")
    if not pdfs:
        flash("Selecciona al menos un PDF", "error")
        return redirect(url_for("index"))

    tmpin = tempfile.mkdtemp()
    paths = []
    for f in pdfs:
        if _allowed(f.filename):
            p = os.path.join(tmpin, f.filename)
            f.save(p)
            paths.append(p)

    outdir = tempfile.mkdtemp()
    _, zip_path = process_pdfs(paths, outdir)
    shutil.rmtree(tmpin)

    return send_file(zip_path, as_attachment=True,
                     download_name="certificados_organizados.zip")


# ------------ descarga de PDF renombrado ------------
@app.route("/download/<path:relpath>")
def download_file(relpath):
    abs_path = safe_join(OUTPUT_DIR, relpath)
    if abs_path and os.path.exists(abs_path):
        return send_file(abs_path, as_attachment=True)
    abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
