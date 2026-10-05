import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
import plotly.express as px
import psycopg2
import streamlit.components.v1 as components
import warnings
import requests

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
    
    # NUEVO: Agregamos la columna 'concepto' a los pagos (Devoluciones/Reembolsos) si no existe
    cursor.execute("ALTER TABLE pagos ADD COLUMN IF NOT EXISTS concepto TEXT DEFAULT 'Abono a deuda';")
    
    usuarios_base = ["Julio", "Karol", "Omar", "Martha"]
    for usr in usuarios_base:
        cursor.execute("INSERT INTO personas (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING;", (usr,))
        
    conn.commit()
    conn.close()

inicializar_bd()

@st.cache_data(ttl=300, show_spinner=False)
def consultar_datos(query):
    conn = conectar_bd()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def sumar_meses(fecha_original, meses_a_sumar):
    mes = fecha_original.month - 1 + meses_a_sumar
    año = fecha_original.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha_original.day, calendar.monthrange(año, mes)[1])
    return datetime(año, mes, dia)

# ---------------------------------------------------------
# INTERFAZ PRINCIPAL (MOBILE FIRST)
# ---------------------------------------------------------

if "menu_actual" not in st.session_state:
    st.session_state.menu_actual = "📊 Dashboard"

def cambiar_menu(nueva_opcion):
    st.session_state.menu_actual = nueva_opcion
    st.session_state.cerrar_sidebar = True

with st.sidebar:
    st.title("📱 Menú Principal")
    st.write("Selecciona una opción:")
    
    # NUEVAS OPCIONES INTEGRADAS
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
    st.success(st.session_state.mensaje_exito)
    del st.session_state.mensaje_exito
if 'mensaje_error' in st.session_state:
    st.error(st.session_state.mensaje_error)
    del st.session_state.mensaje_error

st.title(menu)

