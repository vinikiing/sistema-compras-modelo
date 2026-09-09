import os
import sys
import database as db
import streamlit as st

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def carregar_dados_usuario(username):
    """Busca as permissões do usuário no banco de dados pelo nome do usuário."""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT username, perfil, 
                   pode_ver_saving, 
                   pode_importar_saving, 
                   pode_gerenciar_budgets,
                   pode_consultar_estoque, 
                   pode_dar_entrada_estoque, 
                   pode_dar_baixa_estoque,
                   pode_enderecar_estoque, 
                   pode_transferir_estoque, 
                   pode_estornar_estoque,
                   pode_ver_relatorios, 
                   e_admin
            FROM usuarios 
            WHERE LOWER(username) = LOWER(%s);
        """,
            (username.strip(),),
        )

        usr_data = cursor.fetchone()
        cursor.close()
        conn.close()
        return usr_data
    except Exception:
        return None


def aplicar_sessao_usuario(usr_data):
    """Guarda os dados do usuário no session_state e grava o login na URL."""
    perfil_base = usr_data[1]

    is_consulta = perfil_base == "Consulta"
    is_fiscal = perfil_base == "Fiscal"
    is_almoxarife = perfil_base == "Almoxarife"
    is_comprador = perfil_base == "Comprador"
    is_gestor = perfil_base in ["Gestor", "Gestão Geral"]
    is_admin_geral = perfil_base == "Gestão Geral"

    st.session_state["logado"] = True
    st.session_state["usuario_logado"] = usr_data[0]
    st.session_state["perfil"] = perfil_base

    st.session_state["permissoes"] = {
        "pode_ver_saving": (
            usr_data[2]
            if usr_data[2] is not None
            else (not is_consulta and not is_almoxarife and not is_fiscal)
        ),
        "pode_importar_saving": (
            usr_data[3]
            if usr_data[3] is not None
            else (is_comprador or is_gestor)
        ),
        "pode_gerenciar_budgets": (
            usr_data[4] if usr_data[4] is not None else is_gestor
        ),
        "pode_consultar_estoque": (
            usr_data[5] if usr_data[5] is not None else True
        ),
        "pode_dar_entrada_estoque": (
            usr_data[6]
            if usr_data[6] is not None
            else (is_fiscal or is_admin_geral)
        ),
        "pode_dar_baixa_estoque": (
            usr_data[7]
            if usr_data[7] is not None
            else (is_almoxarife or is_admin_geral)
        ),
        "pode_enderecar_estoque": (
            usr_data[8]
            if usr_data[8] is not None
            else (is_almoxarife or is_admin_geral)
        ),
        "pode_transferir_estoque": (
            usr_data[9]
            if usr_data[9] is not None
            else (is_almoxarife or is_admin_geral)
        ),
        "pode_estornar_estoque": (
            usr_data[10]
            if usr_data[10] is not None
            else (is_fiscal or is_admin_geral)
        ),
        "pode_ver_relatorios": (
            usr_data[11] if usr_data[11] is not None else not is_consulta
        ),
        "e_admin": usr_data[12] if usr_data[12] is not None else is_admin_geral,
    }

    # PERSISTÊNCIA NA URL (MANTÉM CONECTADO MESMO SE O RAILWAY REINICIAR)
    st.query_params["user_token"] = usr_data[0]


def render_login():
    # 1. VERIFICA SE JÁ EXISTE SESSÃO GRAVADA NA URL
    params = st.query_params
    usuario_url = params.get("user_token", None)

    if usuario_url and not st.session_state.get("logado"):
        usr_data = carregar_dados_usuario(usuario_url)
        if usr_data:
            aplicar_sessao_usuario(usr_data)
            st.rerun()

    st.markdown(
        "<h2 style='text-align: center;'>🔐 Acesso ao Portal Delta</h2>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button(
                "Entrar no Sistema", use_container_width=True, type="primary"
            )

            if btn_entrar:
                if usuario and senha:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT username, password 
                        FROM usuarios 
                        WHERE LOWER(username) = LOWER(%s) AND password = %s;
                    """,
                        (usuario.strip(), senha.strip()),
                    )

                    login_valido = cursor.fetchone()

                    if login_valido:
                        usr_data = carregar_dados_usuario(usuario.strip())
                        aplicar_sessao_usuario(usr_data)

                        try:
                            cursor.execute(
                                "INSERT INTO historico_logins (username, perfil) VALUES (%s, %s);",
                                (usr_data[0], usr_data[1]),
                            )
                            conn.commit()
                        except Exception:
                            conn.rollback()

                        cursor.close()
                        conn.close()
                        st.rerun()
                    else:
                        cursor.close()
                        conn.close()
                        st.error("Usuário ou senha incorretos.")
                else:
                    st.warning("Preencha o usuário e a senha.")


def logout():
    """Limpa a sessão e remove o token da URL ao deslogar."""
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()
