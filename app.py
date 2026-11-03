import streamlit as st
import time

st.set_page_config(page_title="Fol.ia | MVP", page_icon="⚖️", layout="centered")

st.title("⚖️ Fol.ia")
st.markdown("Plataforma de saneamiento e indexación para infraestructura legal.")

if 'creditos' not in st.session_state:
    st.session_state.creditos = 2500

st.sidebar.metric(label="Créditos (Fojas)", value=st.session_state.creditos)
st.sidebar.markdown("---")

# Selector de Flujo de Trabajo
modo_procesamiento = st.radio(
    "**Selecciona el tipo de carga:**",
    [
        "📄 Documentos Individuales (Saneamiento visual y renombrado inteligente)",
        "📚 Expediente Completo (Saneamiento e indexación interna por foliatura)"
    ],
    index=0
)

archivos_subidos = st.file_uploader(
    "Arrastra tus archivos PDF aquí", 
    type="pdf", 
    accept_multiple_files=True
)

if archivos_subidos:
    if st.button("Procesar y Descontar Créditos", type="primary"):
        barra = st.progress(0)
        estado = st.empty()
        archivos_listos = []
        fojas_totales_procesadas = 0

        for i, archivo in enumerate(archivos_subidos):
            estado.text(f"Procesando: {archivo.name}...")
            
            # Simulamos el tiempo de procesamiento de tus scripts
            time.sleep(2)
            fojas_estimadas = 20 
            fojas_totales_procesadas += fojas_estimadas
            
            if "Documentos Individuales" in modo_procesamiento:
                # AQUÍ SE CONECTA: optimizar_y_renombrar.py
                # 1. limpiar_paginas_blanco()
                # 2. procesar_pdf_completo() (OCR)
                # 3. obtener_nombre_gemini()
                nombre_final = f"{archivo.name.replace('.pdf', '')}_Renombrado.pdf"
                
            else:
                # AQUÍ SE CONECTA: indexador_expediente.py
                # 1. limpiar_paginas_blanco()
                # 2. procesar_pdf_completo() (OCR para estabilizar)
                # 3. indexar_archivo() (Gemini Vision lee la foliatura y crea marcadores)
                nombre_final = f"{archivo.name.replace('.pdf', '')}_Indexado.pdf"
                
            archivos_listos.append(nombre_final)
            barra.progress((i + 1) / len(archivos_subidos))
            
        st.session_state.creditos -= fojas_totales_procesadas
        estado.success(f"✅ Proceso exitoso. Se descontaron {fojas_totales_procesadas} créditos.")
        
        st.subheader("Archivos Listos para Descarga")
        for nombre in archivos_listos:
            st.download_button(
                label=f"⬇️ Descargar {nombre}",
                data=b"Simulacion de bytes",
                file_name=nombre,
                mime="application/pdf"
            )
