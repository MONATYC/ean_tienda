import streamlit as st
import pandas as pd
import barcode
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

# Configuración inicial
st.set_page_config(layout="wide", page_title="Gestor EAN - MONA")

# Estado de sesión
if "df_inventory" not in st.session_state:
    st.session_state.df_inventory = pd.DataFrame(columns=["Producto", "Codigo_EAN-13"])


# Función para generar EAN secuencial (MOVED UP)
def generate_next_ean(last_ean):
    prefix = last_ean[:8]  # Mantener los primeros 8 dígitos del prefijo
    numeric_part = int(last_ean[8:-1]) + 1  # Incrementar la secuencia
    new_base = f"{prefix}{numeric_part:05d}"  # Formato de 5 dígitos
    # Calcular dígito de control con la librería
    ean_cls = barcode.get_barcode_class("ean13")
    ean = ean_cls(new_base)
    full_ean = ean.get_fullcode()
    return full_ean


# Función para generar PDF con ReportLab (MOVED UP)
def generate_labels_pdf():
    pdf_path = "outputs/etiquetas.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # APLI 01263 Label dimensions
    label_w = 64.6 * mm
    label_h = 33.8 * mm

    # APLI 01263 Margins and Gaps
    margin_left = 9.7 * mm
    margin_right = 9.7 * mm
    margin_top = 10.5 * mm
    margin_bottom = 10.5 * mm
    gap_h = 3.1 * mm  # Horizontal gap between labels
    gap_v = 0 * mm  # Vertical gap between labels (labels are stacked directly)

    col_num = 3
    row_num = 8
    labels_per_page = col_num * row_num

    # Collect all labels to print
    labels_to_print = []
    if (
        "selected_products_for_labels" in st.session_state
        and "quantities_for_labels" in st.session_state
    ):
        selected_products = st.session_state.selected_products_for_labels
        quantities = st.session_state.quantities_for_labels
        for product_name in selected_products:
            qty = quantities.get(product_name, 0)
            if qty > 0:
                # Find the EAN for the product from the inventory DataFrame
                ean = st.session_state.df_inventory[
                    st.session_state.df_inventory["Producto"] == product_name
                ]["Codigo_EAN-13"].iloc[0]
                for _ in range(qty):
                    labels_to_print.append({"product": product_name, "ean": ean})

    if not labels_to_print:
        st.warning("No hay productos seleccionados para generar etiquetas.")
        return

    current_label_idx = 0
    while current_label_idx < len(labels_to_print):
        if current_label_idx > 0:
            c.showPage()  # Start a new page if not the first label on the first page

        for row in range(row_num):
            for col in range(col_num):
                if current_label_idx < len(labels_to_print):
                    label_data = labels_to_print[current_label_idx]
                    product_name = label_data["product"]
                    ean_code = label_data["ean"]

                    # Calculate position for the current label
                    # X-coordinate: left margin + (label width + horizontal gap) * column index
                    x_pos = margin_left + col * (label_w + gap_h)
                    # Y-coordinate: top of page - top margin - (label height + vertical gap) * row index - label height
                    # ReportLab origin is bottom-left, so calculate from top-right and subtract
                    y_pos = height - margin_top - (row + 1) * (label_h + gap_v)

                    # Generate barcode image
                    try:
                        ean_cls = barcode.get_barcode_class("ean13")
                        EAN = ean_cls(ean_code, writer=barcode.writer.ImageWriter())
                        # Save barcode to a BytesIO object to avoid disk I/O
                        from io import BytesIO

                        buffer = BytesIO()
                        EAN.write(buffer)
                        buffer.seek(0)
                        barcode_image = Image.open(buffer)

                        # Resize barcode image to fit label width, maintaining aspect ratio
                        barcode_max_width = label_w * 0.9  # Leave some padding
                        barcode_max_height = (
                            label_h * 0.6
                        )  # Leave space for EAN text and product name

                        img_w, img_h = barcode_image.size
                        aspect_ratio = img_w / img_h

                        if img_w > barcode_max_width:
                            img_w = barcode_max_width
                            img_h = img_w / aspect_ratio
                        if img_h > barcode_max_height:
                            img_h = barcode_max_height
                            img_w = img_h * aspect_ratio

                        # Draw barcode image
                        # Center barcode horizontally within the label
                        barcode_x = x_pos + (label_w - img_w) / 2
                        # Position barcode above the EAN text
                        barcode_y = (
                            y_pos + label_h - img_h - (label_h * 0.1)
                        )  # Adjust for top padding

                        c.drawImage(
                            barcode_image,
                            barcode_x,
                            barcode_y,
                            width=img_w,
                            height=img_h,
                        )

                        # Draw EAN code text
                        c.setFont("Helvetica", 8)  # Smaller font for EAN
                        text_x = x_pos + label_w / 2  # Center text
                        text_y = y_pos + (
                            label_h * 0.1
                        )  # Position near bottom of label

                        c.drawCentredString(text_x, text_y, ean_code)

                        # Optional: Draw product name
                        c.setFont("Helvetica-Bold", 7)  # Even smaller for product name
                        product_text_y = barcode_y - 10  # Above barcode
                        c.drawCentredString(text_x, product_text_y, product_name)

                    except Exception as e:
                        st.error(
                            f"Error al generar código de barras para {ean_code}: {e}"
                        )
                        # Draw placeholder text if barcode generation fails
                        c.setFont("Helvetica", 8)
                        c.drawString(
                            x_pos + 5, y_pos + label_h / 2, f"ERROR: {ean_code}"
                        )

                    current_label_idx += 1
                else:
                    break  # No more labels to print
            if current_label_idx >= len(labels_to_print):
                break  # No more labels to print

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
        df = pd.read_excel(uploaded_file, sheet_name="Hoja1")
        df.columns = [c.strip() for c in df.columns]
        required_cols = {"Producto", "Codigo_EAN-13"}
        if not required_cols.issubset(df.columns):
            raise ValueError("Columnas incorrectas")
        st.session_state.df_inventory = df
        st.success("Inventario cargado correctamente")
        st.dataframe(df)
    except Exception:
        st.error(
            "Error al leer el archivo. Asegúrate de que contenga la hoja 'Hoja1' con columnas 'Producto' y 'Codigo_EAN-13'"
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
        last_ean = st.session_state.df_inventory["Codigo_EAN-13"].iloc[-1]
        new_ean = generate_next_ean(last_ean)
    else:
        new_ean = "8437000000001"  # Valor inicial por defecto

    submitted = st.form_submit_button("Añadir producto")
    if submitted:
        new_row = {
            "Producto": product_name,
            "Codigo_EAN-13": new_ean,
        }
        st.session_state.df_inventory = pd.concat(
            [st.session_state.df_inventory, pd.DataFrame([new_row])], ignore_index=True
        )
        st.success(f"¡Añadido con éxito! Código EAN: {new_ean}")

# Sección de selección de etiquetas
st.header("3. Selección de etiquetas")
with st.form("label_selection_form"):
    selected_products_for_labels = st.multiselect(
        "Elige productos", st.session_state.df_inventory["Producto"].tolist()
    )
    quantities = {}
    if selected_products_for_labels:
        st.subheader("Indica la cantidad para cada producto:")
        for idx, product in enumerate(selected_products_for_labels):
            key = f"quantity_{idx}"
            qty = st.number_input(
                f"{product}", min_value=1, value=1, step=1, format="%d", key=key
            )
            quantities[product] = qty
    submit_button_labels = st.form_submit_button("Confirmar selección de etiquetas")

    if submit_button_labels:
        st.session_state.selected_products_for_labels = selected_products_for_labels
        st.session_state.quantities_for_labels = quantities
        st.success("Selección de etiquetas confirmada.")

# Botón de generación de PDF
if st.button("Generar etiquetas PDF"):
    if (
        "selected_products_for_labels" in st.session_state
        and st.session_state.selected_products_for_labels
    ):
        generate_labels_pdf()
    else:
        st.warning(
            "Por favor, selecciona productos y confirma la selección antes de generar el PDF."
        )

# Botón de descarga de Excel actualizado
if st.button("Descargar inventario actualizado"):

    @st.cache
    def convert_df(df):
        return df.to_csv(index=False).encode("utf-8")

    csv = convert_df(st.session_state.df_inventory)
    st.download_button(
        label="📥 Descargar CSV",
        data=csv,
        file_name="inventario.csv",
        mime="text/csv",
    )
