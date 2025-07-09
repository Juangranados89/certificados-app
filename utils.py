import os, re, zipfile, shutil, pandas as pd, pytesseract
from pdf2image import convert_from_path
from PIL import ImageFilter, ImageOps

def preprocess_image(img):
    # 1) Escala de grises
    gray = img.convert("L")
    # 2) Contraste automático
    gray = ImageOps.autocontrast(gray, cutoff=2)
    # 3) Binarización
    bw = gray.point(lambda x: 0 if x < 160 else 255, '1')
    # 4) Mediana para reducir ruido
    bw = bw.filter(ImageFilter.MedianFilter(size=3))
    return bw

def extract_info_from_image(img):
    # Configuración de Tesseract: PSM 6 + whitelist
    custom_config = r'--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÁÉÍÓÚÑáéíóúñ0123456789./-'
    text = pytesseract.image_to_string(img, lang='spa', config=custom_config)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    nombre = cc = nivel = fecha = ""
    for line in lines:
        if not cc:
            m = re.search(r'\b(?:CC|Cédula)[:\s]*([\d\.]{6,15})\b', line, re.I)
            if m:
                cc = m.group(1).replace('.', '')
                continue
        if not nombre:
            m = re.search(r'\bNombre[:\s]*([A-ZÁÉÍÓÚÑ ]{4,})\b', line, re.I)
            if m:
                nombre = m.group(1).title()
                continue
        if not nivel:
            m = re.search(r'\b(ENTRANTE|VIG[IÍ]A|SUPERVISOR)\b', line, re.I)
            if m:
                nivel = m.group(1).upper().replace('Í','I')
                continue
        if not fecha:
            m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', line)
            if m:
                fecha = m.group(1)
                continue
    return nombre, cc, nivel, fecha

def process_single_pdf(pdf_path, output_dir):
    images = convert_from_path(pdf_path, dpi=300)
    img = images[0]
    proc_img = preprocess_image(img)
    nombre, cc, nivel, fecha = extract_info_from_image(proc_img)
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
    for pdf in pdf_paths:
        resumen.append(process_single_pdf(pdf, output_dir))
    zip_path = os.path.join(output_dir, "certificados_organizados.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".pdf"):
                    absf = os.path.join(root, file)
                    relf = os.path.relpath(absf, output_dir)
                    zipf.write(absf, arcname=relf)
    resumen_df = pd.DataFrame(resumen)
    return resumen_df, zip_path
