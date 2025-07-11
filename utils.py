# utils.py  (sustituye todo)
+import fitz, pytesseract, re, unicodedata, os, shutil, zipfile, pandas as pd
+from PIL import Image, ImageOps, ImageFilter
+
+# ------------------ helpers ------------------
+def _norm(txt: str) -> str:
+    """Mayúsculas sin tildes."""
+    return ''.join(c for c in unicodedata.normalize("NFKD", txt)
+                   if not unicodedata.combining(c)).upper()
+
+def _extract(text: str) -> dict:
+    t = _norm(text)
+    return {
+        "NOMBRE": (re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t) or re.search(r'DE\s*:\s*([A-ZÑ ]{5,})', t)
+                   or re.search(r'FUNCIONARIO\s*[:\-]?\s*([A-ZÑ ]{5,})', t)  # otras variantes
+                   ).group(1).strip() if re.search(r'NOMBRE|DE\s*:', t) else '',
+        "CC":     (re.search(r'(?:C[.]?C[.]?|CEDULA|CEDULA DE CIUDADANIA|N[.ºO])\s*[:\-]?\s*([\d\.\s]{7,15})', t)
+                   ).group(1).replace('.', '').replace(' ', '') if re.search(r'C[.]?C|CEDULA|N[.ºO]', t) else '',
+        "NIVEL":  (re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR)\b', t) or re.search(r'(BASICO|AVANZADO)', t)
+                   ).group(1).replace('Í', 'I') if re.search(r'ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO', t) else '',
+        "FECHA":  (re.search(r'(\d{2}/\d{2}/\d{4})', t) or re.search(r'(\d{2}-\d{2}-\d{4})', t)
+                   ).group(1).replace('-', '/') if re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', t) else ''
+    }
+
+# ------------------ OCR ------------------
+def _page_image(pdf_path: str, dpi: int) -> Image.Image:
+    page = fitz.open(pdf_path)[0]
+    pix  = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB)
+    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
+
+def _ocr(img: Image.Image) -> str:
+    return pytesseract.image_to_string(img, lang="spa", config="--oem 3 --psm 6")
+
+def parse_pdf(pdf_path: str) -> tuple[dict, str]:
+    """Devuelve (campos, texto_raw). Reintenta DPI y binarizado."""
+    for dpi, prep in [(200, False), (300, True), (400, True)]:
+        im = _page_image(pdf_path, dpi)
+        if prep:
+            im = ImageOps.grayscale(im).filter(ImageFilter.SHARPEN)
+            im = ImageOps.autocontrast(im)
+        txt = _ocr(im)
+        campos = _extract(txt)
+        if all(campos.values()):
+            return campos, txt
+    return campos, txt  # podría faltar algo
+
+# ------------------ procesador masivo ------------------
+def _renombra_y_copia(pdf_path: str, out_root: str, campos: dict) -> str:
+    slug = f"{campos['NOMBRE'].replace(' ', '_')}_{campos['CC']}".upper()
+    sub  = f"NIVEL_{campos['NIVEL'] or 'DESCONOCIDO'}"
+    os.makedirs(os.path.join(out_root, sub), exist_ok=True)
+    dst = os.path.join(out_root, sub, f"{slug}.pdf")
+    shutil.copy2(pdf_path, dst)
+    return os.path.relpath(dst, out_root)
+
+def process_pdfs(pdf_paths: list[str], out_dir: str):
+    shutil.rmtree(out_dir, ignore_errors=True)
+    os.makedirs(out_dir, exist_ok=True)
+
+    registros = []
+    for p in pdf_paths:
+        campos, _ = parse_pdf(p)
+        ruta_rel = _renombra_y_copia(p, out_dir, campos)
+        campos["ARCHIVO"] = ruta_rel
+        registros.append(campos)
+
+    # ZIP final
+    zip_path = os.path.join(out_dir, "certificados_organizados.zip")
+    with zipfile.ZipFile(zip_path, "w") as zf:
+        for root, _, files in os.walk(out_dir):
+            for fn in files:
+                if fn.lower().endswith(".pdf"):
+                    zf.write(os.path.join(root, fn),
+                             arcname=os.path.relpath(os.path.join(root, fn), out_dir))
+
+    df = pd.DataFrame(registros)
+    return df, zip_path
