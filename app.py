import streamlit as st
import pandas as pd
import barcode
from barcode.ean import IllegalCharacterError, NumberOfDigitsError, _ean
from barcode.base import Barcode
from barcode.writer import ImageWriter

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from io import BytesIO
import os
from datetime import datetime


# ------------------------
#  CUSTOM BARCODE CLASS
# ------------------------
class EAN13NoChecksum(Barcode):
    """
    Barcode class that keeps the provided 13 digits unchanged.
    This lets us re-use already-calculated EANs coming from the inventory
    without forcing the python-barcode library to recalculate the checksum.
    """

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


# -----------------------------------
#  STREAMLIT CONFIG
# -----------------------------------
st.set_page_config(layout="wide", page_title="Gestor EAN - MONA")

# -----------------------------------
#  SESSION STATE INITIALIZATION
# -----------------------------------
if "df_inventory" not in st.session_state:
    st.session_state.df_inventory = pd.DataFrame(columns=["Producto", "EAN"])

if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = None

# -----------------------------------
#  FUNCTIONS
# -----------------------------------

COUNTRY_PREFIX = "84370000"  # 8-digits : 84 (ES) + 370000 (organización)


def _next_sequential_number(df: pd.DataFrame) -> int:
    """
    Devuelve el siguiente número secuencial (4 dígitos) mirando
    todos los EAN almacenados en el inventario.
    """
    if df.empty:
        return 1
    seq_max = (
        df["EAN"]
        .str.slice(8, 12)  # posiciones 9-12 => parte secuencial de 4 dígitos
        .astype(int)
        .max()
    )
    return seq_max + 1


def generate_next_ean(df: pd.DataFrame) -> str:
    """
    Genera el siguiente código EAN-13 disponible.
    Mantiene un prefijo de 8 dígitos y usa 4 para la parte secuencial.
    El 13º dígito (checksum) lo calcula automáticamente la librería.
    """
    seq = _next_sequential_number(df)
    if seq > 9999:
        raise ValueError(
            "Se agotó el rango de EAN disponible para el prefijo definido."
        )

    base_12 = f"{COUNTRY_PREFIX}{seq:04d}"  # 12 dígitos (sin checksum)
    ean_cls = barcode.get_barcode_class("ean13")
    ean = ean_cls(base_12)
    return ean.get_fullcode()  # Devuelve los 13 dígitos


def generate_labels_pdf(products, copies_per_product=24):
    """
    Crea un PDF (A4) con una parrilla de 24 etiquetas ―3 columnas x 8 filas―
    para cada producto seleccionado. Cada celda incluye:
        • imagen del código de barras
        • nombre del producto
    (El texto con los 13 dígitos ya aparece dentro de la imagen generada).
    """
    if not products:
        st.warning("No hay productos seleccionados.")
        return

    os.makedirs("outputs", exist_ok=True)
    pdf_path = "outputs/etiquetas.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Parrilla: márgenes y tamaños de celda
    # Margen exterior: 0.8 cm lateral, 1.2 cm arriba/abajo
    margin_x = 8 * mm
    margin_y = 12 * mm

    cols = 3
    rows = 8

    # Cada rectángulo (etiqueta) mide 6.5 cm x 3.5 cm
    cell_w = 65 * mm
    cell_h = 35 * mm

    # Margen interno horizontal y vertical para imagen y texto
    h_margin = 5 * mm  # 0,5 cm a cada lado
    v_margin = 4 * mm  # margen vertical interno

    # Ahora solo hay UNA línea de texto ⇒ reservamos ≈ 3,5 mm
    text_block_h = 3.5 * mm

    # Dimensiones máximas para la imagen del código de barras
    img_max_w = cell_w - 2 * h_margin
    img_max_h = cell_h - 2 * v_margin - text_block_h

    # Writer-options para hacer el código más alto (sin variar la fuente)
    writer_opts = {
        "module_width": 0.70,  # barras ligeramente más anchas
        "module_height": 25.0,  # barras más altas
        "quiet_zone": 2.0,  # margen blanco reducido
        "font_size": 15,  # tamaño de texto de los dígitos
        "text_distance": 6.0,
        "dpi": 400,
    }

    # --- NO DIBUJAR NINGUNA LÍNEA DE MÁRGENES NI GRILLA ---

    for product_name in products:
        ean_code = st.session_state.df_inventory.loc[
            st.session_state.df_inventory["Producto"] == product_name, "EAN"
        ].iloc[0]

        try:
            barcode_obj = EAN13NoChecksum(ean_code, writer=ImageWriter())
            buffer = BytesIO()
            # pasamos las opciones al escribir para obtener un PNG más grande
            barcode_obj.write(buffer, options=writer_opts)
            buffer.seek(0)
            barcode_img = ImageReader(buffer)

            # Ajustar tamaño en la celda manteniendo proporciones
            orig_w, orig_h = barcode_img.getSize()
            scale = min(img_max_w / orig_w, img_max_h / orig_h)
            scaled_w = orig_w * scale
            scaled_h = orig_h * scale

            # Dibujar 24 copias (3×8)
            for row in range(rows):
                for col in range(cols):
                    x0 = margin_x + col * cell_w
                    y0 = height - margin_y - (row + 1) * cell_h

                    # Imagen arriba, texto debajo y más pegado (1 mm)
                    img_x = x0 + (cell_w - scaled_w) / 2
                    img_y = y0 + cell_h - v_margin - scaled_h
                    text_y = img_y - 1 * mm  # 1 mm separación

                    # Dibujar imagen
                    c.drawImage(
                        barcode_img,
                        img_x,
                        img_y,
                        width=scaled_w,
                        height=scaled_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )

                    # Nombre del producto (centrado, fuente más grande)
                    c.setFont("Helvetica-Bold", 9)
                    c.drawCentredString(x0 + cell_w / 2, text_y, product_name)
            c.showPage()
        except Exception as e:
            st.error(f"Error al generar código de barras para {ean_code}: {e}")

    c.save()
    # No mostrar botón de descarga aquí, la descarga se gestiona desde el botón principal


