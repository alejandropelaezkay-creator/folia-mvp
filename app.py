import io
import os
import re
import json
import time
import zipfile
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import requests
import streamlit as st
import pypdfium2 as pdfium
from pypdf import PdfReader
import pikepdf
from PIL import ImageStat
from google import genai
from google.genai import types

# ==============================================================================
# 1. CONFIGURACIÓN DE SECRETOS (SIN CREDENCIALES INCRUSTADAS EN CÓDIGO)
# ==============================================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
ADOBE_CLIENT_ID = st.secrets.get("PDF_SERVICES_CLIENT_ID") or os.getenv("PDF_SERVICES_CLIENT_ID", "")
ADOBE_CLIENT_SECRET = st.secrets.get("PDF_SERVICES_CLIENT_SECRET") or os.getenv("PDF_SERVICES_CLIENT_SECRET", "")
GEMINI_MODEL = "gemini-3.8-flash"

st.set_page_config(
    page_title="Fol.ia | Suite Legal de Expedientes",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .metric-card { background-color: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 5px solid #1a365d; margin-bottom: 12px; }
    .guia-nomenclatura { background-color: #f1f3f5; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 0.88em; color: #343a40; }
    .privacy-badge { background-color: #e6fffa; color: #234e52; padding: 0.35rem 0.75rem; border-radius: 6px; font-size: 0.78rem; font-weight: 600; display: inline-block; margin-bottom: 0.8rem; border: 1px solid #b2f5ea; }
    .demo-badge { background-color: #fefcbf; color: #744210; padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; display: inline-block; margin-bottom: 0.6rem; }
</style>
""", unsafe_allow_html=True)

# Estado persistente de sesión
if "creditos" not in st.session_state:
    st.session_state.creditos = 1500
if "historial_consumo" not in st.session_state:
    st.session_state.historial_consumo = []
if "resultados_docs" not in st.session_state:
    st.session_state.resultados_docs = []
if "resultados_exp" not in st.session_state:
    st.session_state.resultados_exp = []


# ==============================================================================
# 2. VALIDACIÓN PREVIA Y UTILIDADES
# ==============================================================================
def validar_pdf(pdf_bytes: bytes, nombre: str) -> tuple[bool, str, int]:
    """Valida que el archivo sea un PDF íntegro, legible, sin contraseña y con páginas."""
    if not pdf_bytes or len(pdf_bytes) < 100:
        return False, f"'{nombre}' está vacío o es demasiado pequeño para ser un PDF válido.", 0
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        return False, f"'{nombre}' no tiene estructura PDF válida (posiblemente otro tipo de archivo renombrado a .pdf).", 0
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            return False, f"'{nombre}' está protegido con contraseña. Desbloquéalo antes de subirlo.", 0
        num_pags = len(reader.pages)
        if num_pags == 0:
            return False, f"'{nombre}' no contiene ninguna página.", 0
        return True, "OK", num_pags
    except Exception:
        return False, f"'{nombre}' está dañado o corrupto y no puede leerse como PDF.", 0


def generar_miniatura(pdf_bytes: bytes):
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        imagen = pdf[0].render(scale=0.45).to_pil()
        pdf.close()
        return imagen
    except Exception:
        return None


def crear_zip_resultados(resultados: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        usados = set()
        for r in resultados:
            nombre = r["nombre_final"]
            if nombre in usados:
                base, ext = os.path.splitext(nombre)
                nombre = f"{base}_{r['id']}{ext}"
            usados.add(nombre)
            zf.writestr(nombre, r["bytes"])
    return buf.getvalue()


def limpiar_titulo_marcador(texto: str) -> str:
    if not texto:
        return ""
    limpio = re.sub(r'[\\/:*?"<>|]', "", texto.strip().replace("\n", " ").replace("\r", " "))
    limpio = re.sub(r'\s+', " ", limpio).strip()
    if limpio.lower().endswith(".pdf"):
        limpio = limpio[:-4].strip()
    return limpio[:180].strip()


# ==============================================================================
# 3. MOTORES DE PROCESAMIENTO (INTEGRIDAD + ADOBE OCR + GEMINI IA)
# ==============================================================================
def purgar_blancos_seguro(input_path: Path, output_path: Path) -> list[int]:
    """
    Elimina SOLO páginas sin texto extraíble y con desviación visual < 1.0 (totalmente vacías).
    Retorna la lista de páginas originales (1-based) eliminadas.
    """
    doc_vis = pdfium.PdfDocument(str(input_path))
    doc_save = pikepdf.open(str(input_path))
    valid_pages = []
    eliminadas = []

    for i in range(len(doc_vis)):
        txt = (doc_vis[i].get_textpage().get_text_range() or "").strip()
        if len(txt) > 0:
            valid_pages.append(doc_save.pages[i])
            continue
        bmp = doc_vis[i].render(scale=0.25)
        img = bmp.to_pil().convert("L")
        if ImageStat.Stat(img).stddev[0] >= 1.0:
            valid_pages.append(doc_save.pages[i])
        else:
            eliminadas.append(i + 1)

    if valid_pages:
        out = pikepdf.new()
        out.pages.extend(valid_pages)
        out.save(str(output_path))
        out.close()
    else:
        # Si todas parecían vacías, conserva el documento íntegro por seguridad
        doc_save.save(str(output_path))
        eliminadas = []

    doc_vis.close()
    doc_save.close()
    return eliminadas


def esperar_trabajo_adobe(status_url: str, headers: dict, etapa: str, timeout_max: int = 180) -> dict:
    inicio = time.time()
    while True:
        if time.time() - inicio > timeout_max:
            raise TimeoutError(f"Tiempo de espera agotado ({timeout_max}s) durante {etapa} en Adobe.")
        r = requests.get(status_url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        estado = data.get("status")
        if estado == "done":
            return data
        if estado == "failed":
            detalle = data.get("error", {}).get("message", "Error desconocido del proveedor.")
            raise RuntimeError(f"Adobe rechazó el trabajo en {etapa}: {detalle}")
        time.sleep(2)


def procesar_pdf_adobe(pdf_bytes: bytes, aplicar_limpieza: bool, nivel_compresion: str) -> dict:
    if not ADOBE_CLIENT_ID or not ADOBE_CLIENT_SECRET:
        raise RuntimeError("Faltan las credenciales de Adobe en Streamlit Secrets.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_in, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_temp, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_out:
        t_in.write(pdf_bytes)
        path_in, path_temp, path_out = Path(t_in.name), Path(t_temp.name), Path(t_out.name)

    try:
        fojas_originales = len(PdfReader(path_in).pages)
        eliminadas = []

        if aplicar_limpieza:
            eliminadas = purgar_blancos_seguro(path_in, path_temp)
        else:
            shutil.copy2(path_in, path_temp)

        # 1. Token Adobe
        r_token = requests.post(
            "https://pdf-services.adobe.io/token",
            data={"client_id": ADOBE_CLIENT_ID, "client_secret": ADOBE_CLIENT_SECRET},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25
        )
        r_token.raise_for_status()
        token = r_token.json()["access_token"]
        hdr = {"x-api-key": ADOBE_CLIENT_ID, "Authorization": f"Bearer {token}"}

        # 2. Subida de asset
        up_r = requests.post(
            "https://pdf-services.adobe.io/assets",
            headers={**hdr, "Content-Type": "application/json"},
            json={"mediaType": "application/pdf"},
            timeout=30
        )
        up_r.raise_for_status()
        up_res = up_r.json()

        with open(path_temp, "rb") as f:
            requests.put(up_res["uploadUri"], data=f, headers={"Content-Type": "application/pdf"}, timeout=120).raise_for_status()

        # 3. OCR (searchable_image_exact evita fuentes corruptas de CamScanner)
        ocr_r = requests.post(
            "https://pdf-services.adobe.io/operation/ocr",
            headers={**hdr, "Content-Type": "application/json"},
            json={"assetID": up_res["assetID"], "ocrType": "searchable_image_exact", "ocrLang": "es-ES"},
            timeout=30
        )
        ocr_r.raise_for_status()
        st_ocr = esperar_trabajo_adobe(ocr_r.headers["location"], hdr, "OCR")
        asset_ocr = st_ocr["asset"]["assetID"]
        dl_url = st_ocr["asset"]["downloadUri"]

        # 4. Compresión configurable
        cmp_r = requests.post(
            "https://pdf-services.adobe.io/operation/compresspdf",
            headers={**hdr, "Content-Type": "application/json"},
            json={"assetID": asset_ocr, "compressionLevel": nivel_compresion},
            timeout=30
        )
        cmp_r.raise_for_status()
        st_cmp = esperar_trabajo_adobe(cmp_r.headers["location"], hdr, "Compresión")
        dl_url = st_cmp["asset"]["downloadUri"]

        # 5. Descarga
        dl_r = requests.get(dl_url, timeout=120)
        dl_r.raise_for_status()
        with open(path_out, "wb") as f:
            f.write(dl_r.content)

        # Saneamiento ligero con pikepdf
        try:
            with pikepdf.open(str(path_out), allow_overwriting_input=True) as pk:
                pk.save(str(path_out))
        except Exception:
            pass

        bytes_finales = path_out.read_bytes()
        fojas_conservadas = len(PdfReader(io.BytesIO(bytes_finales)).pages)

        return {
            "bytes": bytes_finales,
            "fojas_originales": fojas_originales,
            "fojas_conservadas": fojas_conservadas,
            "paginas_eliminadas": eliminadas,
            "kb_orig": len(pdf_bytes) / 1024.0,
            "kb_final": len(bytes_finales) / 1024.0,
        }
    finally:
        for p in (path_in, path_temp, path_out):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


def obtener_nombre_ia(pdf_bytes: bytes, tipo_regla: str, regla_personalizada: str) -> tuple[str | None, str]:
    """Extrae texto y genera el nombre siguiendo estrictamente las plantillas anunciadas."""
    if not GEMINI_API_KEY:
        return None, "Falta GEMINI_API_KEY en Secrets."

    texto = ""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        for i in range(min(5, len(pdf))):
            texto += (pdf[i].get_textpage().get_text_range() or "") + "\n"
        pdf.close()
    except Exception:
        pass

    if len(texto.strip()) < 15:
        return None, "Texto insuficiente tras OCR para renombrar con IA."

    if tipo_regla == "Predeterminada del sistema":
        instrucciones = (
            "Clasifica el documento y aplica EXACTAMENTE la plantilla correspondiente:\n"
            "1) Notariales: YYYY-MM-DD inst. [Nro] [Detalle]\n"
            "2) Judiciales: YYYY-MM-DD [Fs. Rango] [Primer Nombre Primer Apellido], [Acción]\n"
            "   (Si no hay foliatura visible en el documento, omite [Fs. Rango]. Si es resolución judicial, usa el cargo ej. Juez, Vocal).\n"
            "3) Contratos: YYYY-MM-DD [ENTIDAD] CONTR [Tipo] [Contraparte]\n"
            "REGLA CRÍTICA: Si la fecha no figura en el documento, usa 'SIN-FECHA' en lugar de inventarla."
        )
    else:
        instrucciones = f"Aplica estrictamente esta regla personalizada del usuario: {regla_personalizada}\nSi un dato no aparece en el texto, no lo inventes."

    prompt = (
        f"{instrucciones}\n\n"
        "Devuelve ÚNICAMENTE un objeto JSON válido con la clave 'nombre_archivo' (sin extensión .pdf, sin caracteres / \\ : * ? \" < > |):\n"
        '{"nombre_archivo": "..."}\n\n'
        f"TEXTO DEL DOCUMENTO:\n{texto[:6000]}"
    )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json")
        )
        data = json.loads(res.text.strip()) if res.text else {}
        nombre = data.get("nombre_archivo", "").strip()
        if not nombre:
            return None, "La IA devolvió un nombre vacío."
        limpio = re.sub(r'[\\/*?:"<>|]', "-", nombre).replace("\n", " ").strip()
        if limpio.lower().endswith(".pdf"):
            limpio = limpio[:-4].strip()
        return limpio[:130], "OK"
    except Exception as e:
        return None, f"Error IA: {e}"


# ==============================================================================
# 4. INDEXACIÓN JERÁRQUICA DE 3 NIVELES (INTEGRADA DE indexador_expediente.py)
# ==============================================================================
SYSTEM_PROMPT_EXPEDIENTE = """Eres un asistente legal experto en gestión documental y archivística judicial/notarial en Bolivia.
Recibirás el texto página por página de un expediente PDF junto con recortes de la esquina superior derecha para leer la foliatura real.

CONTEXTO DEL PROCESO:
{contexto_partes}

Estructura los marcadores en hasta 3 NIVELES JERÁRQUICOS y devuelve EXCLUSIVAMENTE un arreglo JSON válido:
[
  {{"nivel": 1, "pagina_pdf": 1, "titulo": "2026-09-17 [Fs. 101-104] Parte Demandante, Memorial y actuados"}},
  {{"nivel": 2, "pagina_pdf": 1, "titulo": "2026-09-17 [Fs. 101-102] Parte Demandante, Memorial principal"}},
  {{"nivel": 2, "pagina_pdf": 3, "titulo": "2026-09-18 [Fs. 103] Juez, Decreto se tiene presente"}},
  {{"nivel": 2, "pagina_pdf": 4, "titulo": "Pruebas documentales adjuntas"}},
  {{"nivel": 3, "pagina_pdf": 4, "titulo": "2026-09-10 [Fs. 104] Tercero, Carta"}}
]

REGLAS:
1. Usa la foliatura real visible en el documento/esquina (ej. [Fs. 101-103]). Si NO hay foliatura visible, NO inventes números de foja; usa [Pág. X].
2. En resoluciones/decretos/autos usa el cargo ("Juez", "Vocal", "Árbitro"), no el nombre propio.
3. En partes usa Primer Nombre y Primer Apellido.
4. Sin caracteres prohibidos (/ \\ : * ? " < > |) ni extensión .pdf."""

SYSTEM_PROMPT_DOC_UNICO = """Eres un asistente legal experto en estructuración de escritos jurídicos, demandas, laudos y contratos largos.
CONTEXTO DEL DOCUMENTO:
{contexto_partes}

Detecta la jerarquía real de TÍTULOS, CAPÍTULOS, SUBTÍTULOS y ANEXOS en hasta 3 NIVELES (1, 2, 3) y devuelve EXCLUSIVAMENTE un arreglo JSON válido:
[
  {{"nivel": 1, "pagina_pdf": 1, "titulo": "Carátula - Contrato"}},
  {{"nivel": 1, "pagina_pdf": 2, "titulo": "Cláusula Primera - Objeto"}},
  {{"nivel": 2, "pagina_pdf": 3, "titulo": "1.1. Alcance técnico"}}
]
Sin caracteres prohibidos (/ \\ : * ? " < > |) ni extensión .pdf."""


def extraer_esquina_foliatura(pagina_pdfium) -> bytes:
    bmp = pagina_pdfium.render(scale=1.2).to_pil()
    w, h = bmp.size
    esquina = bmp.crop((int(w * 0.55), 0, w, int(h * 0.25)))
    b_io = io.BytesIO()
    esquina.save(b_io, format="JPEG", quality=75)
    return b_io.getvalue()


def indexar_jerarquico_ia(pdf_bytes: bytes, modo: str, contexto_partes: str) -> tuple[bytes, list]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en Secrets para la indexación jerárquica.")

    pdf_reader = pdfium.PdfDocument(pdf_bytes)
    total_pags = len(pdf_reader)
    paginas_texto = [(pdf_reader[i].get_textpage().get_text_range() or "").strip() for i in range(total_pags)]

    client = genai.Client(api_key=GEMINI_API_KEY)
    sys_prompt = (SYSTEM_PROMPT_DOC_UNICO if modo == "DOCUMENTO_UNICO" else SYSTEM_PROMPT_EXPEDIENTE).format(
        contexto_partes=contexto_partes or "Proceso judicial o documental general."
    )

    tam_ventana = 25 if modo == "DOCUMENTO_UNICO" else 15
    marcadores_raw = []

    for inicio in range(0, total_pags, tam_ventana):
        fin = min(inicio + tam_ventana, total_pags)
        contents = []
        bloque_texto = []

        for p in range(inicio, fin):
            if modo == "EXPEDIENTE":
                img_bytes = extraer_esquina_foliatura(pdf_reader[p])
                contents.append(f"[ESQUINA FOLIATURA - PÁGINA PDF {p + 1}]")
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                txt_pag = paginas_texto[p][:1200]
            else:
                txt_pag = paginas_texto[p][:2500]
            bloque_texto.append(f"=== PÁGINA PDF {p + 1} DE {total_pags} ===\n{txt_pag}")

        contents.append(
            f"Identifica la estructura jerárquica entre las páginas PDF {inicio + 1} y {fin}. Devuelve SOLO el JSON array.\n\n"
            + "\n\n".join(bloque_texto)
        )

        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        items = json.loads(res.text.strip()) if res.text else []
        if isinstance(items, list):
            marcadores_raw.extend(items)

    pdf_reader.close()

    # Normalizar y deduplicar jerarquía
    marcadores = []
    nivel_anterior = 0
    vistos = set()
    for item in sorted(marcadores_raw, key=lambda x: (int(x.get("pagina_pdf", 1)), int(x.get("nivel", 1)))):
        pag = max(1, min(int(item.get("pagina_pdf", 1)), total_pags))
        nivel = max(1, min(int(item.get("nivel", 1)), 3))
        titulo = limpiar_titulo_marcador(str(item.get("titulo", "")))
        if not titulo or (pag, titulo.lower()) in vistos:
            continue
        vistos.add((pag, titulo.lower()))
        if not marcadores:
            nivel = 1
        elif nivel > nivel_anterior + 1:
            nivel = nivel_anterior + 1
        marcadores.append([nivel, titulo, pag])
        nivel_anterior = nivel

    # Escribir marcadores en PDF usando pikepdf
    buf_out = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf_out:
        with pdf_out.open_outline() as outline:
            outline.root.clear()
            pila = {0: outline.root}
            for nivel, titulo, pag_1b in marcadores:
                item = pikepdf.OutlineItem(titulo, max(0, min(pag_1b - 1, len(pdf_out.pages) - 1)))
                nivel_padre = nivel - 1
                while nivel_padre > 0 and nivel_padre not in pila:
                    nivel_padre -= 1
                if nivel_padre == 0:
                    pila[0].append(item)
                else:
                    pila[nivel_padre].children.append(item)
                pila[nivel] = item
        pdf_out.save(buf_out)

    return buf_out.getvalue(), marcadores


# ==============================================================================
# 5. BARRA LATERAL (CONFIGURACIÓN, CRÉDITOS Y TRANSPARENCIA)
# ==============================================================================
with st.sidebar:
    try:
        st.image("Logo.jpg", use_container_width=True)
    except Exception:
        st.title("⚖️ Fol.ia")

    st.markdown("<span class='demo-badge'>MODO DEMO (SESIÓN LOCAL)</span>", unsafe_allow_html=True)
    st.markdown("<span class='privacy-badge'>🔒 Procesamiento temporal sin almacenamiento permanente</span>", unsafe_allow_html=True)
    st.caption("Tus documentos listos para el archivo y la Inteligencia Artificial.")

    with st.expander("ℹ️ Cómo se procesan tus datos"):
        st.write(
            "1. Los archivos se procesan en memoria temporal y se eliminan del servidor local al finalizar cada tarea.\n"
            "2. El PDF se envía vía API a **Adobe PDF Services** (OCR y compresión).\n"
            "3. El texto extraído (y recortes de foliatura en expedientes) se envía vía API a **Google Gemini** para nomenclatura/indexación."
        )

    st.metric(label="Bolsa de Créditos (Fojas)", value=f"{st.session_state.creditos:,} fojas")

    with st.expander("💳 Recargar Créditos (Simulador Demo)"):
        st.write("• **Litigio:** 2,500 fojas — $25 USD ($0.010/foja)")
        st.write("• **Corporativo:** 10,000 fojas — $80 USD ($0.008/foja)")
        if st.button("Simular Recarga +1,000 fojas"):
            st.session_state.creditos += 1000
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Configuración Global")
    opt_limpiar = st.checkbox(
        "Depurar páginas completamente vacías",
        value=False,
        help="Desactivado por defecto para máxima integridad. Si se activa, solo elimina páginas sin texto y sin contenido visual."
    )
    nivel_compresion = st.select_slider(
        "Nivel de compresión PDF",
        options=["LOW", "MEDIUM", "HIGH"],
        value="MEDIUM",
        help="LOW prioriza máxima nitidez de sellos; HIGH reduce más el tamaño del archivo."
    )

    if not ADOBE_CLIENT_ID or not ADOBE_CLIENT_SECRET or not GEMINI_API_KEY:
        st.error("⚠️ Faltan claves API en Streamlit Secrets. Configúralas antes de procesar.")


# ==============================================================================
# 6. ÁREA DE TRABAJO PRINCIPAL
# ==============================================================================
tab_docs, tab_expedientes, tab_liquidacion = st.tabs([
    "📄 A. Documentos Individuales",
    "📚 B. Expedientes (Índice Jerárquico)",
    "📊 Liquidación"
])

# --- PESTAÑA A: DOCUMENTOS INDIVIDUALES ---
with tab_docs:
    st.header("Saneamiento y Renombrado Automático")
    st.write("Aplica OCR, compresión controlada y renombrado estricto según plantilla.")

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        cliente_doc = st.text_input("Cliente / Asunto (para liquidación):", value="General", key="cli_doc")
    with col_meta2:
        tipo_regla = st.radio("Regla de nomenclatura:", ["Predeterminada del sistema", "Personalizada"], horizontal=True)

    if tipo_regla == "Predeterminada del sistema":
        st.markdown("""
        <div class="guia-nomenclatura">
        <b>Plantillas Estándar Fol.ia:</b><br>
        • Notariales: YYYY-MM-DD inst. [Nro] [Detalle]<br>
        • Judiciales: YYYY-MM-DD [Fs. Rango] [Nombre], [Acción]<br>
        • Contratos: YYYY-MM-DD [ENTIDAD] CONTR [Tipo] [Contraparte]
        </div>
        """, unsafe_allow_html=True)
        regla_personalizada = ""
    else:
        regla_personalizada = st.text_input(
            "✨ Instrucciones de Nomenclatura (Funciona con Inteligencia Artificial):",
            placeholder="Ej: YYYY-MM-DD [Nombre del Cliente] - [Tipo de documento]",
            key="regla_ia"
        )

    st.divider()
    archivos_docs = st.file_uploader("Arrastra documentos individuales (PDF)", type=["pdf"], accept_multiple_files=True, key="up_docs")

    if archivos_docs:
        # Validación previa inmediata
        validos_docs = []
        total_pags_est = 0
        for arch in archivos_docs:
            ok, msg, num_p = validar_pdf(arch.getvalue(), arch.name)
            if ok:
                validos_docs.append((arch, num_p))
                total_pags_est += num_p
            else:
                st.error(f"❌ {msg}")

        if validos_docs:
            cols_prev = st.columns(min(len(validos_docs), 4))
            for idx, (arch, num_p) in enumerate(validos_docs):
                with cols_prev[idx % 4]:
                    mini = generar_miniatura(arch.getvalue())
                    if mini:
                        st.image(mini, caption=f"📄 {arch.name[:18]} ({num_p} págs.)", use_container_width=True)

            if st.button(f"🚀 Procesar y Renombrar ({total_pags_est} fojas est.)", type="primary", key="btn_proc_docs"):
                if tipo_regla == "Personalizada" and not regla_personalizada.strip():
                    st.warning("⚠️ Escribe tus instrucciones de nomenclatura personalizada antes de procesar.")
                elif st.session_state.creditos < total_pags_est:
                    st.error(f"❌ Saldo insuficiente. Necesitas ~{total_pags_est} fojas y tienes {st.session_state.creditos}.")
                else:
                    nuevos_resultados = []
                    for idx, (arch, _) in enumerate(validos_docs):
                        with st.status(f"Procesando: {arch.name}", expanded=True) as status:
                            try:
                                st.write("⚙️ Aplicando OCR y compresión en la nube...")
                                res = procesar_pdf_adobe(arch.getvalue(), opt_limpiar, nivel_compresion)

                                st.write("🤖 Aplicando regla de nomenclatura con IA...")
                                nombre_ia, msg_ia = obtener_nombre_ia(res["bytes"], tipo_regla, regla_personalizada)

                                if nombre_ia:
                                    nombre_final = f"{nombre_ia}.pdf"
                                else:
                                    st.warning(f"⚠️ Renombrado omitido ({msg_ia}). Se conserva nombre base.")
                                    nombre_final = f"{arch.name.replace('.pdf', '')}_FolIA.pdf"

                                st.session_state.creditos -= res["fojas_conservadas"]
                                st.session_state.historial_consumo.append({
                                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "Cliente / Asunto": cliente_doc.strip() or "General",
                                    "Archivo": nombre_final,
                                    "Fojas": res["fojas_conservadas"],
                                    "Tipo": "Documento"
                                })
                                nuevos_resultados.append({
                                    "id": f"doc_{int(time.time())}_{idx}",
                                    "nombre_final": nombre_final,
                                    "bytes": res["bytes"],
                                    "fojas_orig": res["fojas_originales"],
                                    "fojas_final": res["fojas_conservadas"],
                                    "eliminadas": res["paginas_eliminadas"],
                                    "kb_orig": res["kb_orig"],
                                    "kb_final": res["kb_final"],
                                })
                                status.update(label=f"✅ Listo: {nombre_final}", state="complete", expanded=False)
                            except Exception as e:
                                status.update(label=f"❌ Error en {arch.name}", state="error", expanded=True)
                                st.error(f"Detalle: {e}")

                    if nuevos_resultados:
                        st.session_state.resultados_docs = nuevos_resultados + st.session_state.resultados_docs
                        st.rerun()

    # Zona persistente de descargas (no desaparece al hacer clic)
    if st.session_state.resultados_docs:
        st.divider()
        st.subheader("📥 Resultados listos para descargar (Sesión actual)")
        if len(st.session_state.resultados_docs) > 1:
            st.download_button(
                "📦 Descargar todo el lote (.ZIP)",
                data=crear_zip_resultados(st.session_state.resultados_docs),
                file_name=f"Folia_Documentos_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
                key="dl_zip_docs"
            )
        for r in st.session_state.resultados_docs:
            c1, c2 = st.columns([3, 1])
            with c1:
                info_elim = f" | Eliminadas: págs. {r['eliminadas']}" if r["eliminadas"] else " | 0 eliminadas"
                st.markdown(
                    f"**{r['nombre_final']}**  \n"
                    f"Páginas: {r['fojas_orig']} → {r['fojas_final']}{info_elim} | "
                    f"Peso: {r['kb_orig']:.0f} KB → {r['kb_final']:.0f} KB"
                )
            with c2:
                st.download_button("⬇️ Descargar PDF", data=r["bytes"], file_name=r["nombre_final"], mime="application/pdf", key=f"dl_{r['id']}")


# --- PESTAÑA B: EXPEDIENTES (INDEXACIÓN JERÁRQUICA 3 NIVELES) ---
with tab_expedientes:
    st.header("Saneamiento e Indexación Jerárquica (3 Niveles)")
    st.write("Aplica OCR, lee la foliatura real y genera marcadores navegables por actuación o capítulos.")

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        cliente_exp = st.text_input("Cliente / Asunto (para liquidación):", value="General", key="cli_exp")
        tipo_exp = st.radio(
            "Tipo de estructura:",
            ["Expediente judicial/arbitral (actuados y pruebas)", "Un solo documento largo (títulos y capítulos)"],
            key="tipo_exp"
        )
        modo_idx = "DOCUMENTO_UNICO" if "documento largo" in tipo_exp else "EXPEDIENTE"
    with col_e2:
        contexto_partes = st.text_input(
            "Contexto simple de partes (ayuda a la IA a nombrar con precisión):",
            placeholder="Ej: Alba Sosa Vs. Mario Bruun - Divorcio ante Juez de Familia 12º",
            key="ctx_partes"
        )

    st.divider()
    archivos_exp = st.file_uploader("Arrastra tomos o documentos largos (PDF)", type=["pdf"], accept_multiple_files=True, key="up_exp")

    if archivos_exp:
        validos_exp = []
        total_pags_exp = 0
        for arch in archivos_exp:
            ok, msg, num_p = validar_pdf(arch.getvalue(), arch.name)
            if ok:
                validos_exp.append((arch, num_p))
                total_pags_exp += num_p
            else:
                st.error(f"❌ {msg}")

        if validos_exp:
            cols_prev_e = st.columns(min(len(validos_exp), 4))
            for idx, (arch, num_p) in enumerate(validos_exp):
                with cols_prev_e[idx % 4]:
                    mini = generar_miniatura(arch.getvalue())
                    if mini:
                        st.image(mini, caption=f"📚 {arch.name[:18]} ({num_p} págs.)", use_container_width=True)

            if st.button(f"🚀 Procesar e Indexar ({total_pags_exp} fojas est.)", type="primary", key="btn_proc_exp"):
                if st.session_state.creditos < total_pags_exp:
                    st.error(f"❌ Saldo insuficiente. Necesitas ~{total_pags_exp} fojas y tienes {st.session_state.creditos}.")
                else:
                    nuevos_exp = []
                    for idx, (arch, _) in enumerate(validos_exp):
                        with st.status(f"Estructurando: {arch.name}", expanded=True) as status_exp:
                            try:
                                st.write("⚙️ Aplicando OCR y compresión en Adobe...")
                                res = procesar_pdf_adobe(arch.getvalue(), opt_limpiar, nivel_compresion)

                                st.write("🤖 Analizando foliatura y construyendo índice jerárquico (3 niveles)...")
                                bytes_idx, marcadores = indexar_jerarquico_ia(res["bytes"], modo_idx, contexto_partes)

                                if len(marcadores) == 0:
                                    st.warning("⚠️ El documento fue optimizado, pero la IA no detectó títulos o actuaciones para crear marcadores.")

                                nombre_final = arch.name.replace(".pdf", "_Indexado.pdf")
                                st.session_state.creditos -= res["fojas_conservadas"]
                                st.session_state.historial_consumo.append({
                                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "Cliente / Asunto": cliente_exp.strip() or "General",
                                    "Archivo": nombre_final,
                                    "Fojas": res["fojas_conservadas"],
                                    "Tipo": "Expediente"
                                })
                                nuevos_exp.append({
                                    "id": f"exp_{int(time.time())}_{idx}",
                                    "nombre_final": nombre_final,
                                    "bytes": bytes_idx,
                                    "fojas_orig": res["fojas_originales"],
                                    "fojas_final": res["fojas_conservadas"],
                                    "eliminadas": res["paginas_eliminadas"],
                                    "marcadores": marcadores,
                                    "kb_orig": res["kb_orig"],
                                    "kb_final": len(bytes_idx) / 1024.0,
                                })
                                status_exp.update(
                                    label=f"✅ Indexado: {nombre_final} ({len(marcadores)} marcadores)",
                                    state="complete",
                                    expanded=False
                                )
                            except Exception as e:
                                status_exp.update(label=f"❌ Error en {arch.name}", state="error", expanded=True)
                                st.error(f"Detalle: {e}")

                    if nuevos_exp:
                        st.session_state.resultados_exp = nuevos_exp + st.session_state.resultados_exp
                        st.rerun()

    if st.session_state.resultados_exp:
        st.divider()
        st.subheader("📥 Expedientes indexados (Sesión actual)")
        if len(st.session_state.resultados_exp) > 1:
            st.download_button(
                "📦 Descargar todos los expedientes (.ZIP)",
                data=crear_zip_resultados(st.session_state.resultados_exp),
                file_name=f"Folia_Expedientes_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
                key="dl_zip_exp"
            )
        for r in st.session_state.resultados_exp:
            c1, c2 = st.columns([3, 1])
            with c1:
                info_elim = f" | Eliminadas: págs. {r['eliminadas']}" if r["eliminadas"] else " | 0 eliminadas"
                st.markdown(
                    f"**{r['nombre_final']}**  \n"
                    f"Páginas: {r['fojas_orig']} → {r['fojas_final']}{info_elim} | "
                    f"Marcadores: **{len(r['marcadores'])}** | "
                    f"Peso: {r['kb_orig']:.0f} KB → {r['kb_final']:.0f} KB"
                )
                if r["marcadores"]:
                    with st.expander(f"Ver índice generado ({len(r['marcadores'])} marcadores)"):
                        for nivel, titulo, pag in r["marcadores"]:
                            st.text(f"{'  ' * (nivel - 1)}• [N{nivel} | Pág. {pag}] {titulo}")
            with c2:
                st.download_button("⬇️ Descargar PDF", data=r["bytes"], file_name=r["nombre_final"], mime="application/pdf", key=f"dl_{r['id']}")


# --- PESTAÑA C: LIQUIDACIÓN ---
with tab_liquidacion:
    st.header("Liquidación de Gastos por Cliente / Asunto")
    tarifa_foja = st.number_input("Tarifa de refacturación por foja (USD):", min_value=0.001, max_value=1.000, value=0.010, step=0.002, format="%.3f")

    if st.session_state.historial_consumo:
        st.dataframe(st.session_state.historial_consumo, use_container_width=True)
        total_fojas_hist = sum(x["Fojas"] for x in st.session_state.historial_consumo)
        st.metric(
            label="Total a Imputar a Clientes (USD)",
            value=f"${total_fojas_hist * tarifa_foja:.2f} USD",
            delta=f"{total_fojas_hist} fojas procesadas"
        )
    else:
        st.info("Aún no se han procesado documentos en esta sesión.")