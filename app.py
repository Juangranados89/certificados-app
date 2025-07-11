from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, abort
)
from werkzeug.utils import safe_join
import os, tempfile, shutil, uuid, threading, zipfile
from utils import (
    parse_file,              # decide PDF vs imagen
    _copiar_renombrar,       # copia/renombra PDFs
    save_image_as_pdf_renamed  # convierte imagen→PDF con nombre final
)

app = Flask(__name__)
app.secret_key = "secret-key"

# extensiones aceptadas
ALLOWED_PDF = {'.pdf'}
ALLOWED_IMG = {'.jpg', '.jpeg', '.png'}
ALLOWED_ZIP = {'.zip'}

# directorio raíz de trabajos
DATA_DIR = "/tmp/cert_jobs"
os.makedirs(DATA_DIR, exist_ok=True)

# memoria sencilla de jobs
jobs: dict[str, dict] = {}   # job_id → {rows, zip, done}


# ───────────────────────── helpers ───────────────────────── #
def _ext_ok(fname: str, allowed: set[str]) -> bool:
    return os.path.splitext(fname)[1].lower() in allowed


def _zip_dir(directory: str) -> str:
    """Empaqueta todos los PDFs de 'directory' en un ZIP y lo devuelve."""
    zip_path = os.path.join(directory, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _, files in os.walk(directory):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    abs_f = os.path.join(root, fn)
                    zf.write(abs_f, arcname=os.path.relpath(abs_f, directory))
    return zip_path


# ───────────────────────── worker thread ───────────────────────── #
def _worker(job_id: str, paths: list[str]):
    outdir = os.path.join(DATA_DIR, job_id)
    os.makedirs(outdir, exist_ok=True)

    for idx, p in enumerate(paths):
        ext = os.path.splitext(p)[1].lower()
        campos, _, sr_
