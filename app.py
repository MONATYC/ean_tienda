import streamlit as st
import pandas as pd
import barcode
from barcode.ean import IllegalCharacterError, NumberOfDigitsError, _ean
from barcode.base import Barcode
from barcode.writer import ImageWriter


class EAN13NoChecksum(Barcode):
    """Barcode class that keeps the provided 13 digits without recalculating the checksum."""

    name = "EAN13-NoChecksum"
    digits = 13

    def __init__(self, ean: str, writer=None, guardbar: bool = False) -> None:
        if not ean.isdigit():
            raise IllegalCharacterError("EAN code can only contain numbers.")
        if len(ean) != self.digits:
            raise NumberOfDigitsError(
                f"EAN must have {self.digits} digits, not {len(ean)}."
            )
        self.ean = ean
        self.guardbar = guardbar
        if guardbar:
            self.EDGE = _ean.EDGE.replace("1", "G")
            self.MIDDLE = _ean.MIDDLE.replace("1", "G")
        else:
            self.EDGE = _ean.EDGE
            self.MIDDLE = _ean.MIDDLE
        self.writer = writer or ImageWriter()

    def get_fullcode(self) -> str:
        if self.guardbar:
            return self.ean[0] + " " + self.ean[1:7] + " " + self.ean[7:] + " >"
        return self.ean

    def build(self):
        code = self.EDGE[:]
        pattern = _ean.LEFT_PATTERN[int(self.ean[0])]
        for i, number in enumerate(self.ean[1:7]):
            code += _ean.CODES[pattern[i]][int(number)]
        code += self.MIDDLE
        for number in self.ean[7:]:
            code += _ean.CODES["C"][int(number)]
        code += self.EDGE
        return [code]
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from io import BytesIO
import os
from datetime import datetime

# Configuración inicial
st.set_page_config(layout="wide", page_title="Gestor EAN - MONA")

# Estado de sesión
if "df_inventory" not in st.session_state:
    st.session_state.df_inventory = pd.DataFrame(columns=["Producto", "EAN"])
if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = None


# Función para generar EAN secuencial (MOVED UP)
def generate_next_ean(last_ean):
    """Generate the next sequential EAN-13 code."""

    # Ensure the incoming value is treated as a 13 digit string
    last_ean_str = str(int(float(last_ean))).zfill(13)

    prefix = last_ean_str[:8]  # Mantener los primeros 8 dígitos del prefijo
    numeric_part = int(last_ean_str[8:-1]) + 1  # Incrementar la secuencia
    new_base = f"{prefix}{numeric_part:05d}"  # Formato de 5 dígitos

    # Calcular dígito de control con la librería
    ean_cls = barcode.get_barcode_class("ean13")
    ean = ean_cls(new_base)
    return ean.get_fullcode()


# Función para generar PDF con ReportLab (MOVED UP)
def generate_labels_pdf(products):
    os.makedirs("outputs", exist_ok=True)
    pdf_path = "outputs/etiquetas.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    for idx, product_name in enumerate(products):
        ean_code = (
            st.session_state.df_inventory[
                st.session_state.df_inventory["Producto"] == product_name
            ]["EAN"].iloc[0]
        )
        try:
            EAN = EAN13NoChecksum(ean_code, writer=ImageWriter())
            buffer = BytesIO()
            EAN.write(buffer)
            buffer.seek(0)
            barcode_img = ImageReader(buffer)

            img_w = 80 * mm
            img_h = 30 * mm
            x = (width - img_w) / 2
            y = (height - img_h) / 2

            c.drawImage(barcode_img, x, y, width=img_w, height=img_h)
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(width / 2, y - 20, product_name)
            c.setFont("Helvetica", 10)
            c.drawCentredString(width / 2, y - 35, ean_code)
        except Exception as e:
            st.error(f"Error al generar código de barras para {ean_code}: {e}")
        if idx < len(products) - 1:
            c.showPage()

    c.save()
    st.success(f"PDF de etiquetas generado en: {pdf_path}")
    with open(pdf_path, "rb") as f:
        st.download_button(
            label="📥 Descargar PDF de Etiquetas",
            data=f.read(),
            file_name="etiquetas_MONA.pdf",
            mime="application/pdf",
        )


