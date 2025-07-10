# app.py
import os
import shutil
import zipfile
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from utils import process_pdfs
import pandas as pd

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"
RESULTS_DIR = "results"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload/")
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    # limpiar resultados previos
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    saved = []
    for file in files:
        path = os.path.join(UPLOAD_DIR, file.filename)
        with open(path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        saved.append(path)

    # procesa y organiza
    df, zip_path = process_pdfs(saved, RESULTS_DIR)

    # guarda Excel
    excel_path = os.path.join(RESULTS_DIR, "resumen.xlsx")
    df.to_excel(excel_path, index=False)
    # añade al ZIP
    with zipfile.ZipFile(zip_path, "a") as zf:
        zf.write(excel_path, arcname="resumen.xlsx")

    return FileResponse(zip_path, filename="certificados_organizados.zip")
