import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import plotly.express as px
import psycopg2
import streamlit.components.v1 as components
import warnings
import requests
import re 

warnings.filterwarnings("ignore")

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
st.set_page_config(page_title="Gestor de Tarjetas", page_icon="💳", layout="wide")
st.markdown("""
    <style>
    .stMetric { 
        background-color: var(--secondary-background-color); 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1); 
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# PANTALLA DE INICIO DE SESIÓN (LOGIN)
# ---------------------------------------------------------
def verificar_password():
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if not st.session_state.autenticado:
        st.title("🔒 Acceso Restringido")
        st.subheader("Control de Tarjetas Compartidas")
        
        with st.form("form_login"):
            password_input = st.text_input("Ingresa la contraseña para ingresar:", type="password", autocomplete="current-password")
            btn_login = st.form_submit_button("Iniciar Sesión 🚀", use_container_width=True)
            
            if btn_login:
                password_correcta = st.secrets.get("APP_PASSWORD", "1234")
                if password_input == password_correcta:
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")
        st.stop()

verificar_password()

# ---------------------------------------------------------
# CONEXIÓN Y CACHÉ SUPABASE
# ---------------------------------------------------------
def conectar_bd():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def inicializar_bd():
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS tarjetas (id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, dia_corte INTEGER, dia_pago INTEGER);")
        cursor.execute("CREATE TABLE IF NOT EXISTS personas (id SERIAL PRIMARY KEY, nombre TEXT UNIQUE);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compras (
                id SERIAL PRIMARY KEY, concepto TEXT, categoria TEXT, monto_total REAL, fecha DATE, tarjeta_id INTEGER,
                FOREIGN KEY (tarjeta_id) REFERENCES tarjetas (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compra_participantes (
                compra_id INTEGER, persona_id INTEGER, monto_asignado REAL,
                PRIMARY KEY (compra_id, persona_id),
                FOREIGN KEY (compra_id) REFERENCES compras (id) ON DELETE CASCADE,
                FOREIGN KEY (persona_id) REFERENCES personas (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY, persona_id INTEGER, tarjeta_id INTEGER, monto REAL, fecha DATE,
                FOREIGN KEY (persona_id) REFERENCES personas (id) ON DELETE CASCADE,
                FOREIGN KEY (tarjeta_id) REFERENCES tarjetas (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("ALTER TABLE pagos ADD COLUMN IF NOT EXISTS concepto TEXT DEFAULT 'Abono a deuda';")
        
        usuarios_base = ["Julio", "Karol", "Omar", "Martha"]
        for usr in usuarios_base:
            cursor.execute("INSERT INTO personas (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING;", (usr,))
            
        conn.commit()
    except Exception as e:
        st.error(f"Error al inicializar la base de datos: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

inicializar_bd()

@st.cache_data(ttl=300, show_spinner=False)
def consultar_datos(query):
    try:
        conn = conectar_bd()
        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        st.error(f"Error en consulta: {e}")
        return pd.DataFrame()
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def sumar_meses(fecha_original, meses_a_sumar):
    mes = fecha_original.month - 1 + meses_a_sumar
    año = fecha_original.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha_original.day, calendar.monthrange(año, mes)[1])
    return datetime(año, mes, dia)

# ---------------------------------------------------------
# INTERFAZ PRINCIPAL Y MANEJO DE TOASTS
# ---------------------------------------------------------
if "menu_actual" not in st.session_state:
    st.session_state.menu_actual = "📊 Dashboard"

def cambiar_menu(nueva_opcion):
    st.session_state.menu_actual = nueva_opcion
    st.session_state.cerrar_sidebar = True

with st.sidebar:
    st.title("📱 Menú Principal")
    st.write("Selecciona una opción:")
    
    opciones_menu = ["📊 Dashboard", "📈 Proyecciones", "🛒 Registrar Compra", "💸 Liquidar Deuda", "📝 Reportes", "🛠️ Gestionar", "⚙️ Ajustes"]
    
    for opcion in opciones_menu:
        es_activa = (st.session_state.menu_actual == opcion)
        st.button(
            opcion, 
            use_container_width=True, 
            type="primary" if es_activa else "secondary",
            on_click=cambiar_menu, 
            args=(opcion,),
            key=f"btn_{opcion}"
        )
        
    st.divider()
    st.write("👤 **Sesión Activa**")
    if st.button("Cerrar Sesión 🚪", use_container_width=True, type="secondary"):
        st.session_state.autenticado = False
        st.cache_data.clear()
        st.rerun()

menu = st.session_state.menu_actual

if 'mensaje_exito' in st.session_state:
    st.toast(st.session_state.mensaje_exito, icon="✅")
    del st.session_state.mensaje_exito
if 'mensaje_error' in st.session_state:
    st.toast(st.session_state.mensaje_error, icon="❌")
    del st.session_state.mensaje_error

st.title(menu)

if st.session_state.get('cerrar_sidebar', False):
    components.html(
        """
        <script>
            const doc = window.parent.document;
            const sidebar = doc.querySelector('[data-testid="stSidebar"]');
            if (sidebar) {
                const closeBtn = sidebar.querySelector('button');
                if (closeBtn) closeBtn.click();
            }
        </script>
        """, height=0, width=0
    )
    st.session_state.cerrar_sidebar = False

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    with st.expander("🔍 Mostrar/Ocultar Filtros de Tiempo", expanded=False):
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            mes_filtro = st.text_input("Filtrar por Mes (YYYY-MM)", value=datetime.now().strftime("%Y-%m"))
        with c_f2:
            quincena_filtro = st.selectbox("Filtrar por Quincena", ["Mes Completo", "1ra Quincena (1-15)", "2da Quincena (16-31)"])

    calc_pago = "(DATE_TRUNC('month', c.fecha) + (CASE WHEN EXTRACT(DAY FROM c.fecha) > t.dia_corte THEN 1 ELSE 0 END + CASE WHEN t.dia_pago <= t.dia_corte THEN 1 ELSE 0 END) * INTERVAL '1 month' + (t.dia_pago - 1) * INTERVAL '1 day')::DATE"

    condicion_c = f"TO_CHAR({calc_pago}, 'YYYY-MM') = '{mes_filtro}'"
    condicion_p = f"TO_CHAR(pa.fecha::DATE, 'YYYY-MM') = '{mes_filtro}'"
    
    if "1ra" in quincena_filtro:
        condicion_c += f" AND EXTRACT(DAY FROM {calc_pago}) <= 15"
        condicion_p += " AND EXTRACT(DAY FROM pa.fecha::DATE) <= 15"
    elif "2da" in quincena_filtro:
        condicion_c += f" AND EXTRACT(DAY FROM {calc_pago}) > 15"
        condicion_p += " AND EXTRACT(DAY FROM pa.fecha::DATE) > 15"

    query_saldos = f"""
    WITH base_pt AS (SELECT p.id as persona_id, p.nombre as Persona, t.id as tarjeta_id, t.nombre as Tarjeta FROM personas p CROSS JOIN tarjetas t),
    compras_periodo AS (
        SELECT cp.persona_id, c.tarjeta_id, SUM(cp.monto_asignado) AS consumido, STRING_AGG(c.concepto, ' | ') AS conceptos_compra 
        FROM compras c JOIN compra_participantes cp ON c.id = cp.compra_id JOIN tarjetas t ON c.tarjeta_id = t.id 
        WHERE {condicion_c} GROUP BY cp.persona_id, c.tarjeta_id
    ),
    pagos_periodo AS (SELECT pa.persona_id, pa.tarjeta_id, SUM(pa.monto) AS pagado, STRING_AGG(pa.concepto, ' | ') AS conceptos_pago FROM pagos pa WHERE {condicion_p} GROUP BY pa.persona_id, pa.tarjeta_id),
    compras_global AS (SELECT cp.persona_id, c.tarjeta_id, SUM(cp.monto_asignado) AS consumido_global FROM compras c JOIN compra_participantes cp ON c.id = cp.compra_id GROUP BY cp.persona_id, c.tarjeta_id),
    pagos_global AS (SELECT pa.persona_id, pa.tarjeta_id, SUM(pa.monto) AS pagado_global FROM pagos pa GROUP BY pa.persona_id, pa.tarjeta_id)
    
    SELECT b.Persona, b.Tarjeta, 
           ROUND(COALESCE(cp.consumido, 0)::numeric, 2) AS "Consumo Filtro", 
           COALESCE(cp.conceptos_compra, '-') AS "Detalle Compras",
           ROUND(COALESCE(pp.pagado, 0)::numeric, 2) AS "Pagos Filtro",
           COALESCE(pp.conceptos_pago, '-') AS "Detalle Pagos",
           ROUND((COALESCE(cp.consumido, 0) - COALESCE(pp.pagado, 0))::numeric, 2) AS "Saldo del Filtro"
    FROM base_pt b
    LEFT JOIN compras_periodo cp ON b.persona_id = cp.persona_id AND b.tarjeta_id = cp.tarjeta_id 
    LEFT JOIN pagos_periodo pp ON b.persona_id = pp.persona_id AND b.tarjeta_id = pp.tarjeta_id
    LEFT JOIN compras_global cg ON b.persona_id = cg.persona_id AND b.tarjeta_id = cg.tarjeta_id 
    LEFT JOIN pagos_global pg ON b.persona_id = pg.persona_id AND b.tarjeta_id = pg.tarjeta_id
    WHERE (COALESCE(cp.consumido, 0) > 0 OR COALESCE(pp.pagado, 0) > 0) OR ('{quincena_filtro}' = 'Mes Completo' AND (COALESCE(cg.consumido_global, 0) - COALESCE(pg.pagado_global, 0)) > 0.01)
    ORDER BY b.Persona, b.Tarjeta
    """
    df_saldos = consultar_datos(query_saldos)
    
    q_trend_full = f"""
        SELECT TO_CHAR({calc_pago}, 'YYYY-MM') AS "Mes", p.nombre AS "Persona", SUM(cp.monto_asignado) AS "Consumo"
        FROM compras c JOIN compra_participantes cp ON c.id = cp.compra_id JOIN personas p ON cp.persona_id = p.id JOIN tarjetas t ON c.tarjeta_id = t.id
        GROUP BY "Mes", "Persona"
    """
    df_trend_full = consultar_datos(q_trend_full)
    
    query_global = "SELECT SUM(monto_asignado) FROM compra_participantes"
    query_pagos_global = "SELECT SUM(monto) FROM pagos"
    tot_comp = consultar_datos(query_global).iloc[0,0] or 0.0
    tot_pag = consultar_datos(query_pagos_global).iloc[0,0] or 0.0
    deuda_historica_total = tot_comp - tot_pag

    df_categorias = consultar_datos(f"SELECT c.categoria, SUM(c.monto_total) as total FROM compras c JOIN tarjetas t ON c.tarjeta_id = t.id WHERE {condicion_c} GROUP BY c.categoria")

    consumo_actual = df_saldos['Consumo Filtro'].sum() if not df_saldos.empty else 0.0
    delta_val = 0.0
    try:
        if not df_trend_full.empty:
            mes_prev_str = (datetime.strptime(mes_filtro, "%Y-%m").replace(day=1) - pd.Timedelta(days=1)).strftime("%Y-%m")
            consumo_previo = df_trend_full[df_trend_full['Mes'] == mes_prev_str]['Consumo'].sum()
            delta_val = consumo_actual - consumo_previo
    except:
        pass 

    if not df_saldos.empty:
        c1, c2 = st.columns(2)
        c1.metric("💸 Deuda (Histórica Total)", f"${deuda_historica_total:,.2f}")
        c2.metric("🎯 Consumo en el Filtro", f"${consumo_actual:,.2f}", delta=f"${delta_val:,.2f}" if delta_val != 0 else None, delta_color="inverse")
        
        c3, c4 = st.columns(2)
        c3.metric("✅ Pagos en el Filtro", f"${df_saldos['Pagos Filtro'].sum():,.2f}")
        c4.metric("⚖️ Saldo Pendiente", f"${df_saldos['Saldo del Filtro'].sum():,.2f}")
        st.divider()
        
        st.subheader("📋 Detalle de Saldos")
        st.dataframe(df_saldos.style.format({"Consumo Filtro": "${:.2f}", "Pagos Filtro": "${:.2f}", "Saldo del Filtro": "${:.2f}"}), use_container_width=True, hide_index=True)
            
        st.divider()
        col_graf_1, col_graf_2 = st.columns(2)
        
        with col_graf_1:
            st.subheader("🛍️ Por Categoría")
            if not df_categorias.empty:
                fig = px.pie(df_categorias, values='total', names='categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                
        with col_graf_2:
            st.subheader("📈 Histórico del Grupo")
            if not df_trend_full.empty:
                df_trend_last = df_trend_full.sort_values("Mes").tail(15) 
                fig_trend = px.bar(df_trend_last, x="Mes", y="Consumo", color="Persona", text_auto='.0f', color_discrete_sequence=px.colors.qualitative.Set2)
                fig_trend.update_layout(margin=dict(t=10, b=10, l=10, r=10), barmode='stack')
                st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info(f"No hay movimientos registrados ni deudas para {quincena_filtro} de {mes_filtro}.")

# --- 1.5 PROYECCIONES ---
elif menu == "📈 Proyecciones":
    st.subheader("🔮 Radar de Pagos Futuros (MSI)")
    mes_actual = datetime.now().strftime("%Y-%m")
    q_proj =