import sys
import os
import io
import pandas as pd
import streamlit as st

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import database as db

def render(perfil_atual):
    try:
        db.init_db()
    except Exception:
        pass

    st.title("Configuracoes do Sistema e Controle de Acessos")

    # Apenas o perfil Gestor Geral / Administrador tem acesso total às abas de gestão
    is_admin_config = perfil_atual in ["Gestao Geral", "Administrador"]

    if is_admin_config:
        tab_minha_s, tab_gestao_u, tab_cc_gest, tab_hist_access = st.tabs([
            "Minha Senha",
            "Controle Personalizado de Usuarios",
            "Gerenciar Centros de Custo",
            "Historico de Acessos"
        ])
    else:
        tab_minha_s = st.container()
        tab_gestao_u = None
        tab_cc_gest = None
        tab_hist_access = None

    with tab_minha_s:
        st.subheader("Alterar Minha Senha")
        with st.form("form_minha_senha"):
            nova_senha = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Atualizar Minha Senha"):
                if nova_senha:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    try:
                        cursor.execute(
                            "UPDATE usuarios SET password = %s WHERE LOWER(username) = LOWER(%s);",
                            (nova_senha, st.session_state["usuario_logado"]),
                        )
                        conn.commit()
                        st.success("Sua senha foi alterada com sucesso.")
                    except Exception as e:
                        st.error(f"Erro ao alterar senha: {e}")
                    cursor.close()
                    conn.close()

    if tab_gestao_u and is_admin_config:
        with tab_gestao_u:
            st.subheader("Lista de Usuarios Cadastrados")

            conn = db.get_db_connection()
            try:
                df_u = pd.read_sql_query("SELECT username, perfil, e_admin FROM usuarios", conn)
            except Exception:
                df_u = pd.DataFrame(columns=["username", "perfil", "e_admin"])
            conn.close()

            if not df_u.empty:
                st.dataframe(df_u, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Cadastrar / Modificar Permissoes do Usuario")

            with st.form("form_usuario_permissoes_personalizadas"):
                col_u1, col_u2, col_u3 = st.columns(3)
                u_nome_in = col_u1.text_input("Nome de Usuario *")
                u_senha_in = col_u2.text_input("Senha *", type="password")
                
                # Perfis corporativos alinhados ao planejamento
                perfis_sistema = [
                    "Administrador",
                    "Comprador",
                    "Fiscal",
                    "Gestor Nivel 1",
                    "Gestor Nivel 2",
                    "Almoxarife",
                    "Visitante",
                    "Gestao Geral"
                ]
                u_perfil_in = col_u3.selectbox("Nivel de Acesso Base", perfis_sistema)

                st.markdown("---")
                st.markdown("### Marque o que este usuario PODE acessar:")

                col_p1, col_p2, col_p3 = st.columns(3)

                with col_p1:
                    st.markdown("**Modulo de Saving & Projetos**")
                    p_ver_saving = st.checkbox("Visualizar Saving & Projetos", value=True)
                    p_imp_saving = st.checkbox("Importar Planilhas de Cotacao")
                    p_budgets = st.checkbox("Gerenciar / Alterar Budgets")

                with col_p2:
                    st.markdown("**Operacoes de Estoque Fisico**")
                    p_cons_est = st.checkbox("Consultar Saldos do Estoque", value=True)
                    p_ent_est = st.checkbox("Dar Entradas (XML / Manual)")
                    p_baixa_est = st.checkbox("Dar Baixas (Kit / Producao)")
                    p_end_est = st.checkbox("Enderecar / Classificar Materiais")
                    p_transf_est = st.checkbox("Transferir Saldo entre Projetos")

                with col_p3:
                    st.markdown("**Auditoria e Administracao**")
                    p_estorno_ent = st.checkbox("Estornar Entradas")
                    p_estorno_sai = st.checkbox("Estornar Saidas")
                    p_relatorios = st.checkbox("Visualizar Relatorios de Consumo", value=True)
                    p_admin = st.checkbox("Administrador Geral (Acesso Total)")

                if st.form_submit_button("Salvar Usuario e Permissoes", type="primary"):
                    if u_nome_in and u_senha_in:
                        conn = db.get_db_connection()
                        cursor = conn.cursor()
                        try:
                            cursor.execute("""
                                ALTER TABLE usuarios 
                                ADD COLUMN IF NOT EXISTS pode_ver_saving BOOLEAN DEFAULT TRUE,
                                ADD COLUMN IF NOT EXISTS pode_importar_saving BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_gerenciar_budgets BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_consultar_estoque BOOLEAN DEFAULT TRUE,
                                ADD COLUMN IF NOT EXISTS pode_dar_entrada_estoque BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_dar_baixa_estoque BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_enderecar_estoque BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_transferir_estoque BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_estornar_estoque BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS pode_ver_relatorios BOOLEAN DEFAULT TRUE,
                                ADD COLUMN IF NOT EXISTS e_admin BOOLEAN DEFAULT FALSE;
                            """)
                            conn.commit()

                            p_estorno_geral = p_estorno_ent or p_estorno_sai
                            cursor.execute("""
                                INSERT INTO usuarios (
                                    username, password, perfil,
                                    pode_ver_saving, pode_importar_saving, pode_gerenciar_budgets,
                                    pode_consultar_estoque, pode_dar_entrada_estoque, pode_dar_baixa_estoque,
                                    pode_enderecar_estoque, pode_transferir_estoque, pode_estornar_estoque,
                                    pode_ver_relatorios, e_admin
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (username) DO UPDATE SET
                                    password = EXCLUDED.password,
                                    perfil = EXCLUDED.perfil,
                                    pode_ver_saving = EXCLUDED.pode_ver_saving,
                                    pode_importar_saving = EXCLUDED.pode_importar_saving,
                                    pode_gerenciar_budgets = EXCLUDED.pode_gerenciar_budgets,
                                    pode_consultar_estoque = EXCLUDED.pode_consultar_estoque,
                                    pode_dar_entrada_estoque = EXCLUDED.pode_dar_entrada_estoque,
                                    pode_dar_baixa_estoque = EXCLUDED.pode_dar_baixa_estoque,
                                    pode_enderecar_estoque = EXCLUDED.pode_enderecar_estoque,
                                    pode_transferir_estoque = EXCLUDED.pode_transferir_estoque,
                                    pode_estornar_estoque = EXCLUDED.pode_estornar_estoque,
                                    pode_ver_relatorios = EXCLUDED.pode_ver_relatorios,
                                    e_admin = EXCLUDED.e_admin;
                            """, (
                                u_nome_in.strip(), u_senha_in.strip(), u_perfil_in,
                                p_ver_saving, p_imp_saving, p_budgets,
                                p_cons_est, p_ent_est, p_baixa_est,
                                p_end_est, p_transf_est, p_estorno_geral,
                                p_relatorios, p_admin
                            ))
                            conn.commit()
                            st.success(f"Permissoes do usuario '{u_nome_in}' salvas com sucesso!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao salvar permissoes: {e}")
                        cursor.close()
                        conn.close()
                    else:
                        st.warning("Preencha o nome de usuario e a senha.")

            st.divider()
            st.subheader("Remover Usuarios")
            if not df_u.empty and "username" in df_u.columns:
                users_del = [
                    u for u in df_u["username"].tolist() if u.lower() != st.session_state["usuario_logado"].lower()
                ]
                if users_del:
                    u_sel = st.selectbox("Selecione o usuario para excluir:", users_del)
                    if st.button("Apagar Usuario", type="primary"):
                        conn = db.get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM usuarios WHERE LOWER(username) = LOWER(%s);", (u_sel,))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        st.success(f"Usuario '{u_sel}' removido.")
                        st.rerun()

    if tab_cc_gest and is_admin_config:
        with tab_cc_gest:
            st.subheader("Gestao de Centros de Custo")

            conn = db.get_db_connection()
            try:
                df_cc_list = pd.read_sql_query("SELECT id, nome_centro FROM centros_custo ORDER BY nome_centro ASC", conn)
            except Exception:
                df_cc_list = pd.DataFrame()

            if not df_cc_list.empty:
                st.write("Centros de Custo Ativos:")
                st.dataframe(df_cc_list, use_container_width=True, hide_index=True)

            col_cc_add, col_cc_del = st.columns(2)

            with col_cc_add:
                st.write("**Cadastrar Novo Centro de Custo:**")
                novo_cc_nome = st.text_input("Nome do Centro de Custo (Ex: Producao - Galpao 2)")
                if st.button("Cadastrar Centro de Custo"):
                    if novo_cc_nome:
                        cursor = conn.cursor()
                        try:
                            cursor.execute("INSERT INTO centros_custo (nome_centro) VALUES (%s);", (novo_cc_nome.strip(),))
                            conn.commit()
                            st.success(f"Centro de Custo '{novo_cc_nome}' adicionado.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error("Erro ao cadastrar ou nome ja existente.")
                        cursor.close()

            with col_cc_del:
                st.write("**Remover Centro de Custo:**")
                if not df_cc_list.empty:
                    cc_del_sel = st.selectbox("Selecione para Excluir:", df_cc_list["nome_centro"].tolist())
                    if st.button("Apagar Centro de Custo", type="primary"):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM centros_custo WHERE nome_centro = %s;", (cc_del_sel,))
                        conn.commit()
                        cursor.close()
                        st.success(f"Centro de Custo '{cc_del_sel}' removido.")
                        st.rerun()

            conn.close()

    if tab_hist_access and is_admin_config:
        with tab_hist_access:
            st.subheader("Historico de Acessos ao Sistema")

            conn = db.get_db_connection()
            try:
                df_acc = pd.read_sql_query("""
                    SELECT id, data_hora, username AS usuario, perfil 
                    FROM historico_logins 
                    ORDER BY data_hora DESC 
                    LIMIT 300
                """, conn)
            except Exception:
                df_acc = pd.DataFrame()
            conn.close()

            if df_acc.empty:
                st.info("Nenhum registro de acesso gravado.")
            else:
                col_acc1, col_acc2 = st.columns([3, 1])
                usrs_filtro = ["Todos os Usuarios"] + sorted(list(df_acc["usuario"].dropna().unique()))
                usr_acc_sel = col_acc1.selectbox("Filtrar por Usuario:", usrs_filtro)

                df_acc_vis = df_acc.copy()
                if usr_acc_sel != "Todos os Usuarios":
                    df_acc_vis = df_acc_vis[df_acc_vis["usuario"] == usr_acc_sel]

                st.dataframe(df_acc_vis[["data_hora", "usuario", "perfil"]], use_container_width=True, hide_index=True)

                buffer_acc = io.BytesIO()
                with pd.ExcelWriter(buffer_acc, engine="openpyxl") as writer:
                    df_acc_vis.to_excel(writer, index=False, sheet_name="Historico_Acessos")

                col_acc2.write("")
                col_acc2.download_button(
                    label="Exportar para Excel",
                    data=buffer_acc.getvalue(),
                    file_name="historico_acessos_portal.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
