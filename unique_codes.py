# unique_codes.py

import streamlit as st
import pandas as pd
import random
import string
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime
import os

# --- Constants ---
DEFAULT_FILENAME_BASE = "codigos_unicos_historial"
CODE_LENGTH = 8  # You can adjust the length of the generated codes here
# Page size for the generated PDF (width x height in mm)
ENVELOPE_SIZE = (148 * mm, 105 * mm)

# --- Session State Initialization for this page ---
if "df_unique_history" not in st.session_state:
    st.session_state.df_unique_history = pd.DataFrame(columns=["Codigo_Unico"])
if "uploaded_unique_filename" not in st.session_state:
    st.session_state.uploaded_unique_filename = None
if "newly_generated_codes" not in st.session_state:
    st.session_state.newly_generated_codes = []


def ensure_session_state():
    """Recreate essential session state keys on every run."""
    if "df_unique_history" not in st.session_state:
        st.session_state.df_unique_history = pd.DataFrame(columns=["Codigo_Unico"])
    if "uploaded_unique_filename" not in st.session_state:
        st.session_state.uploaded_unique_filename = None
    if "newly_generated_codes" not in st.session_state:
        st.session_state.newly_generated_codes = []


# --- Functions for Unique Code Generation ---


def generate_random_code(length=CODE_LENGTH):
    """Generates a random alphanumeric code of specified length."""
    characters = string.ascii_uppercase + string.digits
    # Ensure at least one letter and one digit for better uniqueness
    code = [random.choice(string.ascii_uppercase), random.choice(string.digits)]
    code.extend(random.choices(characters, k=length - 2))
    random.shuffle(code)  # Shuffle to avoid fixed pattern
    return "".join(code)


def generate_random_code_with_prefix(prefix, length=CODE_LENGTH):
    """
    Genera un código aleatorio con un prefijo fijo.
    El prefijo debe tener 4 caracteres o menos (solo letras y números, en mayúsculas).
    """
    characters = string.ascii_uppercase + string.digits
    remaining_length = length - len(prefix)
    if remaining_length < 0:
        raise ValueError("El prefijo supera la longitud permitida del código.")
    random_part = "".join(random.choices(characters, k=remaining_length))
    return prefix + random_part


def get_unique_codes(df_history, num_codes, manual_prefix=None, max_attempts=10000):
    """
    Genera una lista de códigos únicos que no estén presentes en el DataFrame de historial.
    Si manual_prefix se proporciona (no None), se utiliza para generar los códigos.
    """
    if df_history.empty:
        existing_codes = set()
    else:
        existing_codes = set(df_history["Codigo_Unico"].dropna().str.strip())

    new_codes = []
    attempts = 0
    while len(new_codes) < num_codes and attempts < max_attempts:
        if manual_prefix is not None:
            candidate = generate_random_code_with_prefix(manual_prefix, CODE_LENGTH)
        else:
            candidate = generate_random_code()
        if candidate not in existing_codes and candidate not in new_codes:
            new_codes.append(candidate)
            existing_codes.add(candidate)
        attempts += 1

    if len(new_codes) < num_codes:
        raise ValueError(
            f"No se pudieron generar {num_codes} códigos únicos después de {max_attempts} intentos. "
            "Considera aumentar la longitud del código o reducir la cantidad solicitada."
        )
    return new_codes


def get_updated_history_excel(df_history, new_codes):
    """
    Returns BytesIO object of the updated history Excel and the download filename.
    """
    # Create DataFrame for new codes
    df_new = pd.DataFrame({"Codigo_Unico": new_codes})
    # Append new codes to history
    df_updated = pd.concat([df_history, df_new], ignore_index=True)

    output = BytesIO()
    df_updated.to_excel(output, index=False)
    output.seek(0)

    base, ext = os.path.splitext(
        st.session_state.uploaded_unique_filename or f"{DEFAULT_FILENAME_BASE}.xlsx"
    )
    date_suffix = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )  # Include time for uniqueness
    download_name = f"{base}_actualizado_{date_suffix}{ext}"
    return output, download_name


def render_unique_codes_pdf(codes_list):
    """Genera un PDF con un código único por página."""
    if not codes_list:
        return None
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=ENVELOPE_SIZE)
    width, height = ENVELOPE_SIZE

    for code in codes_list:
        c.setFont("Helvetica-Bold", 14)
        # Posicionar el código: 160 mm desde la izquierda y 70 mm desde arriba
        x = 10 * mm
        y = 40 * mm
        c.drawString(x, y, code)
        c.showPage()  # Nueva página para cada código

    c.save()
    buffer.seek(0)
    return buffer


