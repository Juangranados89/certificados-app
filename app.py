from flask import (Flask, render_template, request, redirect, url_for,
                   send_file, flash, abort)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid
from utils import parse_pdf, process_pdfs, _copiar_renombrar

app = Flask(__name__)
app.secret_key = "super-secret-key"
ALLOWED_EXT = {".pdf"}

OUTPUT_DIR = "/tmp/certs_out"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _allowed(fn): return os.path.splitext(fn)[1].lower() in ALLOWED_EXT


# ------------------ INICIO ------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ------------------ LOTE ------------------
@app.route("/lote", methods=["POST"])
def lote():
    files = request.files.getlist("pdfs")
    if not files:
        flash("Adjunta al menos un PDF", "error"); return redirect(url_for("index"))

    tmpin = tempfile.mkdtemp()
    in_paths = []
    for f in files:
        if _allowed(f.filename):
            p = os.path.join(tmpin, f.filename)
            f.save(p); in_paths.append(p)

    # Procesar
    batch_id = uuid.uuid4().hex[:8]
    outdir = os.path.join(OUTPUT_DIR, batch_id)
    registros_df, zip_path = process_pdfs(in_paths, outdir)

    # Armar filas para la tabla
    rows = []
    for _, r in registros_df.iterrows():
        rows.append({
            "orig": r["ARCHIVO"].split("/")[-1].split("_", 1)[-1] if "ARCHIVO" in r else "—",
            "new":  os.path.basename(r["ARCHIVO"]),
            "progress": 100,
            "rel":  r["ARCHIVO"]
        })

    zip_url = url_for("download_zip", batch=batch_id)

    shutil.rmtree(tmpin)
    return render_template("progreso.html", rows=rows, zip_url=zip_url)


# ------------------ DESCARGAR INDIVIDUAL ------------------
@app.route("/download/<path:relpath>")
def download_file(relpath):
    abs_path = safe_join(OUTPUT_DIR, relpath)
    if abs_path and os.path.exists(abs_path):
        return send_file(abs_path, as_attachment=True)
    abort(404)


# ------------------ DESCARGAR ZIP GENERAL ------------------
@app.route("/zip/<batch>")
def download_zip(batch):
    zip_path = safe_join(OUTPUT_DIR, batch, "certificados_organizados.zip")
    if zip_path and os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True,
                         download_name="certificados_organizados.zip")
    abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
