import streamlit as st
import tempfile
import os
import time
from pathlib import Path

# Importar los motores de procesamiento
try:
    import optimizar_y_renombrar as opt
    import indexador_expediente as indx
    MODO_REAL = True
except ImportError as e:
    MODO_REAL = False

st.set_page_config(page_title="Fol.ia | Infraestructura Legal", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1 { color: #1e3d59; font-weight: 700; font-family: 'Helvetica Neue', sans-serif; }
    .stButton>button { background-color: #1e3d59; color: white; border-radius: 4px; padding: 0.5rem 1rem; font-weight: 600; }
    .stButton>button:hover { background-color: #132a40; }
    .metric-container { background-color: white; padding: 1rem; border-radius: 8px; border: 1px solid #e9ecef; }
    .badge-zdr { background-color: #e8f5e9; color: #2e7d32; padding: 4px 8px; border-radius: 4px; font-weight: bold; border: 1px solid #c8e6c9; }
    </style>
""", unsafe_allow_html=True)

if 'creditos' not in st.session_state:
    st.session_state.creditos = 2500

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Scale_of_justice_2.svg/200px-Scale_of_justice_2.svg.png", width=60)
    st.markdown("### Fol.ia Suite")
    st.markdown("<span class='badge-zdr'>✓ Zero Data Retention</span>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<div class='metric-container'>", unsafe_allow_html=True)
    st.metric(label="Saldo de Fojas", value=f"{st.session_state.creditos:,}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.caption("Conectado vía conexión cifrada asíncrona. Los archivos se destruyen tras la descarga.")

st.title("Procesamiento de Expedientes")
if not MODO_REAL:
    st.error("⚠️ Faltan los scripts de procesamiento en GitHub.")

tab1, tab2 = st.tabs(["📄 Contratos (Renombrado)", "📚 Expedientes Judiciales (Indexación)"])

# PESTAÑA 1: CONTRATOS Y MEMORIALES
with tab1:
    docs_subidos = st.file_uploader("Arrastra contratos, poderes o memoriales sueltos", type="pdf", accept_multiple_files=True, key="docs")
    if docs_subidos and st.button("Procesar Documentos", type="primary", key="btn_docs"):
        if MODO_REAL:
            try:
                token_adobe = opt.obtener_token_adobe()
                barra = st.progress(0)
                estado = st.empty()
                
                for i, arch in enumerate(docs_subidos):
                    estado.info(f"Procesando y renombrando: {arch.name}")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in, \
                         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_out:
                        tmp_in.write(arch.getvalue())
                        path_in, path_out = tmp_in.name, tmp_out.name
                    
                    nuevo_nombre = opt.procesar_desde_web(path_in, path_out, token_adobe)
                    nombre_final = f"{nuevo_nombre}.pdf" if nuevo_nombre else f"{arch.name.replace('.pdf', '')}_Opt.pdf"
                    
                    with open(path_out, "rb") as f:
                        pdf_bytes = f.read()
                        
                    st.download_button(label=f"⬇️ Descargar {nombre_final}", data=pdf_bytes, file_name=nombre_final, mime="application/pdf", key=f"dl_{i}")
                    
                    os.unlink(path_in)
                    os.unlink(path_out)
                    st.session_state.creditos -= 15
                    barra.progress((i + 1) / len(docs_subidos))
                estado.success("✅ Procesamiento completado.")
            except Exception as e:
                st.error(f"Error en el servidor: {str(e)}")

# PESTAÑA 2: EXPEDIENTES
with tab2:
    exp_subidos = st.file_uploader("Arrastra tomos de expedientes completos", type="pdf", accept_multiple_files=True, key="exp")
    if exp_subidos and st.button("Indexar Expedientes", type="primary", key="btn_exp"):
        if MODO_REAL:
            try:
                token_adobe = indx.obtener_token_adobe()
                barra_exp = st.progress(0)
                estado_exp = st.empty()
                
                for i, arch in enumerate(exp_subidos):
                    estado_exp.info(f"Mapeando foliatura en: {arch.name}")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in, \
                         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_out:
                        tmp_in.write(arch.getvalue())
                        path_in, path_out = tmp_in.name, tmp_out.name
                    
                    indx.indexar_desde_web(path_in, path_out, token_adobe)
                    nombre_final = arch.name.replace('.pdf', '_Indexado.pdf')
                    
                    with open(path_out, "rb") as f:
                        pdf_bytes = f.read()
                        
                    st.download_button(label=f"⬇️ Descargar {nombre_final}", data=pdf_bytes, file_name=nombre_final, mime="application/pdf", key=f"dl_exp_{i}")
                    
                    os.unlink(path_in)
                    os.unlink(path_out)
                    st.session_state.creditos -= 85
                    barra_exp.progress((i + 1) / len(exp_subidos))
                estado_exp.success("✅ Estructuración finalizada.")
            except Exception as e:
                st.error(f"Error en el servidor: {str(e)}")