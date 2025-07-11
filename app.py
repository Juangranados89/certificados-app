# app.py – Flask minimal para certificados
from flask import (
    Flask, render_template, request, redirect, url_for,
    send_file, flash
)
import os, tempfile, shutil
from tabulate import tabulate
from utils import parse_pdf, process_pdfs

app = Flask(__name__)
app.secret_key = "super-secret-key-change-me"

ALLOWED_EXT = {".pdf"}


def _allowed(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXT


# ------------------------------------------------------------------ #
# Cargar UN PDF y mostrar tabla + texto                              #
# ------------------------------------------------------------------ #
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        pdf = request.files.get("pdf")
        if not pdf or not _allowed(pdf.filename):
            flash("Sube un archivo PDF válido", "error")
            return redirect(request.url)

        tmpdir = tempfile.mkdtemp()
        inpath = os.path.join(tmpdir, pdf.filename)
        pdf.save(inpath)

        campos, texto = parse_pdf(inpath)
        shutil.rmtree(tmpdir)

        tabla_md = tabulate([campos.values()], headers=campos.keys(), tablefmt="github")
        return render_template(
            "resultado.html",
            tabla_markdown=tabla_md,
            texto_raw=texto
        )
    return render_template("index.html")


# ------------------------------------------------------------------ #
# Cargar MÚLTIPLES PDFs y generar ZIP / Excel                        #
# ------------------------------------------------------------------ #
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
    df, zip_path = process_pdfs(paths, outdir)

    # Guardar Excel
    excel_path = os.path.join(outdir, "listado.xlsx")
    df.to_excel(excel_path, index=False)

    # Enviar ZIP al usuario
    return send_file(
        zip_path,
        as_attachment=True,
        download_name="certificados_organizados.zip"
    )


if __name__ == "__main__":
    app.run(debug=True, port=8000)
