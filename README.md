# App Web OCR Certificados PDF

Esta app permite subir certificados PDF, extraer datos por OCR (Nombre, CC, Nivel, Fecha), renombrar y organizar automáticamente, y descargar un ZIP estructurado junto a un Excel resumen.

## Uso

1. Despliega la app en Render.com conectando tu repo de GitHub.
2. Accede al frontend.
3. Sube tus archivos PDF (o ZIP con PDFs).
4. Recibe el ZIP organizado y el Excel resumen.

### Estructura del ZIP

- Nivel_Entrante/
- Nivel_Vigia/
- Nivel_Supervisor/
- resumen.xlsx

### Dependencias

Ver \`requirements.txt\`.  
OCR funciona con \`pytesseract\`. Render instala dependencias de sistema automáticamente.

## Personalización de Regex

Si tus PDFs tienen diferente estructura, ajusta las expresiones regulares en \`utils.py\`.

## Despliegue en Render

1. Sube este repo a GitHub.
2. Entra a [Render.com](https://render.com/), crea un nuevo servicio web, elige tu repo, configura con Python y puerto 10000.
3. ¡Listo!

## Contacto

- Desarrollador: Juan Felipe Granados
- Email: juan.granados@cotema.co