# --- Main Function for Navigation ---
def main():
    ensure_session_state()
    """Main function to be called by the Streamlit navigation."""
    st.header("Códigos Únicos para Entradas")

    # 1. Upload History
    st.subheader("1. Cargar Historial de Códigos")
    uploaded_unique_file = st.file_uploader(
        "Sube tu archivo Excel de historial", type=["xlsx"], key="unique_uploader"
    )

    if uploaded_unique_file and uploaded_unique_file.name != st.session_state.get(
        "uploaded_unique_filename"
    ):
        try:
            xl = pd.ExcelFile(uploaded_unique_file)
            first_sheet = xl.sheet_names[0]
            df = xl.parse(first_sheet, dtype=str)
            df.columns = [c.strip() for c in df.columns]

            # Attempt to find the correct column (case-insensitive)
            code_col = None
            for col in df.columns:
                if col.lower() in {"codigo_unico", "codigo unico", "codigo", "code"}:
                    code_col = col
                    break

            if code_col is None:
                # If no standard name found, assume the first column
                if len(df.columns) >= 1:
                    code_col = df.columns[0]
                    st.info(
                        f"No se encontró una columna con nombre reconocido. Se usará la primera columna '{code_col}'."
                    )

            if code_col is None:
                raise ValueError("El archivo debe contener al menos una columna.")

            df = df[[code_col]].rename(columns={code_col: "Codigo_Unico"})
            df["Codigo_Unico"] = df["Codigo_Unico"].astype(str).str.strip()

            st.session_state.df_unique_history = df.drop_duplicates(
                subset=["Codigo_Unico"]
            )
            st.session_state.uploaded_unique_filename = uploaded_unique_file.name
            st.session_state.newly_generated_codes = []  # Reset generated codes on new upload
            st.success("Historial de códigos cargado correctamente.")
            st.dataframe(st.session_state.df_unique_history.head())
            st.caption("Se muestran las primeras 5 filas del historial.")
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    # 2. Generate New Codes
    st.subheader("2. Generar Nuevos Códigos Únicos")
    if st.session_state.uploaded_unique_filename is None:
        st.warning("Primero debes cargar un archivo de historial en el paso 1.")
    else:
        num_codes_needed = st.number_input(
            "¿Cuántos códigos nuevos necesitas?",
            min_value=1,
            max_value=1000,
            step=1,
            value=1,
        )
        # Nuevo toggle para forzar prefijo manual
        use_manual_prefix = st.checkbox(
            "Forzar código manualmente (4 caracteres máximo, solo letras y números)",
        )
        manual_prefix = None
        if use_manual_prefix:
            manual_prefix_input = st.text_input(
                "Ingresa hasta 4 caracteres (solo letras y números)", max_chars=4
            )
            if manual_prefix_input:
                # Convertir a mayúsculas y validar sólo letras y números
                manual_prefix_input = manual_prefix_input.upper()
                if not manual_prefix_input.isalnum():
                    st.error("El prefijo debe contener solo letras y números.")
                else:
                    manual_prefix = manual_prefix_input

        if st.button("Generar Códigos"):
            if num_codes_needed <= 0:
                st.warning("Por favor, indica un número válido de códigos a generar.")
            elif use_manual_prefix and manual_prefix is None:
                st.error("Debes ingresar un prefijo válido.")
            else:
                try:
                    with st.spinner("Generando códigos únicos..."):
                        new_codes = get_unique_codes(
                            st.session_state.df_unique_history,
                            num_codes_needed,
                            manual_prefix=manual_prefix,
                        )
                        st.session_state.newly_generated_codes = new_codes
                        st.success(f"¡{len(new_codes)} códigos generados con éxito!")
                        st.write("Códigos generados:")
                        st.code("\n".join(new_codes))

                        # Proporcionar la descarga de Excel actualizada inmediatamente
                        excel_buffer, excel_filename = get_updated_history_excel(
                            st.session_state.df_unique_history, new_codes
                        )
                        st.download_button(
                            label="📥 Descargar Historial Actualizado (Excel)",
                            data=excel_buffer.getvalue(),
                            file_name=excel_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_updated_history",
                        )
                except ValueError as ve:
                    st.error(str(ve))
                except Exception as e:
                    st.error(f"Ocurrió un error inesperado: {e}")

    # 3. Download PDF
    st.subheader("3. Descargar PDF de Códigos")
    if not st.session_state.newly_generated_codes:
        st.info("Genera códigos primero para poder descargar el PDF.")
    else:
        pdf_buffer = render_unique_codes_pdf(st.session_state.newly_generated_codes)
        if pdf_buffer:
            st.download_button(
                label="📄 Generar PDF de Códigos",
                data=pdf_buffer.getvalue(),
                file_name="codigos_unicos_entradas.pdf",
                mime="application/pdf",
                key="download_unique_codes_pdf",
            )
        else:
            st.error("Error al generar el PDF.")


def unique_codes_main():
    st.title("Códigos Únicos para Entradas")
    st.write("Contenido para la página de códigos únicos.")
