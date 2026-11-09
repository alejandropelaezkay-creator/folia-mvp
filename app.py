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
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# GESTIÓN DE SESIÓN Y CRÉDITOS
# ---------------------------------------------------------
if "creditos" not in st.session_state:
    st.session_state.creditos = 1500  # Saldo inicial demostrativo

if "historial_consumo" not in st.session_state:
    st.session_state.historial_consumo = []

# ---------------------------------------------------------
# FUNCIONES NATIVAS DE PROCESAMIENTO DE EXPEDIENTES (PYPDF)
# ---------------------------------------------------------
def analizar_expediente(pdf_bytes: bytes):
    """Retorna número de fojas y tamaño original."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages), len(pdf_bytes)

def es_pagina_en_blanco(page, umbral_caracteres: int = 5) -> bool:
    """
    Detecta si una página carece de texto e imágenes sustanciales.
    Heurística: texto extraído menor al umbral y ausencia de XObjects (imágenes/dibujos).
    """
    texto = page.extract_text() or ""
    if len(texto.strip()) > umbral_caracteres:
        return False
    
    # Revisar presencia de imágenes incrustadas en recursos
    recursos = page.get("/Resources", {})
    xobjects = recursos.get("/XObject", {})
    if xobjects:
        return False
        
    return True

def procesar_expediente_completo(
    pdf_bytes: bytes,
    nombre_archivo: str,
    remover_blancos: bool,
    comprimir: bool,
    crear_marcadores: bool,
    prefijo_marcador: str = "Foja"
):
    """
    Ejecuta el pipeline completo de limpieza, indexación y compresión.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    fojas_originales = len(reader.pages)
    fojas_conservadas = 0
    fojas_eliminadas = 0

    # Pipeline de filtrado y copia
    for idx, page in enumerate(reader.pages):
        foja_num = idx + 1
        if remover_blancos and es_pagina_en_blanco(page):
            fojas_eliminadas += 1
            continue

        writer.add_page(page)
        fojas_conservadas += 1

        if crear_marcadores:
            # Crea un marcador jerárquico por cada foja válida procesada
            writer.add_outline_item(
                title=f"{prefijo_marcador} {fojas_conservadas} (Original: {foja_num})",
                page_number=fojas_conservadas - 1
            )

    # Optimización y compresión nativa
    if comprimir:
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects()

    buffer_salida = io.BytesIO()
    writer.write(buffer_salida)
    bytes_optimizados = buffer_salida.getvalue()

    return {
        "nombre_original": nombre_archivo,
        "bytes_resultado": bytes_optimizados,
        "fojas_originales": fojas_originales,
        "fojas_conservadas": fojas_conservadas,
        "fojas_eliminadas": fojas_eliminadas,
        "tamano_original_kb": len(pdf_bytes) / 1024,
        "tamano_final_kb": len(bytes_optimizados) / 1024
    }

# ---------------------------------------------------------
# BARRA LATERAL: CRÉDITOS Y CONFIGURACIÓN
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚖️ Fol.ia")
    st.caption("Plataforma SaaS de Optimización Legal")
    
    # Panel de Créditos
    st.metric(
        label="Bolsa de Créditos (Fojas)",
        value=f"{st.session_state.creditos:,} fojas"
    )
    
    with st.expander("💳 Recargar Créditos / Tarifas"):
        st.write("**Bolsas Disponibles:**")
        st.write("• **Litigio:** 2,500 fojas — $25 USD")
        st.write("• **Corporativo:** 10,000 fojas — $80 USD")
        if st.button("Simular Recarga +1,000 fojas"):
            st.session_state.creditos += 1000
            st.success("Recarga acreditada con éxito.")
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Configuración del Pipeline")
    
    opt_limpiar = st.checkbox("Depurar fojas en blanco", value=True, help="Detecta y remueve fojas escaneadas vacías.")
    opt_comprimir = st.checkbox("Comprimir flujos y objetos", value=True, help="Reduce peso para subida a sistemas judiciales.")
    opt_indexar = st.checkbox("Generar marcadores de fojas", value=True, help="Crea tabla de contenido estructurada para el expediente.")
    
    with st.expander("🛠️ Conectores de API (Avanzado)"):
        st.text_input("Adobe PDF Services Client ID", type="password", help="Para OCR en la nube de alta precisión.")
        st.text_input("Gemini API Key", type="password", help="Para renombrado semántico de actuados mediante IA.")

# ---------------------------------------------------------
# INTERFAZ PRINCIPAL
# ---------------------------------------------------------
tab_procesar, tab_liquidacion = st.tabs(["📄 Procesamiento de Expedientes", "📊 Rendición de Gastos"])

