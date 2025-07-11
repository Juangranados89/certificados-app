from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, send_file, abort)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, threading, zipfile
from utils import parse_pdf, _copiar_renombrar

app = Flask(__name__)
app.secret_key = "secret-key"

ALLOWED_PDF = {'.pdf'}
ALLOWED_ZIP = {'.zip'}
DATA_DIR    = "/tmp/cert_jobs"
os.makedirs(DATA_DIR, exist_ok=True)

# ───── memoria de trabajos ───── #
jobs = {}  # job_id -> {rows, zip, done}


# ───── helpers ───── #
def _ext_ok(fname, allowed): return os.path.splitext(fname)[1].lower() in allowed


def _zip_dir(directory):
    zp = os.path.join(directory, "certificados_organizados.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for root, _, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    z.write(abs_f, arcname=os.path.relpath(abs_f, directory))
    return zp


def _worker(job_id, pdf_paths):
    outdir = os.path.join(DATA_DIR, job_id)
    os.makedirs(outdir, exist_ok=True)

    for idx, p in enumerate(pdf_paths):
        campos, _ = parse_pdf(p)
        rel = _copiar_renombrar(p, outdir, campos)

        jobs[job_id]["rows"][idx] |= {
            "new": os.path.basename(rel),
            "rel": rel,
            "progress": 100
        }

    jobs[job_id]["zip"]  = _zip_dir(outdir)
    jobs[job_id]["done"] = True


# ───── rutas ───── #
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    files = request.files.getlist("files")
    if not files:
        return redirect(url_for("home"))

    pdf_paths, tmpdir = [], tempfile.mkdtemp()

    for f in files:
        if _ext_ok(f.filename, ALLOWED_PDF):
            p = os.path.join(tmpdir, f.filename); f.save(p); pdf_paths.append(p)
        elif _ext_ok(f.filename, ALLOWED_ZIP):
            z = os.path.join(tmpdir, f.filename); f.save(z)
            with zipfile.ZipFile(z) as zf: zf.extractall(tmpdir)
            for root, _, fns in os.walk(tmpdir):
                for fn in fns:
                    if _ext_ok(fn, ALLOWED_PDF):
                        pdf_paths.append(os.path.join(root, fn))

    if not pdf_paths:
        shutil.rmtree(tmpdir)
        return "Sin PDFs válidos", 400

    job = uuid.uuid4().hex[:8]
    jobs[job] = {
        "rows": [{"orig": os.path.basename(p), "new": "", "rel": "", "progress": 0}
                 for p in pdf_paths],
        "zip":  None,
        "done": False
    }
    threading.Thread(target=_worker, args=(job, pdf_paths), daemon=True).start()
    return redirect(url_for("progress_page", job=job))


@app.route("/progress/<job>")
def progress_page(job):
    if job not in jobs: abort(404)
    return render_template("progreso.html", job=job)


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
    return send_file(zp, as_attachment=True,
                     download_name="certificados_organizados.zip") if zp else abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
