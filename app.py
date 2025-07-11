from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, abort
)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, threading, zipfile, pandas as pd

#  ⬇️  IMPORTS CORRECTOS desde utils.py
from utils import (
    parse_file,
    _copiar_renombrar,
    save_image_as_pdf_renamed      # ← nombre exacto
)

app = Flask(__name__)
app.secret_key = "super-secret-key"

ALLOWED_PDF = {".pdf"}
ALLOWED_IMG = {".jpg", ".jpeg", ".png"}
ALLOWED_ZIP = {".zip"}

DATA_DIR = "/tmp/cert_jobs"
os.makedirs(DATA_DIR, exist_ok=True)

# memoria en RAM: job_id → info del trabajo
jobs: dict[str, dict] = {}

# ────────────────────── helpers ──────────────────────
def _ext_ok(name: str, exts) -> bool:
    return os.path.splitext(name)[1].lower() in exts

def _zip_dir(directory: str) -> str:
    """Empaqueta todos los PDFs"""
    zp = os.path.join(directory, "certificados_organizados.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for root, _, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    z.write(abs_f, arcname=os.path.relpath(abs_f, directory))
    return zp

# ────────────────────── worker ──────────────────────
def _worker(job: str, paths: list[str]):
    outdir = os.path.join(DATA_DIR, job)
    os.makedirs(outdir, exist_ok=True)

    for idx, src in enumerate(paths):
        ext = os.path.splitext(src)[1].lower()
        campos, _, src_path = parse_file(src)

        # PDF final
        if ext in ALLOWED_IMG:
            rel = save_image_as_pdf_renamed(src_path, outdir, campos)
        else:
            rel = _copiar_renombrar(src_path, outdir, campos)

        jobs[job]["rows"][idx].update({
            "new": os.path.basename(rel),
            "cargo": campos.get("NIVEL") or campos.get("CERTIFICADO"),
            "fexp": campos.get("FECHA_EXP", ""),
            "fven": campos.get("FECHA_VEN", ""),
            "cc": campos.get("CC", ""),
            "nombre": campos.get("NOMBRE", ""),
            "rel": rel,
            "progress": 100
        })

    # Excel CC | NOMBRE | CARGO | FEXP | FVEN
    df = pd.DataFrame(
        [{
            "CC": r["cc"], "NOMBRE": r["nombre"], "CARGO": r["cargo"],
            "FEXP": r["fexp"], "FVEN": r["fven"]
        } for r in jobs[job]["rows"]],
        columns=["CC", "NOMBRE", "CARGO", "FEXP", "FVEN"]
    )
    excel_path = os.path.join(outdir, "listado.xlsx")
    df.to_excel(excel_path, index=False, engine="openpyxl")

    jobs[job]["zip"]   = _zip_dir(outdir)
    jobs[job]["excel"] = excel_path
    jobs[job]["done"]  = True

# ────────────────────── rutas Flask ──────────────────────
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    files = request.files.getlist("files")
    if not files:
        return redirect(url_for("home"))

    tmpdir = tempfile.mkdtemp()
    paths: list[str] = []

    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in (ALLOWED_PDF | ALLOWED_IMG):
            p = os.path.join(tmpdir, f.filename); f.save(p); paths.append(p)
        elif ext in ALLOWED_ZIP:
            zpath = os.path.join(tmpdir, f.filename); f.save(zpath)
            with zipfile.ZipFile(zpath) as zf: zf.extractall(tmpdir)
            for root, _, fns in os.walk(tmpdir):
                for fn in fns:
                    if _ext_ok(fn, ALLOWED_PDF | ALLOWED_IMG):
                        paths.append(os.path.join(root, fn))

    if not paths:
        shutil.rmtree(tmpdir)
        return "No se encontraron archivos válidos", 400

    job = uuid.uuid4().hex[:8]
    jobs[job] = {
        "rows": [{
            "orig": os.path.basename(p), "new": "", "cargo": "",
            "fexp": "", "fven": "", "cc": "", "nombre": "",
            "progress": 0, "rel": ""
        } for p in paths],
        "zip": None,
        "excel": None,
        "done": False
    }

    threading.Thread(target=_worker, args=(job, paths), daemon=True).start()
    return redirect(url_for("progress_page", job=job))

@app.route("/progress/<job>")
def progress_page(job):
    return render_template("progreso.html", job=job) if job in jobs else abort(404)

@app.route("/status/<job>")
def status(job):
    return jsonify(jobs.get(job) or abort(404))

@app.route("/download/<job>/<path:rel>")
def download_file(job, rel):
    abs_p = safe_join(DATA_DIR, job, rel)
    return send_file(abs_p, as_attachment=True) if abs_p and os.path.exists(abs_p) else abort(404)

@app.route("/zip/<job>")
def download_zip(job):
    zp = jobs.get(job, {}).get("zip")
    return send_file(zp, as_attachment=True, download_name="certificados_organizados.zip") if zp else abort(404)

@app.route("/excel/<job>")
def download_excel(job):
    xl = jobs.get(job, {}).get("excel")
    return send_file(xl, as_attachment=True, download_name="listado.xlsx") if xl else abort(404)

# ────────────────────── run ──────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
