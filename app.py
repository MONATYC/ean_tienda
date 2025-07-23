# app.py (Main Application File)

import streamlit as st
import ean_creator  # Lógica de EAN Creator
import unique_codes  # Lógica de Códigos Únicos

st.set_page_config(
    page_title="Gestor EAN - MONA",
    layout="wide",
    initial_sidebar_state="expanded",
)

page_ean_creator = st.Page(
    ean_creator.main,
    title="Creador de Códigos EAN Tienda",
    default=True,
)


# Envolvemos la función main de unique_codes en un wrapper con nombre único
def unique_codes_wrapper():
    return unique_codes.main()


unique_codes_wrapper.__name__ = "unique_codes_ui"

page_unique_codes = st.Page(
    unique_codes_wrapper,
    title="Códigos Únicos para Entradas",
)

pg = st.navigation([page_ean_creator, page_unique_codes])
pg.run()
