import os
import sys
import inspect
import base64
import streamlit as st
from PIL import Image

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Carrega a nova logo V&B para o Favicon da aba com segurança via Pillow
logo_path = os.path.join(ROOT_DIR, "logo_vb.png")
favicon_img = Image.open(logo_path) if os.path.exists(logo_path) else None

st.set_page_config(
    page_title="V&B Strategic Sourcing",
    page_icon=favicon_img if favicon_img else "🔺",
    layout="wide",
    initial_sidebar_state="expanded"
)

import database as db

# Importações seguras dos módulos reais da pasta 'modulos'
try:
    from modulos import compras_modulo as compras
    from modulos import saving_projetos
    from modulos import estoque
    from modulos import configuracoes
except ImportError:
    try:
        import compras_modulo as compras
        import saving_projetos
        import estoque
        import configuracoes
    except ImportError:
        compras = saving_projetos = estoque = configuracoes = None

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

# Estado global para controlar a página ativa unificada
if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "🛒 Compras"


# ---------------------------------------------------------
# UTILITÁRIO: CONVERSÃO DA LOGO PARA BASE64 (USADO NOS PEDIDOS)
# ---------------------------------------------------------
def get_logo_base64():
    """Converte o arquivo logo_vb.png em string Base64 para uso direto em templates HTML/PDF."""
    path = os.path.join(ROOT_DIR, "logo_vb.png")
    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    return ""


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
            path_logo_login = os.path.join(ROOT_DIR, "logo_vb.png")
            if os.path.exists(path_logo_login):
                st.image(path_logo_login, width=70)
                
        with col_t:
            st.markdown("<h2 style='color: #38bdf8; margin: 0px; line-height: 1.1;'>Portal V&B</h2>", unsafe_allow_html=True)
            st.markdown("<p style='color: #94a3b8; margin: 0px; font-size: 13px;'>Strategic Sourcing</p>", unsafe_allow_html=True)
        
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
# EXECUTOR BLINDADO
# ---------------------------------------------------------
def executar_modulo(modulo, perfil):
    if not modulo:
        st.error("Módulo não encontrado.")
        return

    for nome_func in ['render', 'main', 'run', 'app', 'exibir', 'tela_compras']:
        if hasattr(modulo, nome_func):
            func = getattr(modulo, nome_func)
            if callable(func):
                try:
                    func(perfil)
                    return
                except TypeError:
                    try:
                        func()
                        return
                    except Exception as e:
                        st.error(f"Erro na função '{nome_func}':")
                        st.exception(e)
                        return
                except Exception as e:
                    st.error(f"Erro na função '{nome_func}':")
                    st.exception(e)
                    return

    funcoes_excluidas = ['get_db_connection', 'init_db', 'conectar', 'query', 'db_connect', 'carregar_dados']
    funcs = [
        o for o in inspect.getmembers(modulo, inspect.isfunction) 
        if not o[0].startswith('_') 
        and o[0] not in funcoes_excluidas 
        and o[1].__module__ == modulo.__name__
    ]

    if funcs:
        func = funcs[0][1]
        try:
            func(perfil)
            return
        except TypeError:
            try:
                func()
                return
            except Exception as e:
                st.error(f"Erro na função '{funcs[0][0]}':")
                st.exception(e)
                return
        except Exception as e:
            st.error(f"Erro na função '{funcs[0][0]}':")
            st.exception(e)
            return

    st.error("O arquivo foi carregado, mas nenhuma função de renderização válida foi identificada.")


# ---------------------------------------------------------
# PAINEL PRINCIPAL & NAVEGAÇÃO UNIFICADA
# ---------------------------------------------------------
def painel_principal():
    perfil_atual = st.session_state["perfil"]

    with st.sidebar:
        col_img, col_txt = st.columns([1, 3])
        with col_img:
            path_logo_side = os.path.join(ROOT_DIR, "logo_vb.png")
            if os.path.exists(path_logo_side):
                st.image(path_logo_side, width=35)
        with col_txt:
            st.markdown("##### Portal V&B")
        st.caption("Strategic Sourcing")
        st.divider()

        st.markdown("##### 🧭 Navegação")

        if perfil_atual == "Gestão Geral":
            if st.button("📊 Saving & Projetos", use_container_width=True, type="primary" if st.session_state["pagina_ativa"] == "📊 Saving & Projetos" else "secondary"):
                st.session_state["pagina_ativa"] = "📊 Saving & Projetos"
                st.rerun()

        if st.button("🛒 Compras", use_container_width=True, type="primary" if st.session_state["pagina_ativa"] == "🛒 Compras" else "secondary"):
            st.session_state["pagina_ativa"] = "🛒 Compras"
            st.rerun()

        if st.button("📦 Estoque", use_container_width=True, type="primary" if st.session_state["pagina_ativa"] == "📦 Estoque" else "secondary"):
            st.session_state["pagina_ativa"] = "📦 Estoque"
            st.rerun()

        if st.button("⚙️ Configurações", use_container_width=True, type="primary" if st.session_state["pagina_ativa"] == "⚙️ Configurações" else "secondary"):
            st.session_state["pagina_ativa"] = "⚙️ Configurações"
            st.rerun()

        st.markdown("<br>" * 4, unsafe_allow_html=True)
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
            st.session_state["pagina_ativa"] = "🛒 Compras"
            st.query_params.clear()
            st.rerun()

    modulo_sel = st.session_state["pagina_ativa"]

    if modulo_sel == "🛒 Compras":
        executar_modulo(compras, perfil_atual)
    elif modulo_sel == "📊 Saving & Projetos":
        if perfil_atual == "Gestão Geral":
            executar_modulo(saving_projetos, perfil_atual)
        else:
            st.error("Acesso não autorizado.")
    elif modulo_sel == "📦 Estoque":
        executar_modulo(estoque, perfil_atual)
    elif modulo_sel == "⚙️ Configurações":
        executar_modulo(configuracoes, perfil_atual)
    else:
        executar_modulo(compras, perfil_atual)


# ---------------------------------------------------------
# EXECUÇÃO DA APLICAÇÃO
# ---------------------------------------------------------
if not st.session_state["logged_in"]:
    tela_login()
else:
    painel_principal()