# Sección de carga de archivo Excel
st.header("1. Carga de inventario")
uploaded_file = st.file_uploader("Sube tu archivo Excel", type=["xlsx"])
if uploaded_file:
    try:
        # Read all columns as strings to avoid numeric conversion of EAN codes
        df = pd.read_excel(uploaded_file, sheet_name="Hoja1", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        # Renombrar columnas si es necesario para asegurar consistencia
        col_map = {}
        for col in df.columns:
            if col.lower() == "producto":
                col_map[col] = "Producto"
            elif col.lower() in ["ean", "EAN", "codigo ean-13"]:
                col_map[col] = "EAN"
        df = df.rename(columns=col_map)
        required_cols = {"Producto", "EAN"}
        if not required_cols.issubset(df.columns):
            raise ValueError(
                f"Columnas incorrectas. Se encontraron: {df.columns.tolist()}"
            )
        # Normalizar la columna EAN como cadena de 13 dígitos
        df["EAN"] = df["EAN"].astype(str).str.replace(".0", "", regex=False).str.zfill(13)
        st.session_state.df_inventory = df
        st.session_state.uploaded_filename = uploaded_file.name
        st.success("Inventario cargado correctamente")
        st.dataframe(df.head())
        st.caption("Se muestran solo las primeras 5 líneas")
    except Exception as e:
        st.error(
            f"Error al leer el archivo. Asegúrate de que contenga la hoja 'Hoja1' con columnas 'Producto' y 'EAN'. Detalle: {e}"
        )

# Formulario para nuevos productos
st.header("2. Añadir producto")
with st.form("new_product_form"):
    product_type = st.selectbox("Tipo de producto", ["Samarreta"])  # Expandible
    color = st.text_input("Color")
    size = st.selectbox("Talla", ["XS", "S", "M", "L", "XL"])
    product_name = f"{product_type} {color} - {size}"

    # Generar nuevo EAN
    if not st.session_state.df_inventory.empty:
        last_ean = st.session_state.df_inventory["EAN"].iloc[-1]
        new_ean = generate_next_ean(last_ean)
    else:
        new_ean = "8437000000001"  # Valor inicial por defecto

    submitted = st.form_submit_button("Añadir producto")
    if submitted:
        new_row = {
            "Producto": product_name,
            "EAN": new_ean,
        }
        st.session_state.df_inventory = pd.concat(
            [st.session_state.df_inventory, pd.DataFrame([new_row])], ignore_index=True
        )
        st.success(f"¡Añadido con éxito! Código EAN: {new_ean}")
        output = BytesIO()
        st.session_state.df_inventory.to_excel(output, index=False)
        output.seek(0)
        st.session_state.updated_excel = output.getvalue()
        st.success("Excel actualizado con el nuevo producto, recuerda descargarlo de nuevo.")

# Sección de selección de etiquetas
st.header("3. Selección de etiquetas")
selected_products_for_labels = st.multiselect(
    "Elige productos", st.session_state.df_inventory["Producto"].tolist()
)

if st.button("Generar etiquetas PDF"):
    if selected_products_for_labels:
        generate_labels_pdf(selected_products_for_labels)
    else:
        st.warning("Selecciona al menos un producto")

# Botón de descarga de Excel actualizado
if st.button("Descargar inventario actualizado"):
    output = BytesIO()
    st.session_state.df_inventory.to_excel(output, index=False)
    output.seek(0)
    name = st.session_state.uploaded_filename or "inventario.xlsx"
    base, ext = os.path.splitext(name)
    date_suffix = datetime.now().strftime("%Y%m%d")
    download_name = f"{base}_{date_suffix}{ext}"
    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
