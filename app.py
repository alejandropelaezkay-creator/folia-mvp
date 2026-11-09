import io
import os
import re
import zipfile
import shutil
import tempfile
from pathlib import Path
import streamlit as st
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from google import genai
from google.genai import types

# --- CONEXIÓN SEGURA A MOTORES (VÍA SECRETS) ---
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

try:
    import optimizar_y_renombrar as opt
    MODO_REAL = True
except Exception as e:
    MODO_REAL = False
    ERROR_MSJ = str(e)

# 1. CONFIGURACIÓN Y ESTILOS
st.set_page_config(page_title="Fol.ia | Suite Legal de Expedientes", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .metric-card { background-color: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 5px solid #1a365d; margin-bottom: 12px; }
    .guia-nomenclatura { background-color: #f1f3f5; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 0.9em; color: #495057; }
</style>
""", unsafe_allow_html=True)

if "creditos" not in st.session_state:
    st.session_state.creditos = 1500
if "historial_consumo" not in st.session_state:
    st.session_state.historial_consumo = []

# 2. MOTORES CLOUD (ADOBE OCR + GEMINI IA)
def procesar_expediente_nube(pdf_bytes, token_adobe, prefijo_marcador=None, aplicar_limpieza=True):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_in, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_temp, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t_out:
         
        t_in.write(pdf_bytes)
        path_in = Path(t_in.name)
        path_temp = Path(t_temp.name)
        path_out = Path(t_out.name)
        
    try:
        reader_orig = PdfReader(path_in)
        fojas_originales = len(reader_orig.pages)
        
        if aplicar_limpieza:
            opt.limpiar_paginas_blanco(path_in, path_temp)
        else:
            shutil.copy(path_in, path_temp)
            
        # OCR en Adobe
        opt.procesar_bloque_adobe(str(path_temp), str(path_out), token_adobe)
        
        # RECONSTRUCCIÓN: Repara fuentes corruptas de CamScanner/Adobe y añade marcadores
        reader_final = PdfReader(path_out)
        fojas_conservadas = len(reader_final.pages)
        
        writer = PdfWriter()
        writer.append_pages_from_reader(reader_final)
        
        if prefijo_marcador:
            for i in range(fojas_conservadas):
                writer.add_outline_item(f"{prefijo_marcador} {i+1}", i)
                
        with open(path_out, "wb") as f:
            writer.write(f)
            
        with open(path_out, "rb") as f:
            bytes_finales = f.read()
        
        return {
            "bytes": bytes_finales,
            "fojas_originales": fojas_originales,
            "fojas_conservadas": fojas_conservadas,
            "fojas_eliminadas": fojas_originales - fojas_conservadas,
            "tamano_orig_kb": len(pdf_bytes) / 1024,
            "tamano_final_kb": len(bytes_finales) / 1024
        }
    finally:
        for p in [path_in, path_temp, path_out]:
            if p.exists(): p.unlink()

def obtener_nombre_ia(pdf_bytes, regla_prompt):
    try:
        # pypdfium2 ignora errores de fuente y fuerza la extracción de texto
        pdf = pdfium.PdfDocument(pdf_bytes)
        texto_extraido = []
        for i in range(min(4, len(pdf))):
            texto_extraido.append(pdf[i].get_textpage().get_text_range()[:1500])
        texto = "".join(texto_extraido)
        pdf.close()
        
        if len(texto.strip()) < 15:
            return "ERROR_TEXTO_ILEGIBLE"
            
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        prompt = f"Regla de nomenclatura estricta a seguir: {regla_prompt}\n\nAplica esta regla al siguiente texto documental y devuelve SOLO el nombre del archivo resultante sin extensión ni explicaciones:\n\n{texto}"
        
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        if res.text:
            limpio = res.text.strip().replace("\n", "")
            return re.sub(r'[\\/*?:"<>|]', '-', limpio)[:120]
        return "ERROR_RESPUESTA_VACIA"
    except Exception as e:
        return f"ERROR_IA: {str(e)}"

# 3. BARRA LATERAL
with st.sidebar:
    try:
        st.image("Logo.jpg", use_container_width=True)
    except:
        st.title("⚖️ Fol.ia")
        
    st.caption("Plataforma SaaS de Optimización Legal")
    st.metric(label="Bolsa de Créditos (Fojas)", value=f"{st.session_state.creditos:,} fojas")
    
    with st.expander("💳 Recargar Créditos / Tarifas"):
        st.write("• **Litigio:** 2,500 fojas — $25 USD")
        st.write("• **Corporativo:** 10,000 fojas — $80 USD")
        if st.button("Simular Recarga +1,000 fojas"):
            st.session_state.creditos += 1000
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Configuración Global")
    opt_limpiar = st.checkbox("Depurar fojas en blanco", value=True, help="Remueve fojas escaneadas vacías en ambos flujos.")
    
    if not MODO_REAL:
        st.error(f"Falla de conexión backend: {ERROR_MSJ}")

# 4. ÁREA DE TRABAJO
tab_docs, tab_expedientes, tab_liquidacion = st.tabs([
    "📄 A. Documentos Individuales", 
    "📚 B. Expedientes (Marcadores)", 
    "📊 Liquidación"
])

# --- OPCIÓN A: DOCUMENTOS ---
with tab_docs:
    st.header("Saneamiento y Renombrado Automático")
    st.write("Ideal para memoriales y contratos. Se aplicará OCR, se purgarán blancos y la IA aplicará tu regla.")
    
    tipo_regla = st.radio("Selecciona la regla de nomenclatura:", ["Predeterminada del sistema", "Personalizada"], horizontal=True)
    
    if tipo_regla == "Predeterminada del sistema":
        st.markdown("""
        <div class="guia-nomenclatura">
        <b>Guía de Nomenclatura Estándar Fol.ia:</b><br>
        • Notariales: YYYY-MM-DD inst. [Nro] [Detalle]<br>
        • Judiciales: YYYY-MM-DD [Fs. Rango] [Nombre], [Acción]<br>
        • Contratos: YYYY-MM-DD [ENTIDAD] CONTR [Tipo] [Contraparte]<br>
        </div>
        """, unsafe_allow_html=True)
        regla_prompt = "Usa el estándar: YYYY-MM-DD [Nombre], [Acción/Detalle]"
    else:
        regla_prompt = st.text_input("✨ Instrucciones de Nomenclatura (Funciona con Inteligencia Artificial):", placeholder="Ej: Extraer la fecha y el nombre del cliente en mayúsculas...")
    
    st.divider()
    archivos_docs = st.file_uploader("Arrastra documentos individuales", type=["pdf"], accept_multiple_files=True, key="up_docs")
    
    if archivos_docs and st.button("🚀 Procesar y Renombrar", type="primary"):
        for idx, arch in enumerate(archivos_docs):
            with st.status(f"Procesando: {arch.name}", expanded=True) as status:
                if MODO_REAL:
                    try:
                        st.write("🔐 Conectando con motores de procesamiento...")
                        token_adobe = opt.obtener_token_adobe()
                        
                        st.write("⚙️ Limpiando fojas, reestructurando fuentes y aplicando OCR...")
                        res = procesar_expediente_nube(arch.getvalue(), token_adobe, aplicar_limpieza=opt_limpiar)
                        
                        st.write("🤖 Analizando texto con IA...")
                        nombre_ia = obtener_nombre_ia(res["bytes"], regla_prompt)
                        
                        if nombre_ia and not nombre_ia.startswith("ERROR"):
                            nombre_final = f"{nombre_ia}.pdf"
                        else:
                            st.warning(f"⚠️ Renombrado omitido ({nombre_ia}). Usando nombre genérico.")
                            nombre_final = f"{arch.name.replace('.pdf', '')}_FolIA.pdf"
                        
                        st.session_state.creditos -= res["fojas_conservadas"]
                        st.session_state.historial_consumo.append({"Expediente": nombre_final, "Fojas Válidas": res["fojas_conservadas"], "Créditos": res["fojas_conservadas"], "Tipo": "Documento"})
                        
                        status.update(label=f"¡Optimizado: {nombre_final}!", state="complete", expanded=False)
                        st.download_button("⬇️ Descargar", data=res["bytes"], file_name=nombre_final, mime="application/pdf", key=f"dl_doc_{idx}")
                    except Exception as e:
                        status.update(label="Fallo en la nube", state="error", expanded=True)
                        st.error(f"Error técnico: {e}")

# --- OPCIÓN B: EXPEDIENTES ---
with tab_expedientes:
    st.header("Saneamiento e Indexación de Expedientes")
    st.write("Se depurarán blancos, se aplicará OCR pesado y se insertarán marcadores jerárquicos (índice navegable).")
    
    prefijo = st.text_input("Prefijo para los marcadores (opcional):", value="Foja")
    archivos_exp = st.file_uploader("Arrastra tomos de expedientes", type=["pdf"], accept_multiple_files=True, key="up_exp")
    
    if archivos_exp and st.button("🚀 Procesar e Indexar", type="primary"):
        for idx, arch in enumerate(archivos_exp):
            with st.status(f"Estructurando: {arch.name}", expanded=True) as status_exp:
                if MODO_REAL:
                    try:
                        st.write("🔐 Conectando con motores de procesamiento...")
                        token_adobe = opt.obtener_token_adobe()
                        
                        st.write("⚙️ Comprimiendo e inyectando marcadores...")
                        res = procesar_expediente_nube(arch.getvalue(), token_adobe, prefijo_marcador=prefijo, aplicar_limpieza=opt_limpiar)
                        nombre_final = arch.name.replace(".pdf", "_Indexado.pdf")
                        
                        st.session_state.creditos -= res["fojas_conservadas"]
                        st.session_state.historial_consumo.append({"Expediente": nombre_final, "Fojas Válidas": res["fojas_conservadas"], "Créditos": res["fojas_conservadas"], "Tipo": "Expediente"})
                        
                        status_exp.update(label="¡Expediente indexado con éxito!", state="complete", expanded=False)
                        st.download_button("⬇️ Descargar", data=res["bytes"], file_name=nombre_final, mime="application/pdf", key=f"dl_exp_{idx}")
                    except Exception as e:
                        status_exp.update(label="Fallo en la indexación", state="error", expanded=True)
                        st.error(f"Error técnico: {e}")

# --- LIQUIDACIÓN ---
with tab_liquidacion:
    st.header("Liquidación de Gastos para Clientes")
    if st.session_state.historial_consumo:
        st.dataframe(st.session_state.historial_consumo, use_container_width=True)
        total_fojas_hist = sum(x["Fojas Válidas"] for x in st.session_state.historial_consumo)
        st.metric(label="Total a Imputar a Clientes (Referencia USD)", value=f"${total_fojas_hist * 0.01:.2f} USD", delta=f"{total_fojas_hist} fojas imputables")
    else:
        st.info("Aún no se han procesado documentos.")