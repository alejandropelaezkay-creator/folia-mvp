import os
import re
import time
import io
from pathlib import Path
import requests
import pypdfium2 as pdfium
import pymupdf as fitz
from PIL import ImageStat
from google import genai
from google.genai import types

CLIENT_ID = os.getenv("PDF_SERVICES_CLIENT_ID", "47ecbefd40624c578b1d84362ffda6c7")
CLIENT_SECRET = os.getenv("PDF_SERVICES_CLIENT_SECRET", "p8e-71yKV_apZKh_1XSSNr5aydixYIAar3F8")
API_KEY = os.getenv("GEMINI_API_KEY")

PATRONES_INICIO = re.compile(r'(^\s*informe\s*:|^\s*oficio\s+n|señor[a]?\s+juez|acta\s+de\s+audiencia|auto\s+interlocutorio|decreto|prove[ií]do|vistos\s*:)', re.IGNORECASE | re.MULTILINE)
PATRONES_CONTINUACION = re.compile(r'(p[aá]gina\s+[2-9]\s+de|continuaci[oó]n)', re.IGNORECASE)

def obtener_token_adobe():
    r = requests.post("https://pdf-services.adobe.io/token", data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()["access_token"]

# Reutilizamos la lógica del optimizador para evitar duplicar código de Adobe
import optimizar_y_renombrar as opt

def clasificar_con_gemini_vision(texto_pagina, bytes_esquina):
    if not API_KEY: return ""
    client = genai.Client(api_key=API_KEY)
    prompt = f"""Analiza la foja judicial (texto y la imagen de la esquina con foliatura).
1. Lee la foliatura manuscrita.
2. Determina el actuado procesal.
Si es página intermedia o prueba, responde: DESCARTAR.
Formato: YYYY-MM-DD [Fs. Folio] TipoActuado: Detalle\n\nTexto: {texto_pagina[:1500]}"""
    try:
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[types.Part.from_bytes(data=bytes_esquina, mime_type="image/jpeg"), prompt],
            config=types.GenerateContentConfig(temperature=0.1)
        )
        return res.text.strip().replace("\n", " ") if res.text else ""
    except:
        return ""

def indexar_desde_web(pdf_path_in, pdf_path_out, token_adobe):
    path_temp = Path(pdf_path_in).with_suffix(".temp.pdf")
    opt.limpiar_paginas_blanco(Path(pdf_path_in), path_temp)
    
    try:
        opt.procesar_bloque_adobe(path_temp, Path(pdf_path_out), token_adobe)
        
        pdf_reader = pdfium.PdfDocument(str(pdf_path_out))
        marcadores = []
        
        for i in range(len(pdf_reader)):
            pagina = pdf_reader[i]
            texto = pagina.get_textpage().get_text_range()
            if not texto or PATRONES_CONTINUACION.search(texto[:800]) or not PATRONES_INICIO.search(texto[:800]):
                continue
            
            bmp = pagina.render(scale=1.5).to_pil()
            w, h = bmp.size
            esquina = bmp.crop((int(w * 0.60), 0, w, int(h * 0.22)))
            b_io = io.BytesIO()
            esquina.save(b_io, format="JPEG", quality=85)
            
            titulo = clasificar_con_gemini_vision(texto, b_io.getvalue())
            if titulo and "DESCARTAR" not in titulo:
                marcadores.append([1, titulo[:75], i + 1])
                
        doc = fitz.open(str(pdf_path_out))
        if marcadores: doc.set_toc(marcadores)
        doc.saveIncr()
        doc.close()
        
    finally:
        if path_temp.exists(): path_temp.unlink()