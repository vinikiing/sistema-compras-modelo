import sys
import os
import pandas as pd
import streamlit as st
import plotly.express as px

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import database as db
from utils import clean_currency

def render(perfil_atual):
    st.title("Gestão de Saving & Projetos (Manus Integration)")

    try:
        db.init_db()
    except Exception:
        pass

    conn = db.get_db_connection()
    perm = st.session_state.get("permissoes", {})
    is_admin = perm.get("e_admin", False) or perfil_atual in ["Gestão Geral", "Gestor", "Comprador"]

    pode_ver = perm.get("pode_ver_saving", True) or is_admin
    pode_imp = perm.get("pode_importar_saving", False) or is_admin
    pode_budget = perm.get("pode_gerenciar_budgets", False) or is_admin

    if not pode_ver:
        st.error("Acesso restrito ao módulo de Saving.")
        conn.close()
        return

    abas_s = ["Visão Geral & Saving"]
    if pode_imp:
        abas_s.append("Importar Planilha Manus")
    if pode_budget:
        abas_s.append("Cadastrar Projetos & Budgets")
        abas_s.append("Gerenciar / Estornar Lançamentos")

    st_tabs = st.tabs(abas_s)

    # ---------------------------------------------------------
    # 1. VISÃO GERAL (APENAS MÉTRICAS E GRÁFICOS)
    # ---------------------------------------------------------
    with st_tabs[0]:
        st.subheader("Resumo de Saving do Projeto")
        
        try:
            df_projs = pd.read_sql_query("""
                SELECT DISTINCT projeto FROM orcamentos 
                UNION 
                SELECT DISTINCT projeto FROM lancamentos
            """, conn)
            lista_projs = df_projs["projeto"].dropna().unique().tolist() if not df_projs.empty else []
        except Exception:
            conn.rollback()
            lista_projs = []

        if not lista_projs:
            lista_projs = ["Malha IBT", "Belmicro", "PANASONIC - IBT ARATA", "Geral"]

        proj_sel = st.selectbox("Selecione o Projeto:", lista_projs)

        try:
            df_orc = pd.read_sql_query("SELECT valor_orcado FROM orcamentos WHERE projeto = %s", conn, params=(proj_sel,))
        except Exception:
            conn.rollback()
            df_orc = pd.DataFrame()

        try:
            df_lanc = pd.read_sql_query("SELECT id, setor, item, qtd, preco_inicial, preco_fechado, fornecedor FROM lancamentos WHERE projeto = %s", conn, params=(proj_sel,))
        except Exception:
            conn.rollback()
            df_lanc = pd.DataFrame()

        tot_orc = float(df_orc["valor_orcado"].sum()) if not df_orc.empty and "valor_orcado" in df_orc.columns else 0.0
        
        if not df_lanc.empty and "preco_fechado" in df_lanc.columns:
            df_lanc["qtd"] = pd.to_numeric(df_lanc["qtd"], errors="coerce").fillna(1.0)
            df_lanc["preco_fechado"] = pd.to_numeric(df_lanc["preco_fechado"], errors="coerce").fillna(0.0)
            df_lanc["subtotal"] = df_lanc["qtd"] * df_lanc["preco_fechado"]
            tot_real = float(df_lanc["subtotal"].sum())
        else:
            tot_real = 0.0

        tot_saving = tot_orc - tot_real

        c1, c2, c3 = st.columns(3)
        c1.metric("Budget Aprovado", f"R$ {tot_orc:,.2f}")
        c2.metric("Gasto Realizado (Manus)", f"R$ {tot_real:,.2f}")
        c3.metric("Saving Apurado", f"R$ {tot_saving:,.2f}", delta=f"R$ {tot_saving:,.2f}" if tot_saving >= 0 else f"-R$ {abs(tot_saving):,.2f}")

        st.divider()

        # GRÁFICOS DESTACADOS
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("### 📊 Setores Que Mais Gastaram")
            if not df_lanc.empty and "setor" in df_lanc.columns:
                df_setor = df_lanc.groupby("setor")["subtotal"].sum().reset_index()
                df_setor = df_setor[df_setor["subtotal"] > 0].sort_values(by="subtotal", ascending=False)
                
                if not df_setor.empty:
                    fig_setor = px.bar(
                        df_setor, 
                        x="setor", 
                        y="subtotal", 
                        text_auto=".2f",
                        color="setor",
                        labels={"setor": "Setor", "subtotal": "Total Gasto (R$)"},
                        color_discrete_sequence=px.colors.qualitative.Bold
                    )
                    fig_setor.update_layout(showlegend=False, height=380)
                    st.plotly_chart(fig_setor, use_container_width=True)
                else:
                    st.info("Nenhum gasto por setor registrado com valor positivo.")
            else:
                st.info("Aguardando lançamentos no projeto para exibir gastos por setor.")

        with col_g2:
            st.markdown("### 🏭 Gastos por Fornecedor")
            if not df_lanc.empty and "fornecedor" in df_lanc.columns:
                df_forn = df_lanc.groupby("fornecedor")["subtotal"].sum().reset_index()
                df_forn = df_forn[df_forn["subtotal"] > 0]
                
                if not df_forn.empty:
                    fig_pie = px.pie(
                        df_forn, 
                        names="fornecedor", 
                        values="subtotal", 
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_pie.update_layout(height=380)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("Nenhum gasto por fornecedor acima de R$ 0,00.")
            else:
                st.info("Aguardando lançamentos para exibir divisão por fornecedor.")

    # ---------------------------------------------------------
    # 2. IMPORTAÇÃO MANUS (FILTRO AUTOMÁTICO DE REJEITADOS)
    # ---------------------------------------------------------
    if pode_imp and len(st_tabs) > 1:
        with st_tabs[1]:
            st.subheader("Carga da Planilha Manus")
            proj_imp_nome = st.text_input("Nome do Projeto de Destino *", value="Malha IBT")
            up_file = st.file_uploader("Arquivo Manus (.xlsx)", type=["xlsx", "xls"])

            if up_file:
                try:
                    df_raw = pd.read_excel(up_file)
                    
                    preview_data = []
                    itens_rejeitados_qtd = 0

                    for _, r in df_raw.iterrows():
                        status_val = str(r.get("Status", r.get("Situação", r.get("STATUS", "")))).strip().lower()

                        # TRAVA: Se o status for Rejeitado, Reprovado ou Cancelado, ignora completamente
                        if any(term in status_val for term in ["rejeitado", "recusado", "cancelado", "reprovado"]):
                            itens_rejeitados_qtd += 1
                            continue

                        item = str(r.get("Item", "Material Manus")).strip()
                        qtd = float(clean_currency(r.get("Quantidade", 1)))
                        preco_un = float(clean_currency(r.get("Preço Unitário", 0.0)))
                        total_col = float(clean_currency(r.get("Total", 0.0)))
                        setor_item = str(r.get("Setor", "Geral")).strip()
                        un = str(r.get("Unidade", "UN")).strip()
                        fornecedor = str(r.get("Fornecedor", "Importado Manus")).strip()

                        if fornecedor.lower() in ["nan", "none", "", "-"]:
                            fornecedor = "Não Informado"

                        if setor_item.lower() in ["nan", "none", "", "-"]:
                            setor_item = "Geral"

                        subtotal_calc = total_col if total_col > 0 else (qtd * preco_un)

                        # Adiciona apenas itens válidos com valor > 0
                        if subtotal_calc > 0 and preco_un > 0:
                            preview_data.append({
                                "Item / Descrição": item,
                                "Quantidade": qtd,
                                "Unidade": un,
                                "Preço Unitário (R$)": preco_un,
                                "Subtotal (R$)": subtotal_calc,
                                "Setor": setor_item,
                                "Fornecedor": fornecedor,
                                "Status": str(r.get("Status", "Aprovado")).strip()
                            })

                    df_preview = pd.DataFrame(preview_data)

                    if itens_rejeitados_qtd > 0:
                        st.warning(f"🚫 **{itens_rejeitados_qtd} item(ns) com status 'Rejeitado/Cancelado' foram desconsiderados automaticamente.**")

                    if df_preview.empty:
                        st.warning("Nenhum item válido com valor financeiro foi encontrado na planilha.")
                    else:
                        st.info(f"📋 **Pré-visualização da Planilha Manus:** {len(df_preview)} itens aprovados identificados.")
                        
                        col_m1, col_m2 = st.columns(2)
                        col_m1.metric("Total de Peças/Itens Aprovados", f"{df_preview['Quantidade'].sum():,.0f}")
                        col_m2.metric("Valor Total Considerado no Saving", f"R$ {df_preview['Subtotal (R$)'].sum():,.2f}")

                        st.dataframe(df_preview.drop(columns=["Status"]), use_container_width=True, hide_index=True)

                        st.divider()

                        if st.button("🚀 Confirmar e Importar Planilha Manus para o Estoque", type="primary"):
                            cursor = conn.cursor()
                            loc_transito = f"Projeto: {proj_imp_nome.strip()} (A Chegar)"

                            for _, row in df_preview.iterrows():
                                item_desc = str(row["Item / Descrição"])
                                qtd_num = float(row["Quantidade"])
                                un_str = str(row["Unidade"])
                                p_unit = float(row["Preço Unitário (R$)"])
                                forn_str = str(row["Fornecedor"])
                                set_str = str(row["Setor"])

                                cursor.execute("""
                                    INSERT INTO estoque (item, localizacao, setor_categoria, quantidade, unidade, preco_unitario, ultimo_fornecedor, usuario_registro)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                """, (item_desc, loc_transito, set_str, qtd_num, un_str, p_unit, forn_str, st.session_state["usuario_logado"]))

                                cursor.execute("""
                                    INSERT INTO lancamentos (projeto, setor, item, qtd, preco_inicial, preco_fechado, fornecedor)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                                """, (proj_imp_nome.strip(), set_str, item_desc, qtd_num, p_unit, p_unit, forn_str))

                            conn.commit()
                            cursor.close()
                            st.success(f"Planilha do projeto '{proj_imp_nome}' importada desconsiderando rejeitados!")
                            st.rerun()

                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao processar planilha: {e}")

    # ---------------------------------------------------------
    # 3. CADASTRAR PROJETOS & BUDGETS
    # ---------------------------------------------------------
    if pode_budget and len(st_tabs) > (2 if pode_imp else 1):
        tab_idx_bud = 2 if pode_imp else 1
        with st_tabs[tab_idx_bud]:
            st.subheader("Cadastro de Projetos e Orçamentos (Budgets)")
            
            with st.form("form_novo_budget"):
                col_b1, col_b2 = st.columns(2)
                b_projeto = col_b1.text_input("Nome do Projeto *", placeholder="Ex: PANASONIC - IBT ARATA")
                b_valor = col_b2.number_input("Valor do Budget Aprovado (R$) *", min_value=0.0, format="%.2f")

                if st.form_submit_button("💾 Salvar Budget do Projeto", type="primary"):
                    if b_projeto and b_valor > 0:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO orcamentos (projeto, setor, valor_orcado)
                            VALUES (%s, %s, %s);
                        """, (b_projeto.strip(), 'Geral', b_valor))
                        conn.commit()
                        cursor.close()
                        st.success(f"Budget de R$ {b_valor:,.2f} cadastrado para o projeto '{b_projeto}'!")
                        st.rerun()

            st.divider()
            st.subheader("Orçamentos Cadastrados")
            try:
                df_all_budgets = pd.read_sql_query("SELECT id, projeto, valor_orcado FROM orcamentos ORDER BY projeto ASC", conn)
                if not df_all_budgets.empty:
                    st.dataframe(df_all_budgets.rename(columns={"id": "ID", "projeto": "Projeto", "valor_orcado": "Budget Aprovado (R$)"}), use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum budget cadastrado até o momento.")
            except Exception:
                conn.rollback()

    # ---------------------------------------------------------
    # 4. GERENCIAR E ESTORNAR LANÇAMENTOS
    # ---------------------------------------------------------
    if pode_budget and len(st_tabs) > 3:
        with st_tabs[3]:
            st.subheader("🗑️ Estorno e Exclusão de Lançamentos de Teste")
            st.warning("Utilize esta aba para apagar lançamentos incorretos ou resetar projetos de teste.")

            col_del1, col_del2 = st.columns(2)

            with col_del1:
                st.markdown("### Excluir Lançamento Individual")
                try:
                    df_all_lancs = pd.read_sql_query("SELECT id, projeto, item, qtd, preco_fechado FROM lancamentos ORDER BY id DESC", conn)
                    if not df_all_lancs.empty:
                        dict_lancs = {f"ID {r['id']} | [{r['projeto']}] {r['item']} (Qtd: {r['qtd']}) - R$ {r['preco_fechado']}": r['id'] for _, r in df_all_lancs.iterrows()}
                        sel_id_del = st.selectbox("Selecione o Lançamento:", list(dict_lancs.keys()))

                        if st.button("🔴 Apagar Lançamento Selecionado", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM lancamentos WHERE id = %s;", (dict_lancs[sel_id_del],))
                            conn.commit()
                            cursor.close()
                            st.success("Lançamento apagado do Saving!")
                            st.rerun()
                    else:
                        st.info("Nenhum lançamento registrado no momento.")
                except Exception:
                    conn.rollback()

            with col_del2:
                st.markdown("### Excluir Projeto Inteiro")
                try:
                    df_p_del = pd.read_sql_query("SELECT DISTINCT projeto FROM lancamentos UNION SELECT DISTINCT projeto FROM orcamentos", conn)
                    projs_del_list = df_p_del["projeto"].dropna().tolist() if not df_p_del.empty else []

                    if projs_del_list:
                        sel_p_del = st.selectbox("Selecione o Projeto para Excluir Completamente:", projs_del_list)
                        if st.button("⚠️ EXCLUIR PROJETO COMPLETO E LANÇAMENTOS", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM lancamentos WHERE projeto = %s;", (sel_p_del,))
                            cursor.execute("DELETE FROM orcamentos WHERE projeto = %s;", (sel_p_del,))
                            cursor.execute("DELETE FROM estoque WHERE localizacao LIKE %s;", (f"%{sel_p_del}%",))
                            conn.commit()
                            cursor.close()
                            st.success(f"Projeto '{sel_p_del}' e seus lançamentos foram removidos com sucesso!")
                            st.rerun()
                    else:
                        st.info("Nenhum projeto encontrado.")
                except Exception:
                    conn.rollback()

    conn.close()
