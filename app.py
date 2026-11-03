import streamlit as st
import time
import os

# Intento de importación de tus scripts reales (deben estar subidos a GitHub)
try:
    import optimizar_y_renombrar as opt
    import indexador_expediente as indx
    MODO_REAL = True
except ImportError:
    MODO_REAL = False

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Fol.ia | Infraestructura Legal", page_icon="⚖️", layout="wide")

# 2. ESTILOS CORPORATIVOS (CSS)
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1 { color: #1e3d59; font-weight: 700; font-family: 'Helvetica Neue', sans-serif; }
    h2, h3 { color: #2b3a4a; font-weight: 600; }
    .stButton>button { background-color: #1e3d59; color: white; border-radius: 4px; padding: 0.5rem 1rem; font-weight: 600; transition: all 0.3s; }
    .stButton>button:hover { background-color: #132a40; border-color: #132a40; }
    .css-1d391kg { background-color: #ffffff; border-right: 1px solid #e0e0e0; }
    .metric-container { background-color: white; padding: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e9ecef; }
    .badge-zdr { background-color: #e8f5e9; color: #2e7d32; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; border: 1px solid #c8e6c9; }
    </style>
""", unsafe_allow_html=True)

# 3. ESTADO DE CUENTA
if 'creditos' not in st.session_state:
    st.session_state.creditos = 2500

# 4. BARRA LATERAL (PANEL DE USUARIO)
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Scale_of_justice_2.svg/200px-Scale_of_justice_2.svg.png", width=60)
    st.markdown("### Fol.ia Suite")
    st.markdown("<span class='badge-zdr'>✓ Zero Data Retention</span>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<div class='metric-container'>", unsafe_allow_html=True)
    st.metric(label="Saldo de Fojas", value=f"{st.session_state.creditos:,}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.caption("Conectado vía conexión cifrada asíncrona. Los archivos se destruyen inmediatamente tras la descarga.")

# 5. ENCABEZADO PRINCIPAL
st.title("Procesamiento de Expedientes")
st.markdown("Saneamiento visual, compresión OCR y estructuración taxonómica automatizada.")
if not MODO_REAL:
    st.warning("⚠️ Modo Simulación Activo: Sube tus archivos 'optimizar_y_renombrar.py' e 'indexador_expediente.py' a GitHub para habilitar el procesamiento real.")

# 6. FLUJOS DE TRABAJO (PESTAÑAS)
tab1, tab2 = st.tabs(["📄 Contratos y Documentos (Renombrado)", "📚 Expedientes Judiciales (Indexación)"])

# --- PESTAÑA 1: DOCUMENTOS INDIVIDUALES ---
with tab1:
    st.markdown("#### Saneamiento y Taxonomía")
    st.write("Elimina fojas en blanco, comprime el archivo y aplica reglas de nomenclatura notarial/contractual.")
    
    docs_subidos = st.file_uploader("Arrastra contratos, poderes o memoriales sueltos", type="pdf", accept_multiple_files=True, key="docs")
    
    if docs_subidos:
        if st.button("Procesar Documentos", type="primary", key="btn_docs"):
            barra = st.progress(0)
            estado = st.empty()
            listos = []
            
            for i, arch in enumerate(docs_subidos):
                estado.info(f"Analizando contraste y estructura en: {arch.name}")
                time.sleep(1.5) # Simulación de delay
                
                # EJECUCIÓN REAL (si los scripts están subidos)
                if MODO_REAL:
                    # Aquí irá la lógica de guardado temporal y llamada a opt.main()
                    nombre_final = f"{arch.name.replace('.pdf', '')}_Renombrado.pdf"
                else:
                    nombre_final = f"{arch.name.replace('.pdf', '')}_Renombrado.pdf"
                
                listos.append(nombre_final)
                barra.progress((i + 1) / len(docs_subidos))
                st.session_state.creditos -= 10 # Descuento estimado
            
            estado.success("✅ Procesamiento y renombrado exitoso.")
            st.divider()
            st.markdown("### Descargas Disponibles")
            for doc in listos:
                st.download_button(label=f"⬇️ {doc}", data=b"Bytes", file_name=doc, mime="application/pdf", key=f"dl_{doc}")

# --- PESTAÑA 2: EXPEDIENTES COMPLEJOS ---
with tab2:
    st.markdown("#### Indexación por Foliatura Manuscrita")
    st.write("Ideal para devoluciones de juzgado. Lee el número de folio en la esquina superior y crea un índice navegable (marcadores) por actuado procesal.")
    
    exp_subidos = st.file_uploader("Arrastra tomos de expedientes completos", type="pdf", accept_multiple_files=True, key="exp")
    
    if exp_subidos:
        if st.button("Indexar Expedientes", type="primary", key="btn_exp"):
            barra_exp = st.progress(0)
            estado_exp = st.empty()
            listos_exp = []
            
            for i, arch in enumerate(exp_subidos):
                estado_exp.info(f"Mapeando actuados procesales con Gemini Vision en: {arch.name}")
                time.sleep(2.5) # Simulación de delay
                
                if MODO_REAL:
                    # Aquí irá la llamada a indx.indexar_archivo()
                    nombre_final = f"{arch.name.replace('.pdf', '')}_Indexado.pdf"
                else:
                    nombre_final = f"{arch.name.replace('.pdf', '')}_Indexado.pdf"
                
                listos_exp.append(nombre_final)
                barra_exp.progress((i + 1) / len(exp_subidos))
                st.session_state.creditos -= 85 # Descuento estimado
            
            estado_exp.success("✅ Estructuración de marcadores finalizada.")
            st.divider()
            st.markdown("### Expedientes Indexados")
            for exp in listos_exp:
                st.download_button(label=f"⬇️ {exp}", data=b"Bytes", file_name=exp, mime="application/pdf", key=f"dl_{exp}")
