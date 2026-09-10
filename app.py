import os
import sys
import streamlit as st

st.set_page_config(
    page_title="Portal Delta - Suprimentos & Estoque",
    page_icon="logo_delta.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import database as db

# Importações blindadas contra qualquer variação de nome de arquivo
def safe_import(module_names):
    for name in module_names:
        try:
            return __import__(name, fromlist=['*'])
        except ImportError:
            continue
    return None

compras = safe_import(['compras', 'modulo_compras', 'modulos.compras', 'modulos.modulo_compras'])
saving_projetos = safe_import(['saving_projetos', 'modulos.saving_projetos'])
estoque = safe_import(['estoque', 'modulos.estoque'])
almoxarife = safe_import(['almoxarife', 'modulos.almoxarife'])
configuracoes = safe_import(['configuracoes', 'modulos.configuracoes'])

# Inicializa banco de dados e estrutura de tabelas
try:
    db.init_db()
except Exception as e:
    st.error(f"Erro ao inicializar banco de dados: {e}")

# Gerenciamento de Estado da Sessão
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = ""
if "perfil" not in st.session_state:
    st.session_state["perfil"] = "Consulta"
if "permissoes" not in st.session_state:
    st.session_state["permissoes"] = {}


# ---------------------------------------------------------
# AUTO-RECOVERY DA SESSÃO VIA URL (EVITA LOGOUT NO RAILWAY)
# ---------------------------------------------------------
def tentar_restaurar_sessao_url():
    if not st.session_state["logged_in"]:
        usuario_token = st.query_params.get("user_token", None)
        if usuario_token:
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, perfil, pode_ver_saving, pode_importar_saving, 
                           pode_gerenciar_budgets, pode_consultar_estoque, pode_dar_entrada_estoque, 
                           pode_dar_baixa_estoque, pode_enderecar_estoque, pode_transferir_estoque, 
                           pode_estornar_estoque, e_admin
                    FROM usuarios 
                    WHERE LOWER(username) = LOWER(%s);
                """, (usuario_token.strip(),))
                
                user = cursor.fetchone()
                cursor.close()
                conn.close()

                if user:
                    st.session_state["logged_in"] = True
                    st.session_state["usuario_logado"] = user[0]
                    st.session_state["perfil"] = user[1]
                    st.session_state["permissoes"] = {
                        "pode_ver_saving": user[2],
                        "pode_importar_saving": user[3],
                        "pode_gerenciar_budgets": user[4],
                        "pode_consultar_estoque": user[5],
                        "pode_dar_entrada_estoque": user[6],
                        "pode_dar_baixa_estoque": user[7],
                        "pode_enderecar_estoque": user[8],
                        "pode_transferir_estoque": user[9],
                        "pode_estornar_estoque": user[10],
                        "e_admin": user[11]
                    }
            except Exception:
                pass

tentar_restaurar_sessao_url()


# ---------------------------------------------------------
# TELA DE LOGIN
# ---------------------------------------------------------
def tela_login():
    st.markdown("""
        <style>
        .stApp {
            background-color: #0e1117;
        }
        div[data-testid="stForm"] {
            background-color: #161b22;
            padding: 30px;
            border-radius: 12px;
            border: 1px solid #30363d;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
            max-width: 450px;
            margin: 0 auto;
        }
        </style>
    """, unsafe_allow_html=True)

    _, col_centro, _ = st.columns([1, 1.4, 1])
    
    with col_centro:
        _, col_l, col_t, _ = st.columns([0.2, 0.8, 2.2, 0.2])
        
        with col_l:
            if os.path.exists("logo_delta.png"):
                st.image("logo_delta.png", width=70)
                
        with col_t:
            st.markdown("<h2 style='color: #38bdf8; margin: 0px; line-height: 1.1;'>Portal Delta</h2>", unsafe_allow_html=True)
            st.markdown("<p style='color: #94a3b8; margin: 0px; font-size: 13px;'>Suprimentos & Estoque</p>", unsafe_allow_html=True)
        
        st.write("")
        
        with st.form("form_login_portal", clear_on_submit=False):
            st.markdown("<h4 style='color: #f0f6fc; margin-bottom: 15px;'>🔐 Acesso ao Sistema</h4>", unsafe_allow_html=True)
            
            usuario_input = st.text_input("Usuário *", placeholder="Digite seu usuário").strip()
            senha_input = st.text_input("Senha *", type="password", placeholder="Digite sua senha").strip()
            
            btn_entrar = st.form_submit_button("Entrar no Portal", type="primary", use_container_width=True)

        if btn_entrar:
            if usuario_input and senha_input:
                try:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT username, perfil, password, pode_ver_saving, pode_importar_saving, 
                               pode_gerenciar_budgets, pode_consultar_estoque, pode_dar_entrada_estoque, 
                               pode_dar_baixa_estoque, pode_enderecar_estoque, pode_transferir_estoque, 
                               pode_estornar_estoque, e_admin
                        FROM usuarios 
                        WHERE LOWER(username) = LOWER(%s);
                    """, (usuario_input,))
                    
                    user = cursor.fetchone()
                    
                    if user and user[2] == senha_input:
                        st.session_state["logged_in"] = True
                        st.session_state["usuario_logado"] = user[0]
                        st.session_state["perfil"] = user[1]
                        
                        st.session_state["permissoes"] = {
                            "pode_ver_saving": user[3],
                            "pode_importar_saving": user[4],
                            "pode_gerenciar_budgets": user[5],
                            "pode_consultar_estoque": user[6],
                            "pode_dar_entrada_estoque": user[7],
                            "pode_dar_baixa_estoque": user[8],
                            "pode_enderecar_estoque": user[9],
                            "pode_transferir_estoque": user[10],
                            "pode_estornar_estoque": user[11],
                            "e_admin": user[12]
                        }

                        st.query_params["user_token"] = user[0]

                        try:
                            cursor.execute("INSERT INTO historico_logins (username, perfil) VALUES (%s, %s);", (user[0], user[1]))
                            conn.commit()
                        except Exception:
                            pass

                        cursor.close()
                        conn.close()

                        st.success("Login efetuado com sucesso!")
                        st.rerun()
                    else:
                        if cursor:
                            cursor.close()
                        conn.close()
                        st.error("Usuário ou senha incorretos.")
                except Exception as ex:
                    st.error(f"Erro ao conectar e autenticar: {ex}")
            else:
                st.warning("Por favor, preencha o usuário e a senha.")


