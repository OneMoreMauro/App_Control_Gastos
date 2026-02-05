import streamlit as st
import pandas as pd
import dropbox
from dropbox.exceptions import ApiError
from io import BytesIO
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Financiero", layout="wide", page_icon="💰")

# --- GESTIÓN DE SECRETOS ---
try:
    DROPBOX_ACCESS_TOKEN = st.secrets["DROPBOX_ACCESS_TOKEN"]
    UBICACION_ARCHIVO = st.secrets.get("UBICACION_ARCHIVO", '/Gastos.xlsx')
    APP_PASSWORD = st.secrets["APP_PASSWORD"]  # Obliga a configurar en secrets
except Exception:
    st.error("⚠️ Error crítico: No se encontraron los secretos. Configura los secrets en Streamlit Cloud.")
    st.stop()

# --- SISTEMA DE LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if st.session_state.password_input == APP_PASSWORD:
        st.session_state.authenticated = True
    else:
        st.error("⛔ Contraseña incorrecta")

if not st.session_state.authenticated:
    st.title("🔒 Acceso Restringido")
    st.text_input("Ingrese contraseña de acceso:", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- FUNCIONES DROPBOX ---
def conectar_dropbox():
    try:
        dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
        dbx.users_get_current_account()  # Check rápido
        return dbx
    except Exception as e:
        st.error(f"❌ Error conectando a Dropbox: {e}")
        return None

def crear_template(dbx):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(columns=['Fecha', 'Concepto', 'Categoría', 'Detalle', 'Monto', 'Estado']).to_excel(writer, sheet_name='Movimientos', index=False)
        pd.DataFrame({
            'Concepto': ['Sueldo', 'Colegio hijos', 'Netflix', 'Uber', 'AFIP', 'Carrefour', 'Visa', 'Plazo fijo', 'Ropa', 'Varios', 'Ministerio', 'IUV', 'Magui', 'MP', 'NX', 'PPay', 'Otros'],
            'Categoría': ['Ingresos', 'Educación y Cuidado', 'Suscripciones', 'Transporte', 'Impuestos', 'Supermercado', 'Tarjetas', 'Inversiones', 'Indumentaria', 'Gastos Extraordinarios', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos no salariales'],
            'Tipo': ['Ingresos', 'Fijo', 'Fijo', 'Variable', 'Fijo', 'Variable', 'Fijo', 'Ingreso', 'Variable', 'Variable', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos', 'Ingresos']
        }).to_excel(writer, sheet_name='Conceptos', index=False)
        pd.DataFrame(columns=['Concepto', 'Monto_Est', 'Categoría']).to_excel(writer, sheet_name='Fijos', index=False)
    data = output.getvalue()
    try:
        dbx.files_upload(data, UBICACION_ARCHIVO, mode=dropbox.files.WriteMode.overwrite)
        st.success("✅ Plantilla base creada exitosamente.")
        return cargar_datos(dbx)
    except Exception as e:
        st.error(f"Error creando archivo: {e}")
        return None, None, None

def cargar_datos(dbx):
    try:
        _, res = dbx.files_download(UBICACION_ARCHIVO)
        excel_file = BytesIO(res.content)
        df_mov = pd.read_excel(excel_file, sheet_name='Movimientos', engine='openpyxl')
        df_con = pd.read_excel(excel_file, sheet_name='Conceptos', engine='openpyxl')
        df_fij = pd.read_excel(excel_file, sheet_name='Fijos', engine='openpyxl')
        if not df_mov.empty:
            df_mov['Fecha'] = pd.to_datetime(df_mov['Fecha'], errors='coerce')
            df_mov['Monto'] = pd.to_numeric(df_mov['Monto'], errors='coerce').fillna(0)
            df_mov['Detalle'] = df_mov['Detalle'].astype(str).replace('nan', '')
        return df_mov, df_con, df_fij
    except ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            st.warning("📂 Archivo no encontrado. Inicializando configuración...")
            return crear_template(dbx)
        else:
            st.error(f"Error API Dropbox: {e}")
            return None, None, None
    except Exception as e:
        st.error(f"Error general de lectura: {e}")
        return None, None, None

def guardar_cambios(dbx, df_mov, df_con, df_fij):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_mov.to_excel(writer, sheet_name='Movimientos', index=False)
            df_con.to_excel(writer, sheet_name='Conceptos', index=False)
            df_fij.to_excel(writer, sheet_name='Fijos', index=False)
        dbx.files_upload(output.getvalue(), UBICACION_ARCHIVO, mode=dropbox.files.WriteMode.overwrite)
        return True
    except Exception as e:
        st.error(f"Error guardando: {e}")
        return False

# --- INTERFAZ PRINCIPAL ---
def main():
    st.sidebar.title("Hola, Economista 👋")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()
    if st.sidebar.button("🔄 Refrescar Datos"):
        st.rerun()

    dbx = conectar_dropbox()
    if not dbx: return
    df_mov, df_conc, df_fijos = cargar_datos(dbx)
    if df_mov is None: return

    # --- KPIs (protegido) ---
    hoy = datetime.now()
    ingresos = 0.0
    gastos_pagados = 0.0
    gastos_pendientes = 0.0

    if not df_mov.empty and 'Fecha' in df_mov.columns and df_mov['Fecha'].notna().any():
        try:
            df_mes = df_mov[
                (df_mov['Fecha'].dt.month == hoy.month) &
                (df_mov['Fecha'].dt.year == hoy.year)
            ]
            ingresos = df_mes[df_mes['Monto'] > 0]['Monto'].sum()
            gastos_pagados = df_mes[(df_mes['Monto'] < 0) & (df_mes['Estado'] == 'Pagado')]['Monto'].sum()
            gastos_pendientes = df_mes[(df_mes['Monto'] < 0) & (df_mes['Estado'] == 'Pendiente')]['Monto'].sum()
        except AttributeError:
            st.warning("⚠️ Problema temporal con fechas. Saldos en cero hasta agregar movimientos.")
    else:
        st.info("📊 No hay movimientos. Agregá para ver cálculos.")

    st.title("📊 Tablero de Control")
    c1, c2, c3 = st.columns(3)
    c1.metric("Saldo Caja (Real)", f"${ingresos + gastos_pagados:,.2f}")
    c2.metric("Pendiente de Pago", f"${abs(gastos_pendientes):,.2f}", delta_color="inverse")
    c3.metric("Proyección Fin de Mes", f"${(ingresos + gastos_pagados + gastos_pendientes):,.2f}")
    st.markdown("---")

    # --- FORMULARIO DE CARGA ---
    with st.expander("➕ Registrar Movimiento", expanded=True):
        with st.form("nuevo_mov"):
            col1, col2, col3 = st.columns(3)
            fecha = col1.date_input("Fecha", hoy)
            opciones = df_conc['Concepto'].unique().tolist() if not df_conc.empty else ["Generico"]
            concepto = col2.selectbox("Concepto", opciones)
            cat_match = df_conc[df_conc['Concepto'] == concepto]
            cat_auto = "General"
            if not cat_match.empty:
                cat_auto = cat_match.iloc[0]['Categoría']
            monto = col3.number_input("Monto (Negativo=Gasto)", step=10.0, format="%.2f")
            detalle = st.text_input("Detalle (Obligatorio para 'Otros gastos')")
            if cat_auto == "Otros gastos":
                st.caption("⚠️ Detalle requerido.")
            estado = st.radio("Estado", ["Pendiente", "Pagado"], horizontal=True)
            if st.form_submit_button("Guardar"):
                if cat_auto == "Otros gastos" and not detalle.strip():
                    st.error("⛔ Falta detalle para 'Otros gastos'.")
                else:
                    nuevo = pd.DataFrame([{
                        'Fecha': pd.to_datetime(fecha),
                        'Concepto': concepto,
                        'Categoría': cat_auto,
                        'Detalle': detalle,
                        'Monto': monto,
                        'Estado': estado
                    }])
                    df_mov = pd.concat([df_mov, nuevo], ignore_index=True)
                    if guardar_cambios(dbx, df_mov, df_conc, df_fijos):
                        st.success("Guardado.")
                        st.rerun()

    # --- GESTIÓN DE PENDIENTES ---
    st.subheader("📝 Gestión de Pendientes")
    pendientes = df_mov[df_mov['Estado'] == 'Pendiente'].copy()
    if not pendientes.empty:
        edited_df = st.data_editor(
            pendientes,
            column_config={
                "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "Concepto": st.column_config.TextColumn("Concepto"),
                "Detalle": st.column_config.TextColumn("Detalle"),
                "Monto": st.column_config.NumberColumn("Monto", format="$ %.2f", step=10.0),
                "Estado": st.column_config.SelectboxColumn("Estado", options=["Pendiente", "Pagado"], required=True),
            },
            hide_index=True,
            use_container_width=True,
            key="editor_pendientes"
        )
        if st.button("💾 Actualizar Estados"):
            df_mov.update(edited_df)
            guardar_cambios(dbx, df_mov, df_conc, df_fijos)
            st.success("Estados actualizados.")
            st.rerun()
    else:
        st.info("No hay pagos pendientes.")

    # --- HISTORIAL ---
    with st.expander("Ver Histórico Completo"):
        st.dataframe(df_mov.sort_values("Fecha", ascending=False), use_container_width=True)

if __name__ == "__main__":
    main()
