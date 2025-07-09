import os
import re
import zipfile
import shutil
import pandas as pd
import pytesseract
from pdf2image import convert_from_path

def extract_info_from_image(img):
    text = pytesseract.image_to_string(img, lang='spa')

    nombre = ""
    cc = ""
    nivel = ""
    fecha = ""

    match_nombre = re.search(r'Nombre[:\s]*([A-ZÁÉÍÓÚÑa-záéíóúñ ]{5,})', text)
    match_cc = re.search(r'CC[:\s]*([0-9\.]+)', text)
    match_nivel = re.search(r'(ENTRANTE|VIG[IÍ]A|SUPERVISOR)', text, re.I)
    match_fecha = re.search(r'(\d{2,4}[/-]\d{2}[/-]\d{2,4})', text)

    if match_nombre:
        nombre = match_nombre.group(1).strip()
    if match_cc:
        cc = match_cc.group(1).replace(".", "").strip()
    if match_nivel:
        nivel = match_nivel.group(1).upper()
        if "VIG" in nivel: nivel = "VIGIA"
    if match_fecha:
        fecha = match_fecha.group(1).strip()

    return nombre, cc, nivel, fecha

def process_single_pdf(pdf_path, output_dir):
    images = convert_from_path(pdf_path, dpi=300)
    img = images[0]

    nombre, cc, nivel, fecha = extract_info_from_image(img)
    if not (nombre and cc and nivel):
        nombre = nombre or "NoDetectado"
        cc = cc or "NoDetectado"
        nivel = nivel or "NoDetectado"
    new_filename = f"{nombre}_{cc}.pdf".replace(" ", "_")
    nivel_folder = f"Nivel_{nivel.capitalize()}" if nivel != "NoDetectado" else "SinNivel"

    dest_folder = os.path.join(output_dir, nivel_folder)
    os.makedirs(dest_folder, exist_ok=True)
    dest_path = os.path.join(dest_folder, new_filename)
    shutil.copy2(pdf_path, dest_path)

    return {
        "CC": cc,
        "NOMBRE": nombre,
        "NIVEL": nivel,
        "FECHA": fecha,
        "ARCHIVO": f"{nivel_folder}/{new_filename}"
    }

def process_pdfs(pdf_paths, output_dir):
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)
    resumen = []
    for pdf_path in pdf_paths:
        info = process_single_pdf(pdf_path, output_dir)
        resumen.append(info)

    zip_path = os.path.join(output_dir, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".pdf"):
                    abs_file = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_file, output_dir)
                    zipf.write(abs_file, arcname=rel_path)
    resumen_df = pd.DataFrame(resumen)
    return resumen_df, zip_path
