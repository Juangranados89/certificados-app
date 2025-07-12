def _extract_pdf(text: str):
    t = _norm(text)

    # Nombre
    nom = re.search(r'NOMBRE\s*[:\-]?\s*([A-ZÑ ]{5,})', t)
    # CC
    cc  = re.search(r'(?:C[.]?C[.]?|CEDULA.+?)\s*[:\-]?\s*([\d \.]{7,15})', t)
    # Si no capturó NOMBRE, usa heurísticas
    nombre = nom.group(1).strip() if nom else (
        _guess_prev_line(t, cc.span()) if cc else _guess_between(t)
    )

    # Nivel del certificado (VIGIA / SUPERVISOR / ENTRANTE …)
    nivel = re.search(r'\b(ENTRANTE|VIGI[AI]|SUPERVISOR|BASICO|AVANZADO)\b', t)

    # Fechas (expedición y vencimiento, si existen)
    f_exp = re.search(r'FECHA DE EXPEDICI[ÓO]N[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', t)
    f_gen = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', t)   # fallback: primera fecha

    return {
        "NOMBRE":      nombre,
        "CC":          cc.group(1).replace('.', '').replace(' ', '') if cc else '',
        "NIVEL":       nivel.group(1).replace('Í', 'I') if nivel else '',
        "CERTIFICADO": '',                 # no aplica a estos PDFs
        "FECHA_EXP":  (f_exp or f_gen).group(1).replace('-', '/') if (f_exp or f_gen) else '',
        "FECHA_VEN":  '',                  # estos PDFs no traen vencimiento
    }