# ---------------------------------------------------------
# PAINEL PRINCIPAL & NAVEGAÇÃO
# ---------------------------------------------------------
def painel_principal():
    perfil_atual = st.session_state["perfil"]

    with st.sidebar:
        col_img, col_txt = st.columns([1, 3])
        with col_img:
            if os.path.exists("logo_delta.png"):
                st.image("logo_delta.png", width=35)
        with col_txt:
            st.markdown("##### Portal Delta")
        st.caption("Suprimentos & Estoque")
        st.divider()

        st.markdown("### Navegação do Sistema")

        opcoes_menu = ["🛒 Módulo de Compras", "📦 Controle de Estoque", "📍 Endereçamento (Almoxarifado)"]
        
        if perfil_atual == "Gestão Geral":
            opcoes_menu.insert(0, "📊 Saving & Projetos")

        opcoes_menu.append("⚙️ Configurações")

        modulo_sel = st.radio("Selecione o Módulo:", opcoes_menu, label_visibility="collapsed")

        st.markdown("<br>" * 8, unsafe_allow_html=True)
        st.divider()

        col_avatar, col_info = st.columns([1, 3])
        with col_avatar:
            inicial = st.session_state['usuario_logado'][0].upper() if st.session_state['usuario_logado'] else "U"
            st.markdown(f"**[{inicial}]**")
        with col_info:
            st.markdown(f"**{st.session_state['usuario_logado']}**")
            st.caption(f"Perfil: {perfil_atual}")

        if st.button("🚪 Sair / Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["usuario_logado"] = ""
            st.session_state["perfil"] = "Consulta"
            st.session_state["permissoes"] = {}
            st.query_params.clear()
            st.rerun()

    # Roteamento seguro dos Módulos
    if modulo_sel == "🛒 Módulo de Compras":
        if compras and hasattr(compras, 'render'):
            compras.render(perfil_atual)
        else:
            st.error("O módulo de compras não foi carregado corretamente.")
    elif modulo_sel == "📊 Saving & Projetos":
        if perfil_atual == "Gestão Geral":
            if saving_projetos and hasattr(saving_projetos, 'render'):
                saving_projetos.render(perfil_atual)
            else:
                st.error("O módulo de saving não foi encontrado.")
        else:
            st.error("Acesso não autorizado.")
    elif modulo_sel == "📦 Controle de Estoque":
        if estoque and hasattr(estoque, 'render'):
            estoque.render(perfil_atual)
        else:
            st.error("O módulo de estoque não foi encontrado.")
    elif modulo_sel == "📍 Endereçamento (Almoxarifado)":
        if almoxarife and hasattr(almoxarife, 'render_enderecamento'):
            almoxarife.render_enderecamento()
        else:
            st.error("O módulo de almoxarifado não foi encontrado.")
    elif modulo_sel == "⚙️ Configurações":
        if configuracoes and hasattr(configuracoes, 'render'):
            configuracoes.render(perfil_atual)
        else:
            st.error("O módulo de configurações não foi encontrado.")


# ---------------------------------------------------------
# EXECUÇÃO DA APLICAÇÃO
# ---------------------------------------------------------
if not st.session_state["logged_in"]:
    tela_login()
else:
    painel_principal()