# -----------------------------------
#  UI: 1. CARGA DE INVENTARIO
# -----------------------------------
st.header("1. Carga de inventario")
uploaded_file = st.file_uploader("Sube tu archivo Excel", type=["xlsx"])

if uploaded_file and uploaded_file.name != st.session_state.get("uploaded_filename"):
    try:
        df = pd.read_excel(uploaded_file, sheet_name="Hoja1", dtype=str)
        df.columns = [c.strip() for c in df.columns]

        # Renombrar
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower == "producto":
                col_map[col] = "Producto"
            elif col_lower in {"ean", "codigo ean-13"}:
                col_map[col] = "EAN"
        df = df.rename(columns=col_map)

        if not {"Producto", "EAN"}.issubset(df.columns):
            raise ValueError(
                "El archivo debe contener las columnas 'Producto' y 'EAN'."
            )

        df["EAN"] = (
            df["EAN"].astype(str).str.replace(".0", "", regex=False).str.zfill(13)
        )

        st.session_state.df_inventory = df.drop_duplicates(subset=["Producto"])
        st.session_state.uploaded_filename = uploaded_file.name

        st.success("Inventario cargado correctamente.")
        st.dataframe(st.session_state.df_inventory.head())
        st.caption("Se muestran las primeras 5 filas.")

    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")

# -----------------------------------
#  UI: 2. AÑADIR PRODUCTO
# -----------------------------------
st.header("2. Añadir producto")

with st.form("new_product_form"):
    product_type = st.selectbox("Tipo de producto", ["Samarreta"])
    color = st.text_input("Color")
    size = st.selectbox("Talla", ["XS", "S", "M", "L", "XL"])

    product_name = f"{product_type} {color} - {size}".strip()

    new_ean = generate_next_ean(st.session_state.df_inventory)

    st.markdown(f"**EAN sugerido:** `{new_ean}`")

    submitted = st.form_submit_button("Añadir producto")

    if submitted:
        if not color:
            st.warning("Debes indicar el color.")
            st.stop()

        if product_name in st.session_state.df_inventory["Producto"].values:
            st.error("Este producto ya existe en el inventario.")
            st.stop()

        new_row = {"Producto": product_name, "EAN": new_ean}
        st.session_state.df_inventory = pd.concat(
            [st.session_state.df_inventory, pd.DataFrame([new_row])], ignore_index=True
        )

        st.success(f"¡Añadido con éxito! EAN: {new_ean}")

# -----------------------------------
#  UI: 3. SELECCIÓN DE ETIQUETAS
# -----------------------------------
st.header("3. Selección de etiquetas")

selected_products = st.multiselect(
    "Elige productos para imprimir (máx. 10)",
    st.session_state.df_inventory["Producto"].tolist(),
    max_selections=10,
)

if st.button("Generar etiquetas PDF"):
    # Genera el PDF y lo descarga directamente
    os.makedirs("outputs", exist_ok=True)
    pdf_path = "outputs/etiquetas.pdf"
    generate_labels_pdf(selected_products)
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    st.download_button(
        label="Descargar PDF de Etiquetas",
        data=pdf_bytes,
        file_name="etiquetas_MONA.pdf",
        mime="application/pdf",
    )

# -----------------------------------
#  DESCARGA INVENTARIO COMPLETO
# -----------------------------------
st.header("4. Descargar inventario actualizado")

if st.button("Descargar Excel"):
    output = BytesIO()
    st.session_state.df_inventory.to_excel(output, index=False)
    output.seek(0)

    base, ext = os.path.splitext(
        st.session_state.uploaded_filename or "inventario.xlsx"
    )
    date_suffix = datetime.now().strftime("%Y%m%d")
    download_name = f"{base}_{date_suffix}{ext}"

    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
