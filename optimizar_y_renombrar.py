import os
import re
import time
from pathlib import Path
import requests
import pypdfium2 as pdfium
import pikepdf
from PIL import ImageStat
from google import genai
from google.genai import types

CLIENT_ID = os.getenv("PDF_SERVICES_CLIENT_ID", "47ecbefd40624c578b1d84362ffda6c7")
CLIENT_SECRET = os.getenv("PDF_SERVICES_CLIENT_SECRET", "p8e-71yKV_apZKh_1XSSNr5aydixYIAar3F8")
API_KEY = os.getenv("GEMINI_API_KEY")

UMBRAL_BLANCO = 1.5

SYSTEM_PROMPT = """Eres un asistente legal experto en gestión documental y archivística judicial en Bolivia.
Analiza el texto y devuelve EXCLUSIVAMENTE el nombre estandarizado según las reglas:
- Fechas al inicio YYYY-MM-DD.
- NOMBRES: Solo PRIMER NOMBRE y PRIMER APELLIDO.
- Sin extensiones, guiones bajos ni explicaciones.
Estructuras:
1. Notariales: YYYY-MM-DD inst. [Nro] [Detalle]
2. Judiciales: YYYY-MM-DD [Fs. Rango] [Nombre], [Acción]
3. Contratos: YYYY-MM-DD [ENTIDAD] CONTR [Tipo] [Contraparte]"""

def limpiar_paginas_blanco(input_path: Path, output_path: Path):
    doc_vis = pdfium.PdfDocument(str(input_path))
    doc_save = pikepdf.open(str(input_path))
    valid = []
    for i in range(len(doc_vis)):
        bmp = doc_vis[i].render(scale=0.25)
        img = bmp.to_pil().convert("L")
        if ImageStat.Stat(img).stddev[0] > UMBRAL_BLANCO:
            valid.append(doc_save.pages[i])
    
    if valid:
        out = pikepdf.new()
        out.pages.extend(valid)
        out.save(str(output_path))
    else:
        doc_save.save(str(output_path))
    doc_vis.close()
    doc_save.close()

def obtener_token_adobe():
    r = requests.post(
        "https://pdf-services.adobe.io/token", 
        data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, 
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    r.raise_for_status()
    return r.json()["access_token"]

def procesar_bloque_adobe(entrada_bloque, salida_bloque, token):
    hdr = {"x-api-key": CLIENT_ID, "Authorization": f"Bearer {token}"}
    
    # 1. Obtener URL de subida
    up_res = requests.post(
        "https://pdf-services.adobe.io/assets", 
        headers={**hdr, "Content-Type": "application/json"}, 
        json={"mediaType": "application/pdf"}
    ).json()
    
    # 2. Subir archivo
    with open(entrada_bloque, "rb") as f:
        requests.put(
            up_res["uploadUri"], 
            data=f, 
            headers={"Content-Type": "application/pdf"}
        ).raise_for_status()
    
    # 3. Iniciar OCR
    ocr_r = requests.post(
        "https://pdf-services.adobe.io/operation/ocr", 
        headers={**hdr, "Content-Type": "application/json"}, 
        json={"assetID": up_res["assetID"], "ocrType": "searchable_image", "ocrLang": "es-ES"}
    )
    
    while True:
        st = requests.get(ocr_r.headers["location"], headers=hdr).json()
        if st.get("status") == "done":
            asset_ocr = st["asset"]["assetID"]
            break
        time.sleep(2)
        
    # 4. Comprimir PDF
    cmp_r = requests.post(
        "https://pdf-services.adobe.io/operation/compresspdf", 
        headers={**hdr, "Content-Type": "application/json"}, 
        json={"assetID": asset_ocr, "compressionLevel": "HIGH"}
    )
    
    while True:
        st_c = requests.get(cmp_r.headers["location"], headers=hdr).json()
        if st_c.get("status") == "done":
            with open(salida_bloque, "wb") as f:
                f.write(requests.get(st_c["asset"]["downloadUri"]).content)
            break
        time.sleep(2)

def obtener_nombre_gemini(pdf_path: Path):
    if not API_KEY: 
        return ""
    
    client = genai.Client(api_key=API_KEY)
    pdf = pdfium.PdfDocument(str(pdf_path))
    
    indices = list(range(min(3, len(pdf)))) + list(range(max(0, len(pdf) - 3), len(pdf)))
    texto_extraido = []
    
    for i in sorted(set(indices)):
        texto_pagina = pdf[i].get_textpage().get_text_range()
        texto_extraido.append(texto_pagina[:1500])
        
    texto = "".join(texto_extraido)
    pdf.close()
    
    try:
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Analiza este texto documental:\n\n{texto}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT, 
                temperature=0.1
            )
        )
        if res.text:
            limpio = res.text.strip().replace("\n", "")
            return re.sub(r'[\\/*?:"<>|]', '-', limpio)[:120]
        return ""
    except Exception:
        return ""

def procesar_desde_web(pdf_path_in, pdf_path_out, token_adobe):
    path_temp = Path(pdf_path_in).with_suffix(".temp.pdf")
    limpiar_paginas_blanco(Path(pdf_path_in), path_temp)
    try:
        procesar_bloque_adobe(path_temp, Path(pdf_path_out), token_adobe)
        nombre = obtener_nombre_gemini(Path(pdf_path_out))
        return nombre
    finally:
        if path_temp.exists(): 
            path_temp.unlink()
