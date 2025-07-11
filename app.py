from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, abort
)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, threading, zipfile

from utils import (
    parse_file,                    # decide PDF vs imagen
    _copiar_renombrar,             # renombra/copias PDFs
    save_image_as_pdf_renamed      # convierte imagen→PDF con nombre final
)

app = Flask(__name__)
app.secret_key = "super-secret-key"

# extensiones admitidas
ALLOWED_PDF = {".pdf"}
ALLOWED_IMG = {".jpg", ".jpeg", ".png"}
ALLOWED_ZIP = {".zip"}

# carpeta donde vive cada job
DATA_DIR = "/tmp/cert_jobs"
os.makedirs(DATA_DIR, exist_ok=True)

# memoria en RAM: job_id → {rows, zip, done}
jobs: dict[str, dict] = {}


# ───────────────────── helpers ───────────────────── #
def _ext_ok(name: str, allowed: set[str]) -> bool:
    return os.path.splitext(name)[1].lower() in allowed


def _zip_dir(directory: str) -> str:
    """Crea certificados_organizados.zip con todos los PDFs de directory."""
    zp = os.path.join(directory, "certificados_organizados.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for root, _, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    z.write(abs_f, arcname=os.path.relpath(abs_f, directory))
    return zp


# ───────────────────── worker ───────────────────── #
def _worker(job: str, paths: list[str]):
    """Procesa cada archivo, actualiza progreso y genera el ZIP."""
    outdir = os.path.join(DATA_DIR, job)
    os.makedirs(outdir, exist_ok=True)

    for idx, src in enumerate(paths):
        ext = os.path.splitext(src)[1].lower()
        campos, _, src_path = parse_file(src)  # src_path = src (PDF) o imagen

        if ext in ALLOWED_IMG:
            rel = save_image_as_pdf_renamed(src_path, outdir, campos)
        else:  # PDF
            rel = _copiar_renombrar(src_path, outdir, campos)

        jobs[job]["rows"][idx].update({
            "new": os.path.basename(rel),
            "rel": rel,
            "progress": 100
        })

    jobs[job]["zip"]  = _zip_dir(outdir)
    jobs[job]["done"] = True


# ───────────────────── rutas ───────────────────── #
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

        # archivos sueltos
        if ext in (ALLOWED_PDF | ALLOWED_IMG):
            path = os.path.join(tmpdir, f.filename)
            f.save(path)
            paths.append(path)

        # ZIP: extraer y agregar PDFs/JPEGs
        elif ext in ALLOWED_ZIP:
            zpath = os.path.join(tmpdir, f.filename)
            f.save(zpath)
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(tmpdir)
            for root, _, fns in os.walk(tmpdir):
                for fn in fns:
                    if _ext_ok(fn, ALLOWED_PDF | ALLOWED_IMG):
                        paths.append(os.path.join(root, fn))

    if not paths:
        shutil.rmtree(tmpdir)
        return "No se encontraron archivos PDF/JPEG válidos", 400

    # crear trabajo
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "rows": [{"orig": os.path.basename(p), "new": "", "rel": "", "progress": 0}
                 for p in paths],
        "zip": None,
        "done": False
    }

    threading.Thread(target=_worker, args=(job_id, paths), daemon=True).start()
    return redirect(url_for("progress_page", job=job_id))


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
    return send_file(zp, as_attachment=True,
                     download_name="certificados_organizados.zip") if zp else abort(404)


# ───────────────────── run (dinámico) ───────────────────── #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render inyecta PORT
    app.run(host="0.0.0.0", port=port, debug=True)
