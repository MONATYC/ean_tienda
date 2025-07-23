# ean_creator.py

# Import statements remain the same
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
#  CUSTOM BARCODE CLASS (Keep as is)
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
#  SESSION STATE INITIALIZATION (Keep as is)
# -----------------------------------
# Note: st.set_page_config is removed from here and moved to app.py
if "df_inventory" not in st.session_state:
    st.session_state.df_inventory = pd.DataFrame(columns=["Producto", "EAN"])
if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = None


def ensure_session_state():
    """Recreate essential session state keys on every run."""
    if "df_inventory" not in st.session_state:
        st.session_state.df_inventory = pd.DataFrame(columns=["Producto", "EAN"])
    if "uploaded_filename" not in st.session_state:
        st.session_state.uploaded_filename = None


# -----------------------------------
#  FUNCTIONS (Keep as is)
# -----------------------------------
COUNTRY_PREFIX = "84370000"  # 8-digits : 84 (ES) + 370000 (organización)


def _next_sequential_number(df: pd.DataFrame) -> int:
    """
    Devuelve el siguiente número secuencial (4 dígitos) mirando
    los EAN del inventario que siguen el patrón del prefijo del país.
    Ignora los EAN que no siguen el patrón (considerados antiguos o aleatorios).
    """
    if df.empty or "EAN" not in df.columns:
        return 1
    # Filtrar EANs que siguen el patrón: empiezan con el prefijo y tienen 13 dígitos numéricos.
    pattern_eans = df[
        df["EAN"].str.startswith(COUNTRY_PREFIX, na=False)
        & (df["EAN"].str.len() == 13)
        & (df["EAN"].str.isdigit())
    ]
    if pattern_eans.empty:
        return 1
    # Extraer la parte secuencial, convertir a número y encontrar el máximo.
    seq_numbers = pd.to_numeric(pattern_eans["EAN"].str.slice(8, 12), errors="coerce")
    if seq_numbers.dropna().empty:
        return 1
    seq_max = seq_numbers.max()
    return int(seq_max) + 1


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


def get_inventory_excel():
    """
    Devuelve un objeto BytesIO con el inventario y el nombre de archivo
    que incluye la fecha (ej.: inventario_20250711.xlsx).
    """
    output = BytesIO()
    st.session_state.df_inventory.to_excel(output, index=False)
    output.seek(0)
    base, ext = os.path.splitext(
        st.session_state.uploaded_filename or "inventario.xlsx"
    )
    date_suffix = datetime.now().strftime("%Y%m%d")
    download_name = f"{base}_{date_suffix}{ext}"
    return output, download_name


