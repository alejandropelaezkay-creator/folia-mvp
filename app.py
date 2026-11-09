import io
import os
import zipfile
import streamlit as st
from pypdf import PdfReader, PdfWriter

st.set_page_config(
    page_title="Fol.ia | Suite Legal de Expedientes",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados para interfaz legal corporativa
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #1a365d;
        margin-bottom: 12px;
    }
    .badge-success {
        background-color: #e6fffa;
        color: #234e52;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .guia-nomenclatura {
        background-color: #f1f3f5;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        font-size: 0.9em;
        color: #495057;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# GESTIÓN DE SESIÓN Y CRÉDITOS
# ---------------------------------------------------------
if "creditos" not in st.session_state:
    st.session_state.creditos = 1500

if "historial_consumo" not in st.session_state:
    st.session_state.historial_consumo = []

# ---------------------------------------------------------
# FUNCIONES NATIVAS DE PROCESAMIENTO
# ---------------------------------------------------------
def analizar_expediente(pdf_bytes: bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages), len(pdf_bytes)

def es_pagina_en_blanco(page, umbral_caracteres: int = 5) -> bool:
    texto = page.extract_text() or ""
    if len(texto.strip()) > umbral_caracteres:
        return False
    recursos = page.get("/Resources", {})
    xobjects = recursos.get("/XObject", {})
    if xobjects:
        return False
    return True

def procesar_pdf(
    pdf_bytes: bytes,
    nombre_archivo: str,
    remover_blancos: bool,
    comprimir: bool,
    crear_marcadores: bool = False,
    prefijo_marcador: str = "Foja",
    nuevo_nombre: str = None
):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    fojas_originales = len(reader.pages)
    fojas_conservadas = 0
    fojas_eliminadas = 0

    for idx, page in enumerate(reader.pages):
        foja_num = idx + 1
        if remover_blancos and es_pagina_en_blanco(page):
            fojas_eliminadas += 1
            continue

        writer.add_page(page)
        fojas_conservadas += 1

        if crear_marcadores:
            writer.add_outline_item(
                title=f"{prefijo_marcador} {fojas_conservadas} (Original: {foja_num})",
                page_number=fojas_conservadas - 1
            )

    if comprimir:
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects()

    buffer_salida = io.BytesIO()
    writer.write(buffer_salida)
    bytes_optimizados = buffer_salida.getvalue()
    
    nombre_final = nuevo_nombre if nuevo_nombre else nombre_archivo.replace(".pdf", "_FolIA.pdf")
    if not nombre_final.endswith(".pdf"):
        nombre_final += ".pdf"

    return {
        "nombre_descarga": nombre_final,
        "bytes_resultado": bytes_optimizados,
        "fojas_originales": fojas_originales,
        "fojas_conservadas": fojas_conservadas,
        "fojas_eliminadas": fojas_eliminadas,
        "tamano_original_kb": len(pdf_bytes) / 1024,
        "tamano_final_kb": len(bytes_optimizados) / 1024
    }

# ---------------------------------------------------------
# BARRA LATERAL
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚖️ Fol.ia")
    st.caption("Plataforma SaaS de Optimización Legal")
    
    st.metric(label="Bolsa de Créditos (Fojas)", value=f"{st.session_state.creditos:,} fojas")
    
    with st.expander("💳 Recargar Créditos / Tarifas"):
        st.write("**Bolsas Disponibles:**")
        st.write("• **Litigio:** 2,500 fojas — $25 USD")
        st.write("• **Corporativo:** 10,000 fojas — $80 USD")
        if st.button("Simular Recarga +1,000 fojas"):
            st.session_state.creditos += 1000
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Configuración Global")
    opt_limpiar = st.checkbox("Depurar fojas en blanco", value=True, help="Remueve fojas escaneadas vacías en ambos flujos.")
    opt_comprimir = st.checkbox("Comprimir tamaño", value=True, help="Reduce peso para subida a sistemas judiciales.")
    
    with st.expander("🤖 Motores IA (Opcional)"):
        st.text_input("Gemini API Key", type="password", help="Para renombrado automático inteligente.")

# ---------------------------------------------------------
# INTERFAZ PRINCIPAL (PESTAÑAS DE FLUJO)
# ---------------------------------------------------------
tab_docs, tab_expedientes, tab_liquidacion = st.tabs([
    "📄 A. Documentos Individuales", 
    "📚 B. Expedientes (Marcadores)", 
    "📊 Liquidación"
])

# --- OPCIÓN A: DOCUMENTOS INDIVIDUALES (RENOMBRADO) ---
with tab_docs:
    st.header("Saneamiento y Renombrado Automático")
    st.write("Ideal para memoriales, contratos o poderes sueltos. Se purgarán fojas en blanco, se optimizará el peso y se aplicará una regla de nomenclatura.")
    
    # Configuración de Nomenclatura
    st.subheader("Regla de Nomenclatura")
    tipo_regla = st.radio(
        "Selecciona cómo nombrar los archivos resultantes:",
        options=["Predeterminada del sistema", "Personalizada"],
        horizontal=True
    )
    
    regla_prompt = ""
    if tipo_regla == "Predeterminada del sistema":
        st.markdown("""
        <div class="guia-nomenclatura">
        <b>Guía de Nomenclatura Estándar Fol.ia:</b><br>
        • Notariales: YYYY-MM-DD inst. [Nro] [Detalle]<br>
        • Judiciales: YYYY-MM-DD [Fs. Rango] [Nombre], [Acción]<br>
        • Contratos: YYYY-MM-DD [ENTIDAD] CONTR [Tipo] [Contraparte]<br>
        <i>Ejemplo: 2026-10-15 Fs. 12-15 Perez, Contesta Demanda.pdf</i>
        </div>
        """, unsafe_allow_html=True)
        regla_prompt = "Usa el estándar legal: YYYY-MM-DD [Nombre], [Acción/Detalle]"
    else:
        regla_prompt = st.text_input(
            "Escribe tus instrucciones para la Inteligencia Artificial:", 
            placeholder="Ej: Solo pon la fecha y el nombre del cliente en mayúsculas..."
        )
    
    st.divider()
    archivos_docs = st.file_uploader("Arrastra documentos individuales", type=["pdf"], accept_multiple_files=True, key="up_docs")
    
    if archivos_docs and st.button("🚀 Procesar y Renombrar", type="primary", use_container_width=True):
        barra = st.progress(0)
        resultados_docs = []
        
        for idx, arch in enumerate(archivos_docs):
            # Aquí iría la llamada a Gemini usando 'regla_prompt'. Para este MVP nativo:
            nombre_simulado_ia = f"2026-11-09 {arch.name.replace('.pdf', '')} Optimizado"
            
            res = procesar_pdf(
                pdf_bytes=arch.getvalue(),
                nombre_archivo=arch.name,
                remover_blancos=opt_limpiar,
                comprimir=opt_comprimir,
                crear_marcadores=False,
                nuevo_nombre=nombre_simulado_ia
            )
            
            st.session_state.creditos -= res["fojas_conservadas"]
            st.session_state.historial_consumo.append({"Expediente": arch.name, "Fojas Válidas": res["fojas_conservadas"], "Créditos Descontados": res["fojas_conservadas"], "Tipo": "Documento"})
            resultados_docs.append(res)
            barra.progress((idx + 1) / len(archivos_docs))
            
        st.success("✅ Documentos procesados y renombrados.")
        for item in resultados_docs:
            c_info, c_btn = st.columns([3, 1])
            c_info.write(f"📄 **{item['nombre_descarga']}** ({item['fojas_conservadas']} fojas)")
            c_btn.download_button("⬇️ Descargar", data=item["bytes_resultado"], file_name=item["nombre_descarga"], mime="application/pdf", key=f"dl_{item['nombre_descarga']}")

# --- OPCIÓN B: EXPEDIENTES (MARCADORES) ---
with tab_expedientes:
    st.header("Saneamiento e Indexación de Expedientes")
    st.write("Ideal para cuadernos de prueba o tomos judiciales completos. Además de depurar y optimizar, insertará marcadores jerárquicos (índice navegable) para cada foja válida.")
    
    prefijo = st.text_input("Prefijo para los marcadores (opcional):", value="Foja", help="El texto que aparecerá antes del número en el panel de marcadores del PDF.")
    
    st.divider()
    archivos_exp = st.file_uploader("Arrastra tomos de expedientes", type=["pdf"], accept_multiple_files=True, key="up_exp")
    
    if archivos_exp and st.button("🚀 Procesar e Indexar", type="primary", use_container_width=True):
        barra = st.progress(0)
        resultados_exp = []
        
        for idx, arch in enumerate(archivos_exp):
            res = procesar_pdf(
                pdf_bytes=arch.getvalue(),
                nombre_archivo=arch.name,
                remover_blancos=opt_limpiar,
                comprimir=opt_comprimir,
                crear_marcadores=True,
                prefijo_marcador=prefijo
            )
            
            st.session_state.creditos -= res["fojas_conservadas"]
            st.session_state.historial_consumo.append({"Expediente": arch.name, "Fojas Válidas": res["fojas_conservadas"], "Créditos Descontados": res["fojas_conservadas"], "Tipo": "Expediente"})
            resultados_exp.append(res)
            barra.progress((idx + 1) / len(archivos_exp))
            
        st.success("✅ Expedientes indexados correctamente.")
        for item in resultados_exp:
            c_info, c_btn = st.columns([3, 1])
            c_info.write(f"📚