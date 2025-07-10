# app.py

import os
import shutil
import zipfile
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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

# Estado de trabajos en memoria
jobs: dict[str, dict] = {}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def run_job(job_id: str, paths: list[str]):
    jobs[job_id] = {"pct": 0,  "step": "Inicio"}
    jobs[job_id] = {"pct": 10, "step": "Procesando certificados"}
    df, zip_path = process_pdfs(paths, RESULTS_DIR)

    jobs[job_id] = {"pct": 60, "step": "Generando Excel resumen"}
    excel = os.path.join(RESULTS_DIR, f"{job_id}_resumen.xlsx")
    df.to_excel(excel, index=False)

    jobs[job_id] = {"pct": 80, "step": "Empaquetando ZIP"}
    with zipfile.ZipFile(zip_path, "a") as zf:
        zf.write(excel, arcname="resumen.xlsx")

    jobs[job_id] = {"pct": 100, "step": "Completado", "zip": zip_path}

@app.post("/upload/")
async def upload_files(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    # Limpia resultados previos
    if os.path.exists(RESULTS_DIR):
        shutil.rmtree(RESULTS_DIR)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    saved = []
    for f in files:
        p = os.path.join(UPLOAD_DIR, f.filename)
        with open(p, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved.append(p)

    job_id = str(uuid4())
    jobs[job_id] = {"pct": 0, "step": "En cola"}
    background_tasks.add_task(run_job, job_id, saved)
    return JSONResponse({"job_id": job_id})

@app.get("/progress/{job_id}")
async def progress(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Job no encontrado"}, status_code=404)
    return jobs[job_id]

@app.get("/download/{job_id}")
async def download(job_id: str):
    info = jobs.get(job_id, {})
    if "zip" not in info:
        return JSONResponse({"error": "No listo"}, status_code=404)
    return FileResponse(info["zip"], filename="certificados_organizados.zip")