with tab_procesar:
    st.header("Carga y Preparación de Expedientes")
    st.write("Arrastra memoriales, pruebas documentales o cuadernos de prueba para optimizarlos para uso judicial e IA.")

    archivos = st.file_uploader(
        "Seleccionar expedientes en PDF",
        type=["pdf"],
        accept_multiple_files=True
    )

    if archivos:
        # Pre-evaluación de volumen
        total_fojas_estimadas = 0
        previews = []
        for arch in archivos:
            data = arch.getvalue()
            num_paginas, tamano = analizar_expediente(data)
            total_fojas_estimadas += num_paginas
            previews.append({"Archivo": arch.name, "Fojas": num_paginas, "Tamaño (KB)": round(tamano / 1024, 1)})

        col1, col2, col3 = st.columns(3)
        col1.metric("Expedientes a procesar", len(archivos))
        col2.metric("Fojas totales estimadas", f"{total_fojas_estimadas:,}")
        col3.metric("Consumo previsto", f"{total_fojas_estimadas:,} créditos")

        if total_fojas_estimadas > st.session_state.creditos:
            st.error("⚠️ Saldo insuficiente en tu bolsa de créditos. Recarga para continuar con el lote.")
        else:
            if st.button("🚀 Iniciar Procesamiento Legal", type="primary", use_container_width=True):
                barra = st.progress(0)
                status_txt = st.empty()
                resultados = []

                for idx, arch in enumerate(archivos):
                    status_txt.text(f"Procesando: {arch.name}...")
                    res = procesar_expediente_completo(
                        pdf_bytes=arch.getvalue(),
                        nombre_archivo=arch.name,
                        remover_blancos=opt_limpiar,
                        comprimir=opt_comprimir,
                        crear_marcadores=opt_indexar
                    )
                    
                    # Descontar créditos únicamente por fojas procesadas y conservadas
                    consumo_real = res["fojas_conservadas"]
                    st.session_state.creditos -= consumo_real
                    
                    # Registrar en libro de liquidación para el cliente
                    st.session_state.historial_consumo.append({
                        "Expediente": arch.name,
                        "Fojas Originales": res["fojas_originales"],
                        "Fojas Válidas": res["fojas_conservadas"],
                        "Fojas Depuradas": res["fojas_eliminadas"],
                        "Créditos Descontados": consumo_real,
                        "Ahorro Tamaño (%)": round((1 - (res["tamano_final_kb"] / res["tamano_original_kb"])) * 100, 1)
                    })
                    
                    resultados.append(res)
                    barra.progress((idx + 1) / len(archivos))

                status_txt.success("✅ Procesamiento finalizado con éxito.")
                st.markdown("### 📥 Descarga de Documentos Listos")

                # Generar archivo ZIP consolidado si son múltiples archivos
                if len(resultados) > 1:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for item in resultados:
                            nombre_descarga = item["nombre_original"].replace(".pdf", "_FolIA.pdf")
                            zip_file.writestr(nombre_descarga, item["bytes_resultado"])

                    st.download_button(
                        label="📦 Descargar Lote Completo (.ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="Expedientes_Optimizados_FolIA.zip",
                        mime="application/zip",
                        type="primary"
                    )

                # Descargas individuales
                for item in resultados:
                    c_info, c_btn = st.columns([3, 1])
                    nombre_descarga = item["nombre_original"].replace(".pdf", "_FolIA.pdf")
                    c_info.write(
                        f"**{nombre_descarga}** — "
                        f"{item['fojas_conservadas']} fojas "
                        f"({item['fojas_eliminadas']} fojas en blanco eliminadas) | "
                        f"De {item['tamano_original_kb']:.1f} KB a {item['tamano_final_kb']:.1f} KB"
                    )
                    c_btn.download_button(
                        label="⬇️ Descargar PDF",
                        data=item["bytes_resultado"],
                        file_name=nombre_descarga,
                        mime="application/pdf",
                        key=f"btn_{item['nombre_original']}"
                    )

with tab_liquidacion:
    st.header("Liquidación de Gastos para Clientes")
    st.write(
        "Este reporte te permite trasladar con precisión matemática el costo de procesamiento "
        "de expedientes a la factura o rendición de cuentas del cliente del litigio."
    )

    if st.session_state.historial_consumo:
        st.dataframe(st.session_state.historial_consumo, use_container_width=True)
        
        total_fojas_hist = sum(x["Fojas Válidas"] for x in st.session_state.historial_consumo)
        costo_unitario_foja = 0.01  # USD $0.01 por foja de referencia
        
        st.metric(
            label="Total a Imputar a Clientes (Referencia USD)",
            value=f"${total_fojas_hist * costo_unitario_foja:.2f} USD",
            delta=f"{total_fojas_hist} fojas imputables"
        )
    else:
        st.info("Aún no se han procesado expedientes en esta sesión de trabajo.")