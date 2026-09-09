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
    
    # Inicializa carrinho temporário na sessão para múltiplos itens
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
                        # Descobre o próximo número da SC
                        cursor.execute("SELECT COALESCE(MAX(numero_sc), 0) + 1 FROM compras;")
                        novo_numero_sc = cursor.fetchone()[0]
                        
                        for row in st.session_state["carrinho_sc"]:
                            cursor.execute("""
                                INSERT INTO compras (numero_sc, projeto, item, quantidade, unidade, fornecedor_sugerido, status, solicitante)
                                VALUES (%s, %s, %s, %s, %s, %s, 'Pendente Aprovação Gestor', %s);
                            """, (novo_numero_sc, row["projeto"], row["item"], row["quantidade"], row["unidade"], row["fornecedor_sugerido"], solicitante))
                            
                        conn.commit()
                        cursor.close()
                        st.session_state["carrinho_sc"] = []
                        st.success(f"🎉 Solicitação **SC #{novo_numero_sc:04d}** gerada com sucesso e enviada ao gestor!")
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
                "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aprovado pelo Gestor - Aguardando Cotação'", 
                conn
            )
            
            if df_cot.empty:
                st.info("Nenhuma SC aguardando cotação.")
            else:
                sc_selecionada = st.selectbox("Selecione o Número da SC para Cotação", options=df_cot["numero_sc"].tolist(), format_func=lambda x: f"SC #{x:04d}")
                
                df_itens_cot = pd.read_sql_query(
                    "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f2_nome, f2_preco, f3_nome, f3_preco FROM compras WHERE numero_sc = %s", 
                    conn, params=(sc_selecionada,)
                )
                
                st.markdown(f"**Editando cotações para os itens da SC #{sc_selecionada:04d}:**")
                st.info("Preencha as colunas abaixo diretamente. *Atenção:* Todos os itens devem conter os 3 fornecedores com nomes e preços preenchidos para que a SC possa avançar.")
                
                # Prepara dataframe editável para a matriz
                df_editavel = df_itens_cot.copy()
                
                edited_df = st.data_editor(
                    df_editavel,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "item": st.column_config.TextColumn("Item", disabled=True),
                        "quantidade": st.column_config.NumberColumn("Qtd", disabled=True),
                        "unidade": st.column_config.TextColumn("Un", disabled=True),
                        "f1_nome": "Fornecedor 1",
                        "f1_preco": st.column_config.NumberColumn("Preço F1 (R$)", min_value=0.0, format="R$ %.2f"),
                        "f2_nome": "Fornecedor 2",
                        "f2_preco": st.column_config.NumberColumn("Preço F2 (R$)", min_value=0.0, format="R$ %.2f"),
                        "f3_nome": "Fornecedor 3",
                        "f3_preco": st.column_config.NumberColumn("Preço F3 (R$)", min_value=0.0, format="R$ %.2f"),
                    },
                    hide_index=True,
                    key=f"editor_sc_{sc_selecionada}"
                )
                
                if st.button("💾 Salvar Cotações da SC e Enviar para Escolha", type="primary"):
                    try:
                        cursor = conn.cursor()
                        incompleto = False
                        
                        for idx, row in edited_df.iterrows():
                            # Valida se algum item ficou sem nome ou preço zerado em qualquer um dos 3
                            if not row["f1_nome"] or row["f1_preco"] <= 0 or not row["f2_nome"] or row["f2_preco"] <= 0 or not row["f3_nome"] or row["f3_preco"] <= 0:
                                incompleto = True
                                break
                                
                            cursor.execute("""
                                UPDATE compras 
                                SET f1_nome = %s, f1_preco = %s, 
                                    f2_nome = %s, f2_preco = %s, 
                                    f3_nome = %s, f3_preco = %s 
                                WHERE id = %s;
                            """, (row["f1_nome"], row["f1_preco"], row["f2_nome"], row["f2_preco"], row["f3_nome"], row["f3_preco"], row["id"]))
                            
                        if incompleto:
                            conn.rollback()
                            cursor.close()
                            st.error("⚠️ Existem itens com cotações em branco ou preço zero. Todos os 3 fornecedores devem ser preenchidos para cada item para encerrar a cotação desta SC.")
                        else:
                            # Atualiza status da SC inteira para aguardar escolha do gestor
                            cursor.execute("UPDATE compras SET status = 'Aguardando Escolha do Gestor da Área' WHERE numero_sc = %s;", (sc_selecionada,))
                            conn.commit()
                            cursor.close()
                            st.success(f"🎉 Cotações da SC #{sc_selecionada:04d} salvas com sucesso! SC enviada para a escolha do gestor.")
                            st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao salvar cotações: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")

    with aba_escolha_gestor:
        st.subheader("Escolha do Fornecedor por Item (Gestor da Área)")
        try:
            df_esc = pd.read_sql_query(
                "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aguardando Escolha do Gestor da Área'", 
                conn
            )
            
            if df_esc.empty:
                st.info("Nenhuma SC aguardando escolha de fornecedor pelo gestor.")
            else:
                sc_escolha = st.selectbox("Selecione o Número da SC para Escolha", options=df_esc["numero_sc"].tolist(), format_func=lambda x: f"SC #{x:04d}", key="sel_esc_sc")
                
                df_itens_esc = pd.read_sql_query(
                    "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f2_nome, f2_preco, f3_nome, f3_preco FROM compras WHERE numero_sc = %s", 
                    conn, params=(sc_escolha,)
                )
                
                st.markdown(f"**Escolha o fornecedor vencedor para cada item da SC #{sc_escolha:04d}:**")
                
                escolhas_usuario = {}
                for idx, row in df_itens_esc.iterrows():
                    st.markdown(f"--- **Item:** {row['item']} ({row['quantidade']} {row['unidade']})")
                    opcoes_f = [
                        f"1️⃣ {row['f1_nome']} (R$ {row['f1_preco']:.2f})",
                        f"2️⃣ {row['f2_nome']} (R$ {row['f2_preco']:.2f})",
                        f"3️⃣ {row['f3_nome']} (R$ {row['f3_preco']:.2f})"
                    ]
                    escolha = st.radio(f"Vencedor para: {row['item']}", options=opcoes_f, key=f"radio_item_{row['id']}")
                    escolhas_usuario[row['id']] = escolha
                    
                if st.button("✅ Confirmar Escolhas da SC e Enviar para Gerente Geral", type="primary"):
                    try:
                        cursor = conn.cursor()
                        for item_id, escolha in escolhas_usuario.items():
                            # Busca os dados do item de novo para mapear
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
                                SET fornecedor_escolhido = %s, preco_escolhido = %s 
                                WHERE id = %s;
                            """, (f_escolhido, p_escolhido, item_id))
                            
                        # Atualiza status da SC inteira
                        cursor.execute("UPDATE compras SET status = 'Aguardando Aprovação Gerente Geral' WHERE numero_sc = %s;", (sc_escolha,))
                        conn.commit()
                        cursor.close()
                        st.success(f"Escolhas da SC #{sc_escolha:04d} confirmadas! Enviada para o Gerente Geral.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao salvar escolhas: {e}")
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
                        df_resumo = pd.read_sql_query(
                            "SELECT item, quantidade, unidade, fornecedor_escolhido, preco_escolhido, f1_nome, f1_preco, f2_nome, f2_preco, f3_nome, f3_preco FROM compras WHERE numero_sc = %s", 
                            conn, params=(sc_row['numero_sc'],)
                        )
                        st.dataframe(df_resumo, use_container_width=True)
                        
                        col_fin1, col_fin2 = st.columns(2)
                        with col_fin1:
                            if st.button(f"✅ Aprovar Definitivamente SC #{sc_row['numero_sc']:04d}", type="primary", key=f"ger_ok_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Aprovado - Pronto para Emitir Pedido' WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.success(f"SC #{sc_row['numero_sc']:04d} aprovada integralmente pelo Gerente Geral!")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
                        with col_fin2:
                            if st.button(f"❌ Retornar SC para Cotação #{sc_row['numero_sc']:04d}", key=f"ger_no_{sc_row['numero_sc']}"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação' WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                    conn.commit()
                                    cursor.close()
                                    st.warning("SC retornada para o setor de compras revisar cotações.")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro: {e}")
        except Exception as e:
            st.error(f"Erro: {e}")
            
    conn.close()
