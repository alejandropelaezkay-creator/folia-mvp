import streamlit as st
import tempfile
import os
import time

try:
    import optimizar_y_renombrar as opt
    import indexador_expediente as indx
    MODO_REAL = True
except Exception as e:
    MODO_REAL = False
    st.error(f"Error interno cargando los motores: {e}")

# 1. CONFIGURACIÓN Y ESTILOS GLOBALES
st.set_page_config(page_title="Fol.ia | Infraestructura Legal", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #fbfcff; }
    h1, h2, h3 { color: #0f2537; font-family: 'Inter', sans-serif; font-weight: 700; }
    .hero-text { font-size: 1.15rem; color: #4a5568; margin-bottom: 2rem; }
    .stButton>button { background-color: #0f2537; color: white; border-radius: 6px; padding: 0.6rem 1.2rem; font-weight: 600; border: none; }
    .stButton>button:hover { background-color: #1a365d; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .metric-card { background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .zdr-badge { background-color: #c6f6d5; color: #22543d; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

# 2. GESTIÓN DE CRÉDITOS
if 'creditos' not in st.session_state:
    st.session_state.creditos = 2500

# 3. PANEL LATERAL (SIDEBAR DASHBOARD)
with st.sidebar:
    st.markdown("## ⚖️ Fol.ia")
    st.markdown("<span class='zdr-badge'>✓ Zero Data Retention</span>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    st.metric(label="Saldo Prepago", value=f"{st.session_state.creditos:,} fojas")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.caption("🔒 Tus documentos son procesados en memoria asíncrona y expurgados inmediatamente tras su descarga. No usamos tus expedientes para entrenar IA.")
    if not MODO_REAL:
        st.error("Modo Visual: Scripts de backend no detectados.")

# 4. ENCABEZADO Y PROPUESTA DE VALOR (HERO SECTION)
st.title("Automatización Documental Jurídica")
st.markdown("""
<div class='hero-text'>
Erradicamos el trabajo administrativo manual de tu despacho. Fol.ia purga fojas en blanco, comprime expedientes pesados mediante OCR, y utiliza Inteligencia Artificial para indexar actuados leyendo la foliatura manuscrita del juzgado. <b>Listos para subir a Ciudadanía Digital o el SINPLU.</b>
</div>
""", unsafe_allow_html=True)

# 5. ÁREA DE TRABAJO (TABS)
tab1, tab2 = st.tabs(["📄 Documentos Individuales", "📚 Expedientes"])

# --- MÓDULO 1: DOCUMENTOS INDIVIDUALES ---
with tab1:
    st.markdown("### Saneamiento y Renombrado Inteligente")
    st.write("Sube memoriales, contratos o poderes. El sistema los optimizará y aplicará reglas archivísticas estandarizadas para el nombre del archivo.")
    
    docs_subidos = st.file_uploader("Arrastra tus documentos PDF aquí", type="pdf", accept_multiple_files=True, key="docs")
    
    if docs_subidos and st.button("Procesar Documentos", type="primary", key="btn_docs"):
        for i, arch in enumerate(docs_subidos):
            # UX: Barra de progreso dinámica estilo SaaS
            with st.status(f"Procesando: {arch.name}", expanded=True) as status:
                try:
                    if MODO_REAL:
                        st.write("🔐 Autenticando motores de procesamiento...")
                        token_adobe = opt.obtener_token_adobe()
                        
                        st.write("🔍 Analizando contraste y purgando fojas en blanco...")
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in, \
                             tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_out:
                            tmp_in.write(arch.getvalue())
                            path_in, path_out = tmp_in.name, tmp_out.name
                        
                        st.write("⚙️ Aplicando OCR y compresión estructural...")
                        nuevo_nombre = opt.procesar_desde_web(path_in, path_out, token_adobe)
                        
                        st.write("🤖 Extrayendo taxonomía con Inteligencia Artificial...")
                        nombre_final = f"{nuevo_nombre}.pdf" if nuevo_nombre else f"{arch.name.replace('.pdf', '')}_Opt.pdf"
                        
                        with open(path_out, "rb") as f:
                            pdf_bytes = f.read()
                        
                        os.unlink(path_in)
                        os.unlink(path_out)
                    else:
                        # Simulador si no hay backend
                        st.write("🔍 Analizando fojas en blanco...")
                        time.sleep(1)
                        st.write("⚙️ Comprimiendo archivo...")
                        time.sleep(1)
                        nombre_final = f"{arch.name.replace('.pdf', '')}_Opt.pdf"
                        pdf_bytes = b"Bytes de prueba"
                    
                    # Cierre exitoso del componente visual
                    status.update(label=f"¡Documento optimizado: {nombre_final}!", state="complete", expanded=False)
                    st.session_state.creditos -= 15
                    
                    st.download_button(label=f"⬇️ Descargar archivo", data=pdf_bytes, file_name=nombre_final, mime="application/pdf", key=f"dl_doc_{i}")
                    
                except Exception as e:
                    status.update(label="Fallo en el procesamiento", state="error", expanded=True)
                    st.error(f"Error técnico: {str(e)}")

# --- MÓDULO 2: EXPEDIENTES MASIVOS ---
with tab2:
    st.markdown("### Indexación por Foliatura Manuscrita")
    st.write("Sube tomos completos devueltos por el juzgado. Fol.ia leerá los números manuscritos en la esquina superior derecha y creará un índice (marcadores) navegable por actuado procesal.")
    
    exp_subidos = st.file_uploader("Arrastra tus tomos o expedientes PDF", type="pdf", accept_multiple_files=True, key="exp")
    
    if exp_subidos and st.button("Indexar Expedientes", type="primary", key="btn_exp"):
        for i, arch in enumerate(exp_subidos):
            with st.status(f"Mapeando Expediente: {arch.name}", expanded=True) as status_exp:
                try:
                    if MODO_REAL:
                        st.write("🔐 Preparando infraestructura asíncrona...")
                        token_adobe = indx.obtener_token_adobe()
                        
                        st.write("🧹 Saneando y estabilizando el documento masivo...")
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in, \
                             tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_out:
                            tmp_in.write(arch.getvalue())
                            path_in, path_out = tmp_in.name, tmp_out.name
                        
                        st.write("👁️ Gemini Vision leyendo foliatura manuscrita e inyectando marcadores...")
                        indx.indexar_desde_web(path_in, path_out, token_adobe)
                        
                        nombre_final = arch.name.replace('.pdf', '_Indexado.pdf')
                        with open(path_out, "rb") as f:
                            pdf_bytes = f.read()
                            
                        os.unlink(path_in)
                        os.unlink(path_out)
                    else:
                        st.write("👁️ Simulando lectura de foliatura...")
                        time.sleep(2)
                        nombre_final = arch.name.replace('.pdf', '_Indexado.pdf')
                        pdf_bytes = b"Bytes de prueba"
                        
                    status_exp.update(label="¡Expediente indexado con éxito!", state="complete", expanded=False)
                    st.session_state.creditos -= 85
                    
                    st.download_button(label=f"⬇️ Descargar Expediente", data=pdf_bytes, file_name=nombre_final, mime="application/pdf", key=f"dl_exp_{i}")
                    
                except Exception as e:
                    status_exp.update(label="Fallo en la indexación", state="error", expanded=True)
                    st.error(f"Error técnico: {str(e)}")
