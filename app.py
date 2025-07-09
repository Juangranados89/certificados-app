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
    # Limpia resultados anteriores
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    saved_files = []
    for file in files:
        path = os.path.join(UPLOAD_DIR, file.filename)
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(path)

    # Procesa PDFs y organiza carpetas
    resumen_df, zip_path = process_pdfs(saved_files, RESULTS_DIR)

    # Guarda el Excel resumen
    resumen_excel = os.path.join(RESULTS_DIR, "resumen.xlsx")
    resumen_df.to_excel(resumen_excel, index=False)

    # Agrega el Excel al ZIP final
    with zipfile.ZipFile(zip_path, "a") as zipf:
        zipf.write(resumen_excel, arcname="resumen.xlsx")

    return FileResponse(zip_path, filename="certificados_organizados.zip")
