import streamlit as st
import pandas as pd
from database import get_db_connection, obter_opcoes_destino

def render_modulo_compras():
    st.header("🛒 Módulo de Compras por Solicitação (SC)")
    
    aba_solicitacao, aba_aprov_gestor, aba_cotacao, aba_escolha_gestor, aba_aprov_gerente = st.tabs([
        "📝 Nova SC (Lote)", 
        "👀 1ª Ap. Gestor", 
        "💰 Cotações em Lote",
        "🎯 Escolha Gestor",
        "👑 Ap. Gerente Geral"
    ])
    
    conn = get_db_connection()
    
    if "carrinho_sc" not in st.session_state:
        st.session_state["carrinho_sc"] = []
    
    with aba_solicitacao:
        st.subheader("Montar Carrinho da Solicitação de Compra (SC)")
        opcoes_projetos = obter_opcoes_destino(conn)
        
        with st.form("form_add_item_sc"):
            col1, col2, col3 = st.columns(3)
            with col1:
                projeto_item = st.selectbox("Projeto / Centro de Custo *", options=opcoes_projetos)
                item_nome = st.text_input("Nome do Item / Material *")
            with col2:
                qtd_item = st.number_input("Quantidade *", min_value=0.01, step=1.0)
                unidade_item = st.selectbox("Unidade", options=["UN", "KG", "M", "PCT", "CX", "L", "JG"], index=0)
            with col3:
                forn_sug = st.text_input("Fornecedor Sugerido (Opcional)")
                
            btn_add = st.form_submit_button("➕ Adicionar Item à Lista")
            if btn_add:
                if not item_nome:
                    st.error("Informe o nome do item.")
                else:
                    st.session_state["carrinho_sc"].append({
                        "projeto": projeto_item,
                        "item": item_nome,
                        "quantidade": qtd_item,
                        "unidade": unidade_item,
                        "fornecedor_sugerido": forn_sug
                    })
                    st.success(f"Item '{item_nome}' adicionado à lista!")
                    st.rerun()
                    
        if st.session_state["carrinho_sc"]:
            st.markdown("### Itens na SC Atual:")
            df_carrinho = pd.DataFrame(st.session_state["carrinho_sc"])
            st.dataframe(df_carrinho, use_container_width=True)
            
            solicitante = st.text_input("Seu Nome / Solicitante *", value=st.session_state.get("user_token", ""))
            
            if st.button("🚀 Enviar Solicitação de Compra Completa (Gerar SC)", type="primary"):
                if not solicitante:
                    st.error("Preencha o nome do solicitante.")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT COALESCE(MAX(numero_sc), 0) + 1 FROM compras;")
                        novo_numero_sc = cursor.fetchone()[0]
                        
                        for row in st.session_state["carrinho_sc"]:
                            cursor.execute("""
                                INSERT INTO compras (numero_sc, projeto, item, quantidade, unidade, fornecedor_sugerido, status, solicitante, cotacao_concluida)
                                VALUES (%s, %s, %s, %s, %s, %s, 'Pendente Aprovação Gestor', %s, FALSE);
                            """, (novo_numero_sc, row["projeto"], row["item"], row["quantidade"], row["unidade"], row["fornecedor_sugerido"], solicitante))
                            
                        conn.commit()
                        cursor.close()
                        st.session_state["carrinho_sc"] = []
                        st.success(f"🎉 Solicitação **SC #{novo_numero_sc:04d}** gerada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao salvar SC: {e}")
                        
            if st.button("🗑️ Limpar Carrinho"):
                st.session_state["carrinho_sc"] = []
                st.rerun()

    with aba_aprov_gestor:
        st.subheader("1ª Aprovação - Gestor da Área (Por SC)")
        try:
            df_pendentes = pd.read_sql_query(
                "SELECT DISTINCT numero_sc, projeto, solicitante, data_pedido FROM compras WHERE status = 'Pendente Aprovação Gestor'", 
                conn
            )
            
            if df_pendentes.empty:
                st.info("Nenhuma SC pendente para o gestor.")
            else:
                for idx, sc_row in df_pendentes.iterrows():
                    with st.expander(f"SC #{sc_row['numero_sc']:04d} | Projeto: {sc_row['projeto']} | Solicitante: {sc_row['solicitante']}"):
                        df_itens_sc = pd.read_sql_query(
                            "SELECT id, item, quantidade, unidade, fornecedor_sugerido FROM compras WHERE numero_sc = %s", 
                            conn, params=(sc_row['numero_sc'],)
                        )
                        st.dataframe(df_itens_sc, use_container_width=True)
                        
                        col_g1, col_g2 = st.columns(2)
                        with col_g1:
                            if st.button(f"✅ Aprovar SC #{sc_row['numero_sc']:04d}", type="primary", key=f"apr_sc_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação' WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.success(f"SC #{sc_row['numero_sc']:04d} aprovada integralmente!")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
                        with col_g2:
                            if st.button(f"❌ Rejeitar SC #{sc_row['numero_sc']:04d}", key=f"rej_sc_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Rejeitado pelo Gestor' WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.warning(f"SC #{sc_row['numero_sc']:04d} rejeitada.")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")

    with aba_cotacao:
        st.subheader("Matriz de 3 Cotações em Lote (Setor de Compras)")
        try:
            df_cot = pd.read_sql_query(
                "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aprovado pelo Gestor - Aguardando Cotação' AND cotacao_concluida = FALSE", 
                conn
            )
            
            if df_cot.empty:
                st.info("Nenhuma SC aguardando cotação pendente no momento.")
            else:
                sc_selecionada = st.selectbox("Selecione o Número da SC para Cotação", options=df_cot["numero_sc"].tolist(), format_func=lambda x: f"SC #{x:04d}", key="sel_sc_cot")
                
                df_itens_cot = pd.read_sql_query(
                    "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete FROM compras WHERE numero_sc = %s AND cotacao_concluida = FALSE", 
                    conn, params=(sc_selecionada,)
                )
                
                st.markdown(f"**Condições Comerciais e Propostas dos 3 Fornecedores da SC #{sc_selecionada:04d}:**")
                
                default_f1 = df_itens_cot["f1_nome"].iloc[0] if not df_itens_cot.empty and df_itens_cot["f1_nome"].iloc[0] else ""
                default_p1 = int(df_itens_cot["f1_prazo"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f1_prazo"].iloc[0] else 0
                default_fr1 = float(df_itens_cot["f1_frete"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f1_frete"].iloc[0] else 0.0

                default_f2 = df_itens_cot["f2_nome"].iloc[0] if not df_itens_cot.empty and df_itens_cot["f2_nome"].iloc[0] else ""
                default_p2 = int(df_itens_cot["f2_prazo"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f2_prazo"].iloc[0] else 0
                default_fr2 = float(df_itens_cot["f2_frete"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f2_frete"].iloc[0] else 0.0

                default_f3 = df_itens_cot["f3_nome"].iloc[0] if not df_itens_cot.empty and df_itens_cot["f3_nome"].iloc[0] else ""
                default_p3 = int(df_itens_cot["f3_prazo"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f3_prazo"].iloc[0] else 0
                default_fr3 = float(df_itens_cot["f3_frete"].iloc[0]) if not df_itens_cot.empty and df_itens_cot["f3_frete"].iloc[0] else 0.0
                
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    st.markdown("##### 🏢 Fornecedor 1")
                    sup1_nome = st.text_input("Nome F1", value=default_f1, key=f"sup1_{sc_selecionada}")
                    sup1_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p1, key=f"p1_{sc_selecionada}")
                    sup1_frete = st.number_input("Valor do Frete (R$)", min_value=0.0, value=default_fr1, format="%.2f", key=f"fr1_{sc_selecionada}")
                with col_f2:
                    st.markdown("##### 🏢 Fornecedor 2")
                    sup2_nome = st.text_input("Nome F2", value=default_f2, key=f"sup2_{sc_selecionada}")
                    sup2_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p2, key=f"p2_{sc_selecionada}")
                    sup2_frete = st.number_input("Valor do Frete (R$)", min_value=0.0, value=default_fr2, format="%.2f", key=f"fr2_{sc_selecionada}")
                with col_f3:
                    st.markdown("##### 🏢 Fornecedor 3")
                    sup3_nome = st.text_input("Nome F3", value=default_f3, key=f"sup3_{sc_selecionada}")
                    sup3_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p3, key=f"p3_{sc_selecionada}")
                    sup3_frete = st.number_input("Valor do Frete (R$)", min_value=0.0, value=default_fr3, format="%.2f", key=f"fr3_{sc_selecionada}")
                
                st.markdown("---")
                st.markdown("**Preencha apenas os preços unitários para cada item abaixo:**")
                st.caption("ℹ️ Itens que ficarem sem preço em qualquer um dos 3 fornecedores continuarão pendentes nesta SC para posterior finalização.")
                
                df_editavel = df_itens_cot.copy()
                
                edited_df = st.data_editor(
                    df_editavel[[
                        "id", "item", "quantidade", "unidade", 
                        "f1_preco", "f2_preco", "f3_preco"
                    ]],
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "item": st.column_config.TextColumn("Item", disabled=True),
                        "quantidade": st.column_config.NumberColumn("Qtd", disabled=True),
                        "unidade": st.column_config.TextColumn("Un", disabled=True),
                        "f1_preco": st.column_config.NumberColumn("Preço F1 (R$)", min_value=0.0, format="R$ %.2f"),
                        "f2_preco": st.column_config.NumberColumn("Preço F2 (R$)", min_value=0.0, format="R$ %.2f"),
                        "f3_preco": st.column_config.NumberColumn("Preço F3 (R$)", min_value=0.0, format="R$ %.2f"),
                    },
                    hide_index=True,
                    key=f"editor_sc_{sc_selecionada}"
                )
                
                if st.button("💾 Salvar e Processar Itens Concluídos", type="primary"):
                    if not sup1_nome or not sup2_nome or not sup3_nome:
                        st.error("⚠️ Por favor, informe o nome dos 3 fornecedores nos campos acima.")
                    else:
                        try:
                            cursor = conn.cursor()
                            itens_concluidos_count = 0
                            
                            for idx, row in edited_df.iterrows():
                                tem_p1 = float(row["f1_preco"]) > 0
                                tem_p2 = float(row["f2_preco"]) > 0
                                tem_p3 = float(row["f3_preco"]) > 0
                                
                                if tem_p1 and tem_p2 and tem_p3:
                                    cursor.execute("""
                                        UPDATE compras 
                                        SET f1_nome = %s, f1_preco = %s, f1_prazo = %s, f1_frete = %s,
                                            f2_nome = %s, f2_preco = %s, f2_prazo = %s, f2_frete = %s,
                                            f3_nome = %s, f3_preco = %s, f3_prazo = %s, f3_frete = %s,
                                            cotacao_concluida = TRUE,
                                            status = 'Aguardando Escolha do Gestor da Área'
                                        WHERE id = %s;
                                    """, (
                                        sup1_nome, row["f1_preco"], sup1_prazo, sup1_frete,
                                        sup2_nome, row["f2_preco"], sup2_prazo, sup2_frete,
                                        sup3_nome, row["f3_preco"], sup3_prazo, sup3_frete,
                                        row["id"]
                                    ))
                                    itens_concluidos_count += 1
                                else:
                                    cursor.execute("""
                                        UPDATE compras 
                                        SET f1_nome = %s, f1_preco = %s, f1_prazo = %s, f1_frete = %s,
                                            f2_nome = %s, f2_preco = %s, f2_prazo = %s, f2_frete = %s,
                                            f3_nome = %s, f3_preco = %s, f3_prazo = %s, f3_frete = %s
                                        WHERE id = %s;
                                    """, (
                                        sup1_nome, row["f1_preco"], sup1_prazo, sup1_frete,
                                        sup2_nome, row["f2_preco"], sup2_prazo, sup2_frete,
                                        sup3_nome, row["f3_preco"], sup3_prazo, sup3_frete,
                                        row["id"]
                                    ))
                                    
                            conn.commit()
                            cursor.close()
                            st.success(f"💾 Cotações salvas! {itens_concluidos_count} item(ns) completos avançaram para o gestor. Os incompletos continuam pendentes nesta SC.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao salvar: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")

    with aba_escolha_gestor:
        st.subheader("Escolha do Fornecedor por Item (Gestor da Área)")
        try:
            df_esc = pd.read_sql_query(
                "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aguardando Escolha do Gestor da Área' AND cotacao_concluida = TRUE", 
                conn
            )
            
            if df_esc.empty:
                st.info("Nenhum item aguardando escolha de fornecedor pelo gestor.")
            else:
                sc_escolha = st.selectbox("Selecione o Número da SC para Escolha", options=df_esc["numero_sc"].tolist(), format_func=lambda x: f"SC #{x:04d}", key="sel_esc_sc_novo")
                
                df_itens_esc = pd.read_sql_query(
                    "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete FROM compras WHERE numero_sc = %s AND cotacao_concluida = TRUE AND status = 'Aguardando Escolha do Gestor da Área'", 
                    conn, params=(sc_escolha,)
                )
                
                st.markdown(f"**Itens aptos da SC #{sc_escolha:04d}:**")
                
                st.markdown("---")
                st.markdown("⚡ **Atalho rápido (Sem tempo? Escolha um fornecedor padrão para todos os itens abaixo):**")
                
                nomes_forn_unicos = sorted(list(set(
                    df_itens_esc["f1_nome"].tolist() + df_itens_esc["f2_nome"].tolist() + df_itens_esc["f3_nome"].tolist()
                )))
                
                forn_padrao = st.selectbox("Aplicar este fornecedor em massa (Opcional)", options=["-- Escolha individual abaixo --"] + nomes_forn_unicos)
                
                escolhas_usuario = {}
                for idx, row in df_itens_esc.iterrows():
                    st.markdown(f"**Item:** {row['item']} ({row['quantidade']} {row['unidade']})")
                    opcoes_f = [
                        f"1️⃣ {row['f1_nome']} — R$ {row['f1_preco']:.2f} | Prazo: {row['f1_prazo']}d | Frete: R$ {row['f1_frete']:.2f}",
                        f"2️⃣ {row['f2_nome']} — R$ {row['f2_preco']:.2f} | Prazo: {row['f2_prazo']}d | Frete: R$ {row['f2_frete']:.2f}",
                        f"3️⃣ {row['f3_nome']} — R$ {row['f3_preco']:.2f} | Prazo: {row['f3_prazo']}d | Frete: R$ {row['f3_frete']:.2f}"
                    ]
                    
                    default_idx = 0
                    if forn_padrao != "-- Escolha individual abaixo --":
                        for i, opt in enumerate(opcoes_f):
                            if forn_padrao in opt:
                                default_idx = i
                                break
                                
                    escolha = st.radio(f"Vencedor - {row['id']}", options=opcoes_f, index=default_idx, key=f"radio_item_{row['id']}", label_visibility="collapsed")
                    escolhas_usuario[row['id']] = escolha
                    st.markdown("---")
                    
                if st.button("✅ Confirmar Escolhas e Enviar para Gerente Geral", type="primary"):
                    try:
                        cursor = conn.cursor()
                        for item_id, escolha in escolhas_usuario.items():
                            cursor.execute("SELECT f1_nome, f1_preco, f2_nome, f2_preco, f3_nome, f3_preco FROM compras WHERE id = %s", (item_id,))
                            f_data = cursor.fetchone()
                            
                            if "1️⃣" in escolha:
                                f_escolhido, p_escolhido = f_data[0], f_data[1]
                            elif "2️⃣" in escolha:
                                f_escolhido, p_escolhido = f_data[2], f_data[3]
                            else:
                                f_escolhido, p_escolhido = f_data[4], f_data[5]
                                
                            cursor.execute("""
                                UPDATE compras 
                                SET fornecedor_escolhido = %s, preco_escolhido = %s, status = 'Aguardando Aprovação Gerente Geral' 
                                WHERE id = %s;
                            """, (f_escolhido, p_escolhido, item_id))
                            
                        conn.commit()
                        cursor.close()
                        st.success("🎉 Escolhas confirmadas e enviadas para o Gerente Geral!")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")

    with aba_aprov_gerente:
        st.subheader("Aprovação Final da SC (Gerente Geral / Diretoria)")
        try:
            df_ger = pd.read_sql_query(
                "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aguardando Aprovação Gerente Geral'", 
                conn
            )
            
            if df_ger.empty:
                st.info("Nenhuma SC aguardando a aprovação do Gerente Geral.")
            else:
                for idx, sc_row in df_ger.iterrows():
                    with st.expander(f"SC #{sc_row['numero_sc']:04d} | Projeto: {sc_row['projeto']} | Solicitante: {sc_row['solicitante']}"):
                        df_itens_ger = pd.read_sql_query(
                            "SELECT item, quantidade, unidade, fornecedor_escolhido, preco_escolhido, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete FROM compras WHERE numero_sc = %s AND status = 'Aguardando Aprovação Gerente Geral'", 
                            conn, params=(sc_row['numero_sc'],)
                        )
                        
                        for _, r in df_itens_ger.iterrows():
                            st.markdown(f"📦 **{r['item']}** ({r['quantidade']} {r['unidade']})")
                            st.markdown(f"👉 **Escolhido:** `{r['fornecedor_escolhido']}` por `R$ {r['preco_escolhido']:.2f}`")
                            st.caption(f"Comparativo: [1] {r['f1_nome']} (R$ {r['f1_preco']:.2f} | {r['f1_prazo']}d | R$ {r['f1_frete']:.2f}) | [2] {r['f2_nome']} (R$ {r['f2_preco']:.2f} | {r['f2_prazo']}d | R$ {r['f2_frete']:.2f}) | [3] {r['f3_nome']} (R$ {r['f3_preco']:.2f} | {r['f3_prazo']}d | R$ {r['f3_frete']:.2f})")
                            st.markdown("---")
                        
                        col_fin1, col_fin2 = st.columns(2)
                        with col_fin1:
                            if st.button(f"✅ Aprovar Definitivamente SC #{sc_row['numero_sc']:04d}", type="primary", key=f"ger_ok_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Aprovado - Pronto para Emitir Pedido' WHERE numero_sc = %s AND status = 'Aguardando Aprovação Gerente Geral';", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.success(f"SC #{sc_row['numero_sc']:04d} aprovada integralmente!")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
                        with col_fin2:
                            if st.button(f"❌ Retornar SC para Cotação #{sc_row['numero_sc']:04d}", key=f"ger_no_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação', cotacao_concluida = FALSE WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.warning("SC retornada para revisão do compras.")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")
            
    conn.close()