# -----------------------------------
#  MAIN FUNCTION WRAPPING THE UI LOGIC
# -----------------------------------
def main():
    ensure_session_state()
    # All your original UI code goes here, inside this function
    # Remove the st.set_page_config line from here if it exists

    # -----------------------------------
    #  UI: 1. CARGA DE INVENTARIO (Keep as is)
    # -----------------------------------
    st.header("1. Carga de inventario")
    uploaded_file = st.file_uploader("Sube tu archivo Excel", type=["xlsx"])
    if uploaded_file and uploaded_file.name != st.session_state.get(
        "uploaded_filename"
    ):
        try:
            # Leer la primera hoja independientemente del nombre
            xl = pd.ExcelFile(uploaded_file)
            first_sheet = xl.sheet_names[0]
            df = xl.parse(first_sheet, dtype=str)
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
    #  UI: 2. AÑADIR PRODUCTO (Keep as is)
    # -----------------------------------
    st.header("2. Añadir producto")
    if st.session_state.uploaded_filename is None:
        st.warning("Primero debes cargar un archivo de inventario en el paso 1.")
    else:
        with st.form("new_product_form"):
            # Solo un campo para el nombre de producto
            product_name = st.text_input("Nombre de producto").strip()
            # Sugerir EAN compatible libre
            if not st.session_state.df_inventory.empty:
                used_eans = set(st.session_state.df_inventory["EAN"].values)
                seq = _next_sequential_number(st.session_state.df_inventory)
                while True:
                    if seq > 9999:
                        suggested_ean = ""
                        break
                    base_12 = f"{COUNTRY_PREFIX}{seq:04d}"
                    ean_cls = barcode.get_barcode_class("ean13")
                    ean_obj = ean_cls(base_12)
                    candidate_ean = ean_obj.get_fullcode()
                    if candidate_ean not in used_eans:
                        suggested_ean = candidate_ean
                        break
                    seq += 1
            else:
                suggested_ean = ""
            ean_input = st.text_input(
                "Código EAN-13",
                value=suggested_ean,
                help="Debe tener 13 dígitos numéricos.",
                max_chars=13,
            )
            submitted = st.form_submit_button("Añadir producto")
            if submitted:
                if not product_name:
                    st.warning("Debes indicar el nombre del producto.")
                    st.stop()
                if not ean_input.isdigit() or len(ean_input) != 13:
                    st.warning("El EAN debe contener 13 dígitos numéricos.")
                    st.stop()
                if product_name in st.session_state.df_inventory["Producto"].values:
                    st.error(
                        f"El producto '{product_name}' ya existe en el inventario."
                    )
                    st.stop()
                if ean_input in st.session_state.df_inventory["EAN"].values:
                    st.error(f"El EAN '{ean_input}' ya está asignado a otro producto.")
                    st.stop()
                new_row = {"Producto": product_name, "EAN": ean_input}
                st.session_state.df_inventory = pd.concat(
                    [st.session_state.df_inventory, pd.DataFrame([new_row])],
                    ignore_index=True,
                )
                st.success(
                    f"¡Añadido con éxito! Producto: {product_name}, EAN: {ean_input}"
                )
    # -----------------------------------
    #  UI: 3. SELECCIÓN DE ETIQUETAS (Keep as is)
    # -----------------------------------
    st.header("3. Selección de etiquetas")
    selected_products = st.multiselect(
        "Elige productos para imprimir (máx. 10)",
        st.session_state.df_inventory["Producto"].tolist(),
        max_selections=10,
    )

    def render_pdf_buffer(product_list):
        if not product_list:
            return None
        buffer = BytesIO()
        width, height = A4
        margin_x = 8 * mm
        margin_y = 12 * mm
        extra_bottom_margin = -3 * mm  # Añade 3mm de margen blanco inferior
        cols = 3
        rows = 8
        cell_w = 65 * mm
        cell_h = 35 * mm
        h_margin = 5 * mm
        v_margin = 4 * mm
        text_block_h = 3.5 * mm
        img_max_w = cell_w - 2 * h_margin
        img_max_h = cell_h - 2 * v_margin - text_block_h
        writer_opts = {
            "module_width": 0.70,  # ancho de módulo en mm
            "module_height": 25.0,  # altura del código de barras en mm
            "quiet_zone": 2.0,  # zona de silencio en mm
            "font_size": 15,  # tamaño de fuente para el texto
            "text_distance": 6.0,  # distancia entre el código y el texto
            "dpi": 400,  # resolución en DPI
        }
        c = canvas.Canvas(buffer, pagesize=A4)
        for product_name in product_list:
            ean_code = st.session_state.df_inventory.loc[
                st.session_state.df_inventory["Producto"] == product_name, "EAN"
            ].iloc[0]
            barcode_obj = EAN13NoChecksum(ean_code, writer=ImageWriter())
            img_buffer = BytesIO()
            barcode_obj.write(img_buffer, options=writer_opts)
            img_buffer.seek(0)
            barcode_img = ImageReader(img_buffer)
            orig_w, orig_h = barcode_img.getSize()
            scale = min(img_max_w / orig_w, img_max_h / orig_h)
            scaled_w = orig_w * scale
            scaled_h = orig_h * scale
            for row in range(rows):
                for col in range(cols):
                    x0 = margin_x + col * cell_w
                    # Suma el extra solo al margen inferior
                    y0 = height - (margin_y + extra_bottom_margin) - (row + 1) * cell_h
                    img_x = x0 + (cell_w - scaled_w) / 2
                    img_y = y0 + cell_h - v_margin - scaled_h
                    text_y = img_y - 1 * mm
                    c.drawImage(
                        barcode_img,
                        img_x,
                        img_y,
                        width=scaled_w,
                        height=scaled_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    c.setFont("Helvetica-Bold", 9)
                    c.drawCentredString(x0 + cell_w / 2, text_y, product_name)
            c.showPage()
        c.save()
        buffer.seek(0)
        return buffer

    if selected_products:
        pdf_buffer = render_pdf_buffer(selected_products)
        st.download_button(
            label="Generar y descargar etiquetas PDF",
            data=pdf_buffer.getvalue(),
            file_name="etiquetas_MONA.pdf",
            mime="application/pdf",
            key="download_etiquetas",
        )
    else:
        st.warning("Selecciona al menos un producto para imprimir.")
    # -----------------------------------
    #  UI: 4. DESCARGAR INVENTARIO COMPLETO (Keep as is)
    # -----------------------------------
    st.header("4. Descargar inventario actualizado")
    output, download_name = get_inventory_excel()  # genera el Excel al vuelo
    st.download_button(
        label="📥 Descargar Excel",
        data=output.getvalue(),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel",
    )


# The main() function is called by app.py
# if __name__ == "__main__": # This line is not needed in ean_creator.py
#     main()