if st.session_state.get('cerrar_sidebar', False):
    components.html(
        """
        <script>
            const doc = window.parent.document;
            const sidebar = doc.querySelector('[data-testid="stSidebar"]');
            if (sidebar) {
                // El botón "X" para cerrar siempre es el primer botón dentro del menú
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

    # 🧠 FÓRMULA SQL MAGISTRAL: Calcula la fecha de pago exacta basándose en el corte
    calc_pago = "(DATE_TRUNC('month', c.fecha) + (CASE WHEN EXTRACT(DAY FROM c.fecha) > t.dia_corte THEN 1 ELSE 0 END + CASE WHEN t.dia_pago <= t.dia_corte THEN 1 ELSE 0 END) * INTERVAL '1 month' + (t.dia_pago - 1) * INTERVAL '1 day')::DATE"

    # Los filtros ahora evalúan la fecha de cobro proyectada, no la de compra
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
    
    -- IMPORTANTE: Agregamos el JOIN a tarjetas 't' para poder usar sus días de corte/pago
    compras_periodo AS (
        SELECT cp.persona_id, c.tarjeta_id, SUM(cp.monto_asignado) AS consumido, STRING_AGG(c.concepto, ' | ') AS conceptos_compra 
        FROM compras c 
        JOIN compra_participantes cp ON c.id = cp.compra_id 
        JOIN tarjetas t ON c.tarjeta_id = t.id 
        WHERE {condicion_c} 
        GROUP BY cp.persona_id, c.tarjeta_id
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
    
    # NUEVO: Para obtener el histórico global total y mostrarlo solo en las tarjetas métricas (Metrics)
    query_global = "SELECT SUM(monto_asignado) FROM compra_participantes"
    query_pagos_global = "SELECT SUM(monto) FROM pagos"
    tot_comp = consultar_datos(query_global).iloc[0,0] or 0.0
    tot_pag = consultar_datos(query_pagos_global).iloc[0,0] or 0.0
    deuda_historica_total = tot_comp - tot_pag

    df_categorias = consultar_datos(f"SELECT categoria, SUM(monto_total) as total FROM compras c WHERE {condicion_c} GROUP BY categoria")

    if not df_saldos.empty:
        c1, c2 = st.columns(2)
        c1.metric("💸 Deuda (Histórica Total)", f"${deuda_historica_total:,.2f}")
        c2.metric("🎯 Saldo del Filtro", f"${df_saldos['Saldo del Filtro'].sum():,.2f}")
        
        c3, c4 = st.columns(2)
        c3.metric("✅ Pagos (en Filtro)", f"${df_saldos['Pagos Filtro'].sum():,.2f}")
        c4.metric("📅 Activo", f"{mes_filtro} | {quincena_filtro[:3]}")
        st.divider()
        
        st.subheader("📋 Detalle de Saldos")
        # Se removió la deuda histórica del formato de la tabla
        st.dataframe(df_saldos.style.format({
            "Consumo Filtro": "${:.2f}", 
            "Pagos Filtro": "${:.2f}", 
            "Saldo del Filtro": "${:.2f}"
        }), use_container_width=True, hide_index=True)
            
        st.subheader("🛍️ Gastos por Categoría")
        if not df_categorias.empty:
            fig = px.pie(df_categorias, values='total', names='categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="%{label}: <br>$%{value:,.2f} <br>(%{percent})")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No hay movimientos registrados ni deudas para {quincena_filtro} de {mes_filtro}.")

# --- 1.5 PROYECCIONES ---
elif menu == "📈 Proyecciones":
    st.subheader("🔮 Radar de Pagos Futuros (MSI)")
    mes_actual = datetime.now().strftime("%Y-%m")
    
    q_proj = f"""
        SELECT TO_CHAR(c.fecha::DATE, 'YYYY-MM') AS mes, SUM(cp.monto_asignado) AS total
        FROM compras c
        JOIN compra_participantes cp ON c.id = cp.compra_id
        WHERE TO_CHAR(c.fecha::DATE, 'YYYY-MM') >= '{mes_actual}'
        GROUP BY TO_CHAR(c.fecha::DATE, 'YYYY-MM')
        ORDER BY TO_CHAR(c.fecha::DATE, 'YYYY-MM')
    """
    df_proj = consultar_datos(q_proj)
    
    if not df_proj.empty:
        st.info("Esta gráfica proyecta todo el dinero que ya debes en los próximos meses a causa de las compras a Meses Sin Intereses (MSI).")
        fig_proj = px.bar(df_proj, x='mes', y='total', text_auto='.2f', 
                          labels={'mes': 'Mes del Año', 'total': 'Deuda Comprometida ($)'},
                          color_discrete_sequence=['#ff4b4b'])
        fig_proj.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_proj, use_container_width=True)
    else:
        st.success("¡Felicidades! No hay compras a Meses Sin Intereses registradas para el futuro.")

# --- 2. COMPRAS ---
elif menu == "🛒 Registrar Compra":
    tarjetas = consultar_datos("SELECT id, nombre FROM tarjetas")
    personas = consultar_datos("SELECT id, nombre FROM personas")

    if not tarjetas.empty and not personas.empty:
        with st.expander("➕ Completar detalles de compra", expanded=True):
            concepto = st.text_input("Concepto (Ej. Chedraui, Netflix, Gym)")
            
            tipo_compra = st.radio("Tipo de Compra", ["Pago Único", "Meses Sin Intereses (MSI)", "Suscripción / Recurrente"], horizontal=True)
            
            if tipo_compra == "Meses Sin Intereses (MSI)":
                monto_ingresado = st.number_input("Monto TOTAL de la compra ($)", min_value=0.01, step=10.0, value=1200.0)
                meses = st.selectbox("Plazo (Meses)", [3, 6, 9, 12, 18, 24], index=0)
                monto_mensual = monto_ingresado / meses
                monto_validacion = monto_ingresado
                label_manual = "Pago TOTAL de"
            elif tipo_compra == "Suscripción / Recurrente":
                monto_ingresado = st.number_input("Monto MENSUAL de la suscripción ($)", min_value=0.01, step=10.0, value=150.0)
                meses = st.number_input("¿Cuántos meses quieres programar?", min_value=2, max_value=60, value=12)
                monto_mensual = monto_ingresado
                monto_validacion = monto_ingresado 
                label_manual = "Pago MENSUAL de"
            else: # Pago Único
                monto_ingresado = st.number_input("Monto Total ($)", min_value=0.01, step=10.0, value=100.0)
                meses = 1
                monto_mensual = monto_ingresado
                monto_validacion = monto_ingresado
                label_manual = "Pago de"

            categoria = st.selectbox("Categoría", ["Supermercado", "Restaurantes", "Servicios", "Suscripciones", "Ropa", "Transporte", "Otros"], index=3 if tipo_compra=="Suscripción / Recurrente" else 0)
            fecha = st.date_input("Fecha del primer cobro", datetime.today())
            tarjeta_sel = st.selectbox("Tarjeta", options=tarjetas["id"], format_func=lambda x: tarjetas.loc[tarjetas["id"]==x, "nombre"].values[0])
            st.write("👥 **¿Quiénes participan en la compra?**")
            cols_personas = st.columns(len(personas))
            participantes_sel = []
            
            for i, (_, row_p) in enumerate(personas.iterrows()):
                with cols_personas[i]:
                    if st.checkbox(row_p["nombre"], key=f"chk_{row_p['id']}"):
                        participantes_sel.append(row_p["id"])
            
            st.divider()
            tipo_division = st.radio("¿Cómo se paga?", ["Partes Iguales", "Monto Exacto por Persona"], horizontal=True)
            
            montos_manuales = {}
            if tipo_division == "Monto Exacto por Persona" and participantes_sel:
                for p_id in participantes_sel:
                    n_persona = personas.loc[personas["id"]==p_id, "nombre"].values[0]
                    montos_manuales[p_id] = st.number_input(f"{label_manual} {n_persona}", min_value=0.0, max_value=monto_validacion, step=10.0)

        if st.button("Guardar Compra 💾", use_container_width=True):
            if concepto and participantes_sel:
                suma_manual = sum(montos_manuales.values()) if montos_manuales else 0
                if tipo_division == "Monto Exacto por Persona" and abs(suma_manual - monto_validacion) > 0.1:
                    st.error(f"La suma de los pagos no coincide con el monto indicado (${monto_validacion:,.2f}).")
                else:
                    conn = conectar_bd()
                    cursor = conn.cursor()
                    
                    for mes_actual in range(meses):
                        fecha_registro = sumar_meses(fecha, mes_actual)
                        
                        if tipo_compra == "Meses Sin Intereses (MSI)":
                            concepto_final = f"{concepto} (Mes {mes_actual+1}/{meses})"
                        elif tipo_compra == "Suscripción / Recurrente":
                            concepto_final = f"{concepto} (Recurrente {mes_actual+1}/{meses})"
                        else:
                            concepto_final = concepto
                            
                        cursor.execute("INSERT INTO compras (concepto, categoria, monto_total, fecha, tarjeta_id) VALUES (%s, %s, %s, %s, %s) RETURNING id", 
                                       (concepto_final, categoria, monto_mensual, str(fecha_registro.date()), tarjeta_sel))
                        compra_id = cursor.fetchone()[0]
                        
                        for p_id in participantes_sel:
                            if tipo_division == "Partes Iguales":
                                cuota_persona = monto_mensual / len(participantes_sel)
                            else:
                                cuota_persona = montos_manuales[p_id] if tipo_compra == "Suscripción / Recurrente" else (montos_manuales[p_id] / meses)
                                
                            cursor.execute("INSERT INTO compra_participantes (compra_id, persona_id, monto_asignado) VALUES (%s, %s, %s)", 
                                           (compra_id, p_id, cuota_persona))
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.session_state.mensaje_exito = f"✨ ¡Compra '{concepto}' guardada!"
                    st.rerun()
    else:
        st.warning("⚠️ Primero añade tarjetas y personas en Ajustes.")

# --- 3. PAGOS Y DEVOLUCIONES ---
elif menu == "💸 Liquidar Deuda":
    tarjetas_pago = consultar_datos("SELECT id, nombre FROM tarjetas")
    personas_pago = consultar_datos("SELECT id, nombre FROM personas")

    if not tarjetas_pago.empty and not personas_pago.empty:
        p_pago = st.selectbox("¿Quién va a pagar?", options=personas_pago["id"], format_func=lambda x: personas_pago.loc[personas_pago["id"]==x, "nombre"].values[0])
        t_pago = st.selectbox("¿A qué tarjeta abona?", options=tarjetas_pago["id"], format_func=lambda x: tarjetas_pago.loc[tarjetas_pago["id"]==x, "nombre"].values[0])
        
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(cp.monto_asignado) FROM compra_participantes cp JOIN compras c ON cp.compra_id = c.id WHERE cp.persona_id = %s AND c.tarjeta_id = %s", (p_pago, t_pago))
        total_comprado = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT SUM(monto) FROM pagos WHERE persona_id = %s AND tarjeta_id = %s", (p_pago, t_pago))
        total_pagado = cursor.fetchone()[0] or 0.0
        conn.close()
        
        deuda_actual = total_comprado - total_pagado
        if deuda_actual > 0: 
            st.info(f"💰 Deuda actual: **${deuda_actual:,.2f}**")
        else: 
            st.success("✅ Sin deudas pendientes en esta tarjeta.")
            
        with st.expander("Detalles del Abono / Devolución", expanded=True):
            concepto_pago = st.text_input("Concepto (Opcional)", value="Abono a deuda", help="Modifícalo si fue una Devolución, Reembolso, o quieres especificar la quincena.")
            tipo_pago = st.radio("¿Cuánto va a abonar?", ["Liquidar deuda completa", "Abonar un monto específico"])
            m_pago = deuda_actual if tipo_pago == "Liquidar deuda completa" else st.number_input("Monto ($)", min_value=0.01, step=50.0, value=float(min(500.0, max(0.01, deuda_actual))))
            f_pago = st.date_input("Fecha del Pago", datetime.today())
        
        if st.button("Registrar Movimiento ✅", use_container_width=True):
            if m_pago > 0:
                conn = conectar_bd()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pagos (persona_id, tarjeta_id, monto, fecha, concepto) VALUES (%s, %s, %s, %s, %s)", (p_pago, t_pago, m_pago, str(f_pago), concepto_pago))
                conn.commit()
                conn.close()
                st.cache_data.clear() 
                st.session_state.mensaje_exito = f"✅ Movimiento de ${m_pago:,.2f} registrado."
                st.rerun()

# --- 4. REPORTES ---
elif menu == "📝 Reportes":
    tarjetas_disp = consultar_datos("SELECT id, nombre FROM tarjetas")
    nombres_tarjetas = ["Todas"] + tarjetas_disp['nombre'].tolist() if not tarjetas_disp.empty else ["Todas"]

    with st.expander("🔍 Filtros de Búsqueda", expanded=True):
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1:
            mes_filtro = st.text_input("Mes (YYYY-MM) - Vacio para todos", value=datetime.now().strftime("%Y-%m"), key="rep_mes")
        with c_f2:
            quincena_filtro = st.selectbox("Quincena", ["Todas", "1ra Quincena (1-15)", "2da Quincena (16-31)"], key="rep_quin")
        with c_f3:
            tarjeta_filtro = st.selectbox("Tarjeta", nombres_tarjetas, key="rep_tarj")

    # Misma fórmula SQL proyectiva que usamos en el Dashboard
    calc_pago = "(DATE_TRUNC('month', c.fecha) + (CASE WHEN EXTRACT(DAY FROM c.fecha) > t.dia_corte THEN 1 ELSE 0 END + CASE WHEN t.dia_pago <= t.dia_corte THEN 1 ELSE 0 END) * INTERVAL '1 month' + (t.dia_pago - 1) * INTERVAL '1 day')::DATE"

    cond_c, cond_p = "1=1", "1=1"
    if mes_filtro.strip():
        cond_c += f" AND TO_CHAR({calc_pago}, 'YYYY-MM') = '{mes_filtro}'"
        cond_p += f" AND TO_CHAR(pa.fecha::DATE, 'YYYY-MM') = '{mes_filtro}'"
    if "1ra" in quincena_filtro:
        cond_c += f" AND EXTRACT(DAY FROM {calc_pago}) <= 15"
        cond_p += " AND EXTRACT(DAY FROM pa.fecha::DATE) <= 15"
    elif "2da" in quincena_filtro:
        cond_c += f" AND EXTRACT(DAY FROM {calc_pago}) > 15"
        cond_p += " AND EXTRACT(DAY FROM pa.fecha::DATE) > 15"
        
    if tarjeta_filtro != "Todas":
        cond_c += f" AND t.nombre = '{tarjeta_filtro}'"
        cond_p += f" AND t.nombre = '{tarjeta_filtro}'"

    # Seleccionamos el Mes y Quincena proyectados, pero mantenemos c.fecha visible para que sepas cuándo se compró realmente
    q_det = f"""
    SELECT 
        TO_CHAR({calc_pago}, 'YYYY-MM') AS mes,
        CASE WHEN EXTRACT(DAY FROM {calc_pago}) <= 15 THEN '1ra Quincena' ELSE '2da Quincena' END AS quincena,
        c.fecha AS fecha, p.nombre AS persona, t.nombre AS tarjeta, c.concepto AS concepto, 'Compra' AS tipo, cp.monto_asignado AS monto
    FROM compras c 
    JOIN tarjetas t ON c.tarjeta_id = t.id 
    JOIN compra_participantes cp ON c.id = cp.compra_id 
    JOIN personas p ON cp.persona_id = p.id
    WHERE {cond_c}
    UNION ALL
    SELECT 
        TO_CHAR(pa.fecha::DATE, 'YYYY-MM') AS mes,
        CASE WHEN EXTRACT(DAY FROM pa.fecha::DATE) <= 15 THEN '1ra Quincena' ELSE '2da Quincena' END AS quincena,
        pa.fecha AS fecha, p.nombre AS persona, t.nombre AS tarjeta, COALESCE(pa.concepto, 'Abono a deuda') AS concepto, 'Pago' AS tipo, pa.monto AS monto
    FROM pagos pa 
    JOIN tarjetas t ON pa.tarjeta_id = t.id 
    JOIN personas p ON pa.persona_id = p.id
    WHERE {cond_p}
    ORDER BY fecha DESC
    """
    
    df_rep = consultar_datos(q_det)

    if not df_rep.empty:
        df_rep.columns = [col.capitalize() for col in df_rep.columns]
        
        st.dataframe(
            df_rep.style.format({"Monto": "${:.2f}"}).map(
                lambda v: 'background-color: #ffcdd2; color: black' if v == 'Compra' else 'background-color: #c8e6c9; color: black', 
                subset=['Tipo']
            ), 
            use_container_width=True, 
            hide_index=True
        )
        st.download_button("Descargar Estado de Cuenta", data=df_rep.to_csv(index=False).encode('utf-8'), file_name="estado_cuenta.csv", mime="text/csv", use_container_width=True)
        
        st.divider()
        st.subheader("💬 Generar WhatsApp")
        
        # Poblamos el selector usando directamente la tabla filtrada
        p_wa = st.selectbox("Selecciona para generar cobro:", df_rep['Persona'].unique())
        df_filtro = df_rep[df_rep['Persona'] == p_wa]
        
        # NUEVO: Calculamos los totales sumando EXACTAMENTE lo que aparece filtrado
        tot_consumido = df_filtro[df_filtro['Tipo'] == 'Compra']['Monto'].sum()
        tot_abonado = df_filtro[df_filtro['Tipo'] == 'Pago']['Monto'].sum()
        saldo_pendiente = tot_consumido - tot_abonado
        
        tarjeta_msg = f" en la tarjeta {tarjeta_filtro}" if tarjeta_filtro != "Todas" else ""
        msg = f"Hola {p_wa}, este es tu estado de cuenta filtrado{tarjeta_msg}:\n\n"
        
        periodos = df_filtro[['Mes', 'Quincena']].drop_duplicates().sort_values(by=['Mes', 'Quincena'])
        for _, row in periodos.iterrows():
            m, q = row['Mes'], row['Quincena']
            msg += f"📅 *{m} | {q}*\n"
            for _, f in df_filtro[(df_filtro['Mes'] == m) & (df_filtro['Quincena'] == q)].iterrows():
                msg += f"  {'🛒' if f['Tipo']=='Compra' else '✅'} {f['Concepto']} ({f['Tarjeta']}): {'-' if f['Tipo']=='Pago' else ''}${f['Monto']:.2f}\n"
            msg += "\n"
        
        # Usamos las nuevas variables filtradas para el mensaje
        msg += f"💰 *Total Consumido:* ${tot_consumido:.2f}\n💰 *Total Abonado:* ${tot_abonado:.2f}\n"
        if saldo_pendiente > 0: msg += f"👉 *SALDO PENDIENTE: ${saldo_pendiente:.2f}*"
        elif saldo_pendiente < 0: msg += f"✨ *SALDO A FAVOR: ${abs(saldo_pendiente):.2f}*"
        else: msg += "✅ *CUENTA LIQUIDADA*"
        
        st.divider()
        st.write("📱 **Enviar por WhatsApp Automáticamente**")
        
        if st.button("Enviar Cobro al Grupo 🚀", use_container_width=True, type="primary"):
            with st.spinner("Enviando mensaje al grupo..."):
                url = st.secrets.get("GREEN_API_URL", "")
                grupo_id = st.secrets.get("WHATSAPP_GROUP_ID", "")
                
                if url and grupo_id:
                    payload = {"chatId": f"{grupo_id}@g.us", "message": msg}
                    try:
                        respuesta = requests.post(url, json=payload, verify=False)
                        if respuesta.status_code == 200:
                            st.success("✅ ¡Mensaje enviado exitosamente al grupo!")
                        else:
                            st.error(f"❌ Error al enviar. Código: {respuesta.status_code}")
                    except Exception as e:
                        st.error(f"❌ Ocurrió un error de conexión: {e}")
                else:
                    st.error("Faltan credenciales de WhatsApp en secrets.toml")
                    
        with st.expander("Ver texto generado (Respaldo manual)"):
            st.code(msg, language="text")
    else:
        st.info("📭 No hay movimientos para los filtros seleccionados.")

# --- 5. GESTIÓN (EDITAR / BORRAR) ---
elif menu == "🛠️ Gestionar":
    import re 
    
    tipo_gestion = st.radio("¿Qué deseas gestionar?", ["🛒 Compras", "💸 Pagos / Abonos"], horizontal=True)
    
    if tipo_gestion == "🛒 Compras":
        df_del = consultar_datos("SELECT c.id, c.fecha, c.concepto, c.monto_total, c.tarjeta_id, t.nombre as tarjeta FROM compras c JOIN tarjetas t ON c.tarjeta_id = t.id ORDER BY c.fecha DESC")
        
        if not df_del.empty:
            df_del.columns = [col.capitalize() for col in df_del.columns]
            opciones = [f"ID: {r['Id']} | {r['Fecha']} | {r['Concepto']} | ${r['Monto_total']} ({r['Tarjeta']})" for _, r in df_del.iterrows()]
            seleccion = st.selectbox("Selecciona un movimiento:", opciones)
            id_seleccionado = seleccion.split(" | ")[0].replace("ID: ", "")
            
            fila_actual = df_del[df_del['Id'] == int(id_seleccionado)].iloc[0]
            
            t_editar, t_eliminar = st.tabs(["✏️ Editar Datos", "🗑️ Eliminar Registro"])
            
            with t_editar:
                with st.form("form_editar"):
                    st.info("💡 Solo puedes editar nombre y fecha. Para cambiar montos, elimina el registro y vuelve a crearlo.")
                    nuevo_concepto = st.text_input("Concepto", value=fila_actual['Concepto'])
                    nueva_fecha = st.date_input("Fecha", pd.to_datetime(fila_actual['Fecha']))
                    
                    if st.form_submit_button("Guardar Cambios 💾", use_container_width=True):
                        conn = conectar_bd()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE compras SET concepto=%s, fecha=%s WHERE id=%s", (nuevo_concepto, str(nueva_fecha), id_seleccionado))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()
                        st.session_state.mensaje_exito = "✏️ Registro actualizado."
                        st.rerun()
                        
            with t_eliminar:
                es_serie = bool(re.search(r" \((Mes|Recurrente) \d+/\d+\)$", fila_actual['Concepto']))
                
                if es_serie:
                    base_concepto = re.sub(r" \((Mes|Recurrente) \d+/\d+\)$", "", fila_actual['Concepto'])
                    st.warning(f"⚠️ Esta compra es parte de una serie programada: **{base_concepto}**")
                    tipo_borrado = st.radio("¿Qué deseas borrar?", ["Borrar SOLO este mes", "Borrar TODA la serie"])
                else:
                    tipo_borrado = "Borrar SOLO este mes"
                    base_concepto = ""
                    
                if st.button("🚨 Eliminar Compra Definitivamente", use_container_width=True, type="primary"):
                    conn = conectar_bd()
                    cursor = conn.cursor()
                    
                    if es_serie and tipo_borrado == "Borrar TODA la serie":
                        cursor.execute("DELETE FROM compras WHERE concepto LIKE %s AND tarjeta_id = %s", (f"{base_concepto} (%", int(fila_actual['Tarjeta_id'])))
                        st.session_state.mensaje_exito = f"🗑 Serie completa de '{base_concepto}' eliminada."
                    else:
                        cursor.execute("DELETE FROM compras WHERE id = %s", (id_seleccionado,))
                        st.session_state.mensaje_exito = "🗑 Compra individual eliminada."
                        
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info("📭 Aún no hay compras registradas para gestionar.")
            
    else: 
        df_del_p = consultar_datos("SELECT pa.id, pa.fecha, pa.concepto, pa.monto, p.nombre as persona, t.nombre as tarjeta FROM pagos pa JOIN personas p ON pa.persona_id = p.id JOIN tarjetas t ON pa.tarjeta_id = t.id ORDER BY pa.fecha DESC")
        
        if not df_del_p.empty:
            df_del_p.columns = [col.capitalize() for col in df_del_p.columns]
            opciones_p = [f"ID: {r['Id']} | {r['Fecha']} | {r['Persona']} abonó ${r['Monto']} ({r['Concepto']})" for _, r in df_del_p.iterrows()]
            seleccion_p = st.selectbox("Selecciona el abono a eliminar:", opciones_p)
            id_p_seleccionado = seleccion_p.split(" | ")[0].replace("ID: ", "")
            
            if st.button("🚨 Eliminar Abono Definitivamente", use_container_width=True, type="primary"):
                conn = conectar_bd()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM pagos WHERE id = %s", (id_p_seleccionado,))
                conn.commit()
                conn.close()
                st.cache_data.clear()
                st.session_state.mensaje_exito = "🗑️ Abono eliminado."
                st.rerun()
        else:
            st.info("📭 Aún no hay abonos registrados para gestionar.")

# --- 6. AJUSTES ---
elif menu == "⚙️ Ajustes":
    st.subheader("💳 Tarjetas Registradas")
    
    df_tarjetas = consultar_datos("SELECT id as \"ID\", nombre as \"Tarjeta\", dia_corte as \"Día de Corte\", dia_pago as \"Día de Pago\" FROM tarjetas ORDER BY id ASC")
    
    if not df_tarjetas.empty:
        st.dataframe(df_tarjetas, use_container_width=True, hide_index=True)
    else:
        st.info("📭 Aún no hay tarjetas registradas.")
        
    st.divider()

    # 1. Agregar Tarjeta
    with st.expander("➕ Añadir Nueva Tarjeta", expanded=False):
        with st.form("form_tarjeta", clear_on_submit=True):
            n_t = st.text_input("Nombre de la Tarjeta")
            col_corte, col_pago = st.columns(2)
            with col_corte: corte = st.number_input("Día de Corte", 1, 31, 15)
            with col_pago: pago = st.number_input("Día de Pago", 1, 31, 5)
                
            if st.form_submit_button("Guardar Tarjeta", use_container_width=True) and n_t.strip():
                conn = conectar_bd()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO tarjetas (nombre, dia_corte, dia_pago) VALUES (%s, %s, %s)", (n_t, corte, pago))
                conn.commit()
                conn.close()
                st.cache_data.clear()
                st.session_state.mensaje_exito = f"💳 Tarjeta '{n_t}' agregada."
                st.rerun()

    # NUEVO: 2. Gestionar Tarjeta (Editar / Borrar)
    with st.expander("🛠️ Gestionar Tarjetas Existentes", expanded=False):
        if not df_tarjetas.empty:
            opciones_t = [f"ID: {r['ID']} | {r['Tarjeta']}" for _, r in df_tarjetas.iterrows()]
            seleccion_t = st.selectbox("Selecciona la tarjeta a modificar o eliminar:", opciones_t)
            id_t_sel = seleccion_t.split(" | ")[0].replace("ID: ", "")
            
            fila_t = df_tarjetas[df_tarjetas['ID'] == int(id_t_sel)].iloc[0]
            
            t_editar_t, t_eliminar_t = st.tabs(["✏️ Editar Tarjeta", "🗑️ Eliminar Tarjeta"])
            
            with t_editar_t:
                with st.form("form_editar_tarjeta"):
                    nuevo_nombre_t = st.text_input("Nombre de la Tarjeta", value=fila_t['Tarjeta'])
                    c_corte, c_pago = st.columns(2)
                    with c_corte: 
                        nuevo_corte = st.number_input("Nuevo Día de Corte", 1, 31, int(fila_t['Día de Corte']))
                    with c_pago: 
                        nuevo_pago = st.number_input("Nuevo Día de Pago", 1, 31, int(fila_t['Día de Pago']))
                    
                    if st.form_submit_button("Guardar Cambios 💾", use_container_width=True):
                        conn = conectar_bd()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE tarjetas SET nombre=%s, dia_corte=%s, dia_pago=%s WHERE id=%s", (nuevo_nombre_t, nuevo_corte, nuevo_pago, id_t_sel))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()
                        st.session_state.mensaje_exito = f"✏️ Tarjeta '{nuevo_nombre_t}' actualizada correctamente."
                        st.rerun()
                        
            with t_eliminar_t:
                st.warning("⚠️ **¡ADVERTENCIA CRÍTICA!** Eliminar una tarjeta borrará AUTOMÁTICAMENTE y para siempre todas las compras y abonos vinculados a ella.")
                seguro_t = st.checkbox("Entiendo que esto borrará el historial de esta tarjeta", key="chk_del_t")
                if st.button("🚨 Eliminar Tarjeta Definitivamente", use_container_width=True, type="primary", disabled=not seguro_t):
                    conn = conectar_bd()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM tarjetas WHERE id = %s", (id_t_sel,))
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.session_state.mensaje_exito = "🗑️ Tarjeta y todo su historial eliminados."
                    st.rerun()
        else:
            st.info("📭 No hay tarjetas para gestionar.")

    # 3. Zona de Peligro Global
    with st.expander("⚠️ Zona de Peligro (Empezar de 0)", expanded=False):
        st.warning("Esto borrará permanentemente TODAS las compras y abonos. Las tarjetas y personas se mantendrán.")
        
        seguro = st.checkbox("Entiendo que esto no se puede deshacer", key="chk_reset_global")
        
        if st.button("🗑️ Reiniciar Historial Financiero", use_container_width=True, type="primary", disabled=not seguro):
            conn = conectar_bd()
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE compras, pagos, compra_participantes RESTART IDENTITY CASCADE;")
            conn.commit()
            conn.close()
            st.cache_data.clear()
            st.session_state.mensaje_exito = "✨ Base de datos reiniciada. ¡Listo para usar en el mundo real!"
            st.rerun()