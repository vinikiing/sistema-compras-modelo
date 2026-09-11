import os
import base64
import streamlit as st
import pandas as pd
from database import get_db_connection, obter_opcoes_destino

def get_logo_base64():
    """Converte automaticamente a logo_vb.png da raiz do projeto para Base64."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(root_dir, "logo_vb.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    return ""

def render_modulo_compras():
    st.header("Módulo de Compras")
    
    # Identifica o usuário logado com segurança e de forma imutável
    user_token = st.session_state.get("usuario_logado", st.session_state.get("user_token", "admin"))
    if not user_token:
        user_token = "admin"

    conn = get_db_connection()
    try:
        df_user = pd.read_sql_query("SELECT perfil FROM usuarios WHERE username = %s", conn, params=(user_token,))
        perfil_atual = df_user["perfil"].iloc[0] if not df_user.empty else "Administrador"
    except Exception:
        perfil_atual = "Administrador"
    
    is_visitante = (perfil_atual == "Visitante")

    if is_visitante:
        abas = st.tabs(["SC Aprovada / Visualização de Pedidos", "Materiais a Receber"])
    else:
        abas = st.tabs([
            "Nova Solicitação", 
            "Aprovação Gestor", 
            "Cotações",
            "Aprovação Gestor Nível 1",
            "Aprovação Nível 2",
            "SC Aprovada/Reprovada",
            "Materiais a Receber"
        ])
    
    if "carrinho_sc" not in st.session_state:
        st.session_state["carrinho_sc"] = []
    
    if not is_visitante:
        with abas[0]:
            st.subheader("Montar Lote da Solicitação de Compra")
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
                    
                btn_add = st.form_submit_button("Adicionar Item ao Lote")
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
                        st.success(f"Item '{item_nome}' adicionado ao lote!")
                        st.rerun()
                        
            if st.session_state["carrinho_sc"]:
                st.markdown("### Itens no Lote da SC Atual:")
                df_carrinho = pd.DataFrame(st.session_state["carrinho_sc"])
                
                col_configs = {
                    col: st.column_config.Column(alignment="center") 
                    for col in df_carrinho.columns if col not in ['item', 'fornecedor_sugerido', 'projeto']
                }
                for col in ['item', 'fornecedor_sugerido', 'projeto']:
                    if col in df_carrinho.columns:
                        col_configs[col] = st.column_config.Column(alignment="left")

                st.dataframe(df_carrinho, column_config=col_configs, use_container_width=True)
                
                # Opção para remover item específico do carrinho antes de emitir a SC
                with st.expander("🗑️ Remover item incorreto do lote atual"):
                    item_idx_remover = st.selectbox(
                        "Selecione o item para remover do lote:",
                        options=range(len(st.session_state["carrinho_sc"])),
                        format_func=lambda i: f"{st.session_state['carrinho_sc'][i]['item']} ({st.session_state['carrinho_sc'][i]['quantidade']} {st.session_state['carrinho_sc'][i]['unidade']})"
                    )
                    if st.button("Remover Item Selecionado do Lote", type="secondary"):
                        removido = st.session_state["carrinho_sc"].pop(item_idx_remover)
                        st.success(f"Item '{removido['item']}' removido do lote com sucesso!")
                        st.rerun()

                st.markdown("---")
                st.info(f"👤 **Solicitante Vinculado (Automático):** `{user_token}` (Imutável)")
                
                col_btn_sc1, col_btn_sc2 = st.columns(2)
                with col_btn_sc1:
                    if st.button("Emitir Solicitação de Compra (Gerar SC)", type="primary", use_container_width=True):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("SELECT COALESCE(MAX(numero_sc), 0) + 1 FROM compras;")
                            novo_numero_sc = cursor.fetchone()[0]
                            
                            for row in st.session_state["carrinho_sc"]:
                                cursor.execute("""
                                    INSERT INTO compras (numero_sc, projeto, item, quantidade, unidade, fornecedor_sugerido, status, solicitante, cotacao_concluida)
                                    VALUES (%s, %s, %s, %s, %s, %s, 'Pendente Aprovação Gestor', %s, FALSE);
                                """, (novo_numero_sc, row["projeto"], row["item"], row["quantidade"], row["unidade"], row["fornecedor_sugerido"], user_token))
                            
                            conn.commit()
                            cursor.close()
                            st.session_state["carrinho_sc"] = []
                            st.success(f"Solicitação SC #{novo_numero_sc:04d} emitida com sucesso!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao salvar SC: {e}")
                            
                with col_btn_sc2:
                    if st.button("Limpar Lote", use_container_width=True):
                        st.session_state["carrinho_sc"] = []
                        st.rerun()

        with abas[1]:
            st.subheader("Aprovação Inicial - Gestor da Área (Por SC)")
            try:
                df_pendentes = pd.read_sql_query(
                    "SELECT DISTINCT numero_sc, projeto, solicitante, data_pedido FROM compras WHERE status = 'Pendente Aprovação Gestor'", 
                    conn
                )
                
                if df_pendentes.empty:
                    st.info("Nenhuma SC pendente de aprovação inicial.")
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
                                if st.button(f"Aprovar SC #{sc_row['numero_sc']:04d}", type="primary", key=f"apr_sc_{sc_row['numero_sc']}"):
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
                                if st.button(f"Rejeitar SC #{sc_row['numero_sc']:04d}", key=f"rej_sc_{sc_row['numero_sc']}"):
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

        with abas[2]:
            st.subheader("Matriz de Cotações em Lote (Setor de Compras)")
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
                        "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete, condicao_pagamento FROM compras WHERE numero_sc = %s AND cotacao_concluida = FALSE", 
                        conn, params=(sc_selecionada,)
                    )
                    
                    if not df_itens_cot.empty:
                        with st.expander("🗑️ Excluir item incorreto desta SC"):
                            item_para_deletar = st.selectbox(
                                "Selecione o item para excluir permanentemente:",
                                options=df_itens_cot["id"].tolist(),
                                format_func=lambda x: f"ID {x} - {df_itens_cot.loc[df_itens_cot['id'] == x, 'item'].values[0]}"
                            )
                            if st.button("Confirmar Exclusão deste Item", type="secondary"):
                                try:
                                    cursor = conn.cursor()
                                    cursor.execute("DELETE FROM compras WHERE id = %s;", (item_para_deletar,))
                                    conn.commit()
                                    cursor.close()
                                    st.success(f"Item ID {item_para_deletar} excluído com sucesso!")
                                    st.rerun()
                                except Exception as ex:
                                    conn.rollback()
                                    st.error(f"Erro ao excluir item: {ex}")

                    df_itens_cot = pd.read_sql_query(
                        "SELECT id, item, quantidade, unidade, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete, condicao_pagamento FROM compras WHERE numero_sc = %s AND cotacao_concluida = FALSE", 
                        conn, params=(sc_selecionada,)
                    )
                    
                    if df_itens_cot.empty:
                        st.info("Todos os itens desta SC foram removidos ou processados.")
                        st.rerun()

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
                    
                    col_cond1, col_cond2 = st.columns(2)
                    with col_cond1:
                        cond_opcao = st.selectbox("Condição de Pagamento *", options=["À vista", "15 dias", "30 dias", "30 / 60 dias", "30 / 60 / 90 dias", "Outros"], index=2, key=f"cond_{sc_selecionada}")
                        if cond_opcao == "Outros":
                            condicao_pagamento = st.text_input("Especifique a Condição de Pagamento *", key=f"outro_cond_{sc_selecionada}")
                        else:
                            condicao_pagamento = cond_opcao
                    
                    col_f1, col_f2, col_f3 = st.columns(3)
                    
                    with col_f1:
                        st.markdown("##### Fornecedor 1")
                        sup1_nome = st.text_input("Nome F1", value=default_f1, key=f"sup1_{sc_selecionada}")
                        
                        c_moeda1, c_val1 = st.columns(2)
                        with c_moeda1:
                            sup1_moeda = st.selectbox("Moeda", ["BRL", "USD", "EUR"], key=f"moeda1_{sc_selecionada}")
                        with c_val1:
                            sup1_validade = st.date_input("Validade Proposta", key=f"val1_{sc_selecionada}")
                            
                        sup1_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p1, key=f"p1_{sc_selecionada}")
                        
                        c_ftipo1, c_fval1 = st.columns(2)
                        with c_ftipo1:
                            sup1_tipo_frete = st.selectbox("Frete", ["CIF", "FOB"], key=f"tftype1_{sc_selecionada}")
                        with c_fval1:
                            if sup1_tipo_frete == "CIF":
                                st.number_input("Valor Frete", value=0.0, disabled=True, key=f"fr1_dis_{sc_selecionada}")
                                sup1_frete = 0.0
                            else:
                                sup1_frete = st.number_input("Valor Frete", min_value=0.0, value=default_fr1, format="%.2f", key=f"fr1_{sc_selecionada}")

                    with col_f2:
                        st.markdown("##### Fornecedor 2")
                        sup2_nome = st.text_input("Nome F2", value=default_f2, key=f"sup2_{sc_selecionada}")
                        
                        c_moeda2, c_val2 = st.columns(2)
                        with c_moeda2:
                            sup2_moeda = st.selectbox("Moeda", ["BRL", "USD", "EUR"], key=f"moeda2_{sc_selecionada}")
                        with c_val2:
                            sup2_validade = st.date_input("Validade Proposta", key=f"val2_{sc_selecionada}")
                            
                        sup2_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p2, key=f"p2_{sc_selecionada}")
                        
                        c_ftipo2, c_fval2 = st.columns(2)
                        with c_ftipo2:
                            sup2_tipo_frete = st.selectbox("Frete", ["CIF", "FOB"], key=f"tftype2_{sc_selecionada}")
                        with c_fval2:
                            if sup2_tipo_frete == "CIF":
                                st.number_input("Valor Frete", value=0.0, disabled=True, key=f"fr2_dis_{sc_selecionada}")
                                sup2_frete = 0.0
                            else:
                                sup2_frete = st.number_input("Valor Frete", min_value=0.0, value=default_fr2, format="%.2f", key=f"fr2_{sc_selecionada}")

                    with col_f3:
                        st.markdown("##### Fornecedor 3")
                        sup3_nome = st.text_input("Nome F3", value=default_f3, key=f"sup3_{sc_selecionada}")
                        
                        c_moeda3, c_val3 = st.columns(2)
                        with c_moeda3:
                            sup3_moeda = st.selectbox("Moeda", ["BRL", "USD", "EUR"], key=f"moeda3_{sc_selecionada}")
                        with c_val3:
                            sup3_validade = st.date_input("Validade Proposta", key=f"val3_{sc_selecionada}")
                            
                        sup3_prazo = st.number_input("Prazo de Entrega (Dias)", min_value=0, value=default_p3, key=f"p3_{sc_selecionada}")
                        
                        c_ftipo3, c_fval3 = st.columns(2)
                        with c_ftipo3:
                            sup3_tipo_frete = st.selectbox("Frete", ["CIF", "FOB"], key=f"tftype3_{sc_selecionada}")
                        with c_fval3:
                            if sup3_tipo_frete == "CIF":
                                st.number_input("Valor Frete", value=0.0, disabled=True, key=f"fr3_dis_{sc_selecionada}")
                                sup3_frete = 0.0
                            else:
                                sup3_frete = st.number_input("Valor Frete", min_value=0.0, value=default_fr3, format="%.2f", key=f"fr3_{sc_selecionada}")
                    
                    st.markdown("---")
                    st.markdown("**Preencha os preços unitários para cada item abaixo:**")
                    
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
                            "f1_preco": st.column_config.NumberColumn(f"Preço F1 ({sup1_moeda})", min_value=0.0, format="%.2f"),
                            "f2_preco": st.column_config.NumberColumn(f"Preço F2 ({sup2_moeda})", min_value=0.0, format="%.2f"),
                            "f3_preco": st.column_config.NumberColumn(f"Preço F3 ({sup3_moeda})", min_value=0.0, format="%.2f"),
                        },
                        hide_index=True,
                        key=f"editor_sc_{sc_selecionada}"
                    )
                    
                    if st.button("Salvar e Processar Itens Concluídos", type="primary"):
                        if not sup1_nome or not sup2_nome or not sup3_nome:
                            st.error("Informe o nome dos 3 fornecedores nos campos acima.")
                        elif cond_opcao == "Outros" and not condicao_pagamento:
                            st.error("Por favor, especifique a condição de pagamento no campo 'Outros'.")
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
                                                condicao_pagamento = %s,
                                                cotacao_concluida = TRUE,
                                                status = 'Aguardando Escolha do Gestor da Área'
                                            WHERE id = %s;
                                        """, (
                                            sup1_nome, row["f1_preco"], sup1_prazo, sup1_frete,
                                            sup2_nome, row["f2_preco"], sup2_prazo, sup2_frete,
                                            sup3_nome, row["f3_preco"], sup3_prazo, sup3_frete,
                                            condicao_pagamento, row["id"]
                                        ))
                                        itens_concluidos_count += 1
                                    else:
                                        cursor.execute("""
                                            UPDATE compras 
                                            SET f1_nome = %s, f1_preco = %s, f1_prazo = %s, f1_frete = %s,
                                                f2_nome = %s, f2_preco = %s, f2_prazo = %s, f2_frete = %s,
                                                f3_nome = %s, f3_preco = %s, f3_prazo = %s, f3_frete = %s,
                                                condicao_pagamento = %s
                                            WHERE id = %s;
                                        """, (
                                            sup1_nome, row["f1_preco"], sup1_prazo, sup1_frete,
                                            sup2_nome, row["f2_preco"], sup2_prazo, sup2_frete,
                                            sup3_nome, row["f3_preco"], sup3_prazo, sup3_frete,
                                            condicao_pagamento, row["id"]
                                        ))
                                        
                                conn.commit()
                                cursor.close()
                                st.success(f"Cotações salvas! {itens_concluidos_count} item(ns) completos avançaram para o gestor.")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao salvar: {e}")
            except Exception as e:
                st.error(f"Erro: {e}")

        with abas[3]:
            st.subheader("Seleção do Fornecedor por Item - Aprovação Gestor Nível 1")
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
                    
                    escolhas_usuario = {}
                    for idx, row in df_itens_esc.iterrows():
                        st.markdown(f"**Item:** {row['item']} ({row['quantidade']} {row['unidade']})")
                        opcoes_f = [
                            f"1 - {row['f1_nome']} — R$ {row['f1_preco']:.2f} | Prazo: {row['f1_prazo']}d | Frete: R$ {row['f1_frete']:.2f}",
                            f"2 - {row['f2_nome']} — R$ {row['f2_preco']:.2f} | Prazo: {row['f2_prazo']}d | Frete: R$ {row['f2_frete']:.2f}",
                            f"3 - {row['f3_nome']} — R$ {row['f3_preco']:.2f} | Prazo: {row['f3_prazo']}d | Frete: R$ {row['f3_frete']:.2f}"
                        ]
                        escolha = st.radio(f"Vencedor - {row['id']}", options=opcoes_f, key=f"radio_item_{row['id']}", label_visibility="collapsed")
                        escolhas_usuario[row['id']] = escolha
                        st.markdown("---")
                        
                    if st.button("Confirmar Seleção e Enviar para Aprovação Nível 2", type="primary"):
                        try:
                            cursor = conn.cursor()
                            for item_id, escolha in escolhas_usuario.items():
                                cursor.execute("SELECT f1_nome, f1_preco, f2_nome, f2_preco, f3_nome, f3_preco FROM compras WHERE id = %s", (item_id,))
                                f_data = cursor.fetchone()
                                
                                if "1 -" in escolha:
                                    f_escolhido, p_escolhido = f_data[0], f_data[1]
                                elif "2 -" in escolha:
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
                            st.success("Seleção confirmada e encaminhada para a Aprovação Nível 2!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro: {e}")
            except Exception as e:
                st.error(f"Erro: {e}")

        with abas[4]:
            st.subheader("Aprovação Nível 2 (Gerência / Diretoria)")
            try:
                df_ger = pd.read_sql_query(
                    "SELECT DISTINCT numero_sc, projeto, solicitante FROM compras WHERE status = 'Aguardando Aprovação Gerente Geral'", 
                    conn
                )
                
                if df_ger.empty:
                    st.info("Nenhuma SC aguardando a aprovação Nível 2.")
                else:
                    for idx, sc_row in df_ger.iterrows():
                        with st.expander(f"SC #{sc_row['numero_sc']:04d} | Projeto: {sc_row['projeto']} | Solicitante: {sc_row['solicitante']}"):
                            df_itens_ger = pd.read_sql_query(
                                "SELECT item, quantidade, unidade, fornecedor_escolhido, preco_escolhido, f1_nome, f1_preco, f1_prazo, f1_frete, f2_nome, f2_preco, f2_prazo, f2_frete, f3_nome, f3_preco, f3_prazo, f3_frete FROM compras WHERE numero_sc = %s AND status = 'Aguardando Aprovação Gerente Geral'", 
                                conn, params=(sc_row['numero_sc'],)
                            )
                            
                            for _, r in df_itens_ger.iterrows():
                                st.markdown(f"**Item:** {r['item']} ({r['quantidade']} {r['unidade']})")
                                st.markdown(f"**Fornecedor Vencedor:** `{r['fornecedor_escolhido']}` por `R$ {r['preco_escolhido']:.2f}` (Unit.)")
                                st.markdown("---")
                            
                            col_fin1, col_fin2 = st.columns(2)
                            with col_fin1:
                                if st.button(f"Aprovar Definitivamente SC #{sc_row['numero_sc']:04d}", type="primary", key=f"ger_ok_{sc_row['numero_sc']}"):
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("UPDATE compras SET status = 'Aprovado - Pronto para Emitir Pedido' WHERE numero_sc = %s AND status = 'Aguardando Aprovação Gerente Geral';", (sc_row['numero_sc'],))
                                        
                                        cursor.execute("SELECT projeto, item, quantidade, unidade, fornecedor_escolhido, preco_escolhido FROM compras WHERE numero_sc = %s AND status = 'Aprovado - Pronto para Emitir Pedido';", (sc_row['numero_sc'],))
                                        itens_aprovados = cursor.fetchall()
                                        
                                        for proj, itm, qtd, und, forn, preco in itens_aprovados:
                                            loc_trand = f"Projeto: {proj} - (A Chegar)"
                                            cursor.execute("""
                                                INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao)
                                                VALUES (%s, %s, %s, %s, %s, %s, %s);
                                            """, (f"SC-{sc_row['numero_sc']:04d}", itm, qtd, und, preco, forn, loc_trand))
                                        
                                        conn.commit()
                                        cursor.close()
                                        st.success(f"SC #{sc_row['numero_sc']:04d} aprovada no Nível 2 e enviada para 'A Chegar' no almoxarifado!")
                                        st.rerun()
                                    except Exception as e:
                                        conn.rollback()
                                        st.error(f"Erro: {e}")
                            with col_fin2:
                                if st.button(f"Retornar SC para Cotação #{sc_row['numero_sc']:04d}", key=f"ger_no_{sc_row['numero_sc']}"):
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação', cotacao_concluida = FALSE WHERE numero_sc = %s;", (sc_row['numero_sc'],))
                                        conn.commit()
                                        cursor.close()
                                        st.warning("SC retornada para revisão do setor de compras.")
                                        st.rerun()
                                    except Exception as e:
                                        conn.rollback()
                                        st.error(f"Erro: {e}")
            except Exception as e:
                st.error(f"Erro: {e}")

        with abas[5]:
            st.subheader("Solicitações de Compra (SC) Aprovadas / Reprovadas")
            try:
                df_status = pd.read_sql_query(
                    "SELECT DISTINCT numero_sc, projeto, solicitante, status FROM compras WHERE status IN ('Aprovado - Pronto para Emitir Pedido', 'Rejeitado pelo Gestor')", 
                    conn
                )
                
                if df_status.empty:
                    st.info("Nenhuma SC finalizada no momento.")
                else:
                    st.dataframe(df_status, use_container_width=True)
                    
                    df_aprovadas = df_status[df_status["status"] == 'Aprovado - Pronto para Emitir Pedido']
                    if not df_aprovadas.empty:
                        st.markdown("---")
                        st.subheader("Gerar Pedido de Compra (PO) — Iniciando do 01")
                        sc_po = st.selectbox("Selecione a SC Aprovada para Gerar o Pedido", options=df_aprovadas["numero_sc"].tolist(), format_func=lambda x: f"SC #{x:04d}")
                        
                        if sc_po:
                            df_itens_po = pd.read_sql_query(
                                "SELECT item, quantidade, unidade, fornecedor_escolhido, preco_escolhido, data_pedido, condicao_pagamento FROM compras WHERE numero_sc = %s AND status = 'Aprovado - Pronto para Emitir Pedido'",
                                conn, params=(sc_po,)
                            )
                            
                            if not df_itens_po.empty:
                                forn_atual = df_itens_po["fornecedor_escolhido"].iloc[0]
                                data_ped = pd.to_datetime(df_itens_po["data_pedido"].iloc[0]).strftime("%d/%m/%Y")
                                cond_pgto = df_itens_po["condicao_pagamento"].iloc[0]
                                
                                po_numero_formatado = f"{sc_po:02d}"
                                
                                cnpj_emitente = "45.123.789/0001-99"
                                ie_emitente = "998877665"
                                endereco_emitente = "Rodovia Central, 500, Galpão A, Distrito Industrial, São Paulo - SP"
                                nome_comprador = "V&B Strategic Sourcing"
                                
                                cnpj_forn = "12.345.678/0001-10"
                                end_forn = "Rua das Indústrias, 100, Centro, Belo Horizonte - MG"
                                tel_forn = "(31) 3333-4444"
                                
                                st.markdown(f"""
                                ### Pedido de Compra N° {po_numero_formatado}
                                
                                **Empresa Emitente (Comprador):**  
                                **{nome_comprador}**  
                                CNPJ: {cnpj_emitente} | IE: {ie_emitente}  
                                Endereço: {endereco_emitente}  
                                
                                ---
                                
                                **Fornecedor:**  
                                **{forn_atual}**  
                                CNPJ: {cnpj_forn}  
                                Endereço: {end_forn}  
                                Telefone: {tel_forn}  
                                
                                **Data do Pedido:** {data_ped}  
                                **Condição de Pagamento:** {cond_pgto}  
                                """)
                                
                                df_itens_po["Valor Total (R$)"] = df_itens_po["quantidade"] * df_itens_po["preco_escolhido"]
                                
                                st.markdown("#### Itens do Pedido de Compra")
                                st.dataframe(
                                    df_itens_po[["item", "unidade", "quantidade", "preco_escolhido", "Valor Total (R$)"]].rename(columns={
                                        "item": "Descrição do produto/serviço",
                                        "unidade": "Un",
                                        "quantidade": "Qtde",
                                        "preco_escolhido": "Valor unitário"
                                    }),
                                    use_container_width=True
                                )
                                
                                soma_qtd = df_itens_po["quantidade"].sum()
                                total_geral = df_itens_po["Valor Total (R$)"].sum()
                                
                                st.markdown(f"""
                                - **Soma das Quantidades:** {soma_qtd:,.2f}
                                - **Total de Produtos:** R$ {total_geral:,.2f}
                                - **Total do Pedido:** R$ {total_geral:,.2f}
                                
                                **Observações:**  
                                Condição de Pagamento pactuada: {cond_pgto}. Entrega conforme especificado.
                                """)
                                
                                # Obtém a logo em Base64 para embutir perfeitamente no HTML do PO
                                logo_b64 = get_logo_base64()
                                
                                html_content = f"""
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <meta charset="utf-8">
                                    <title>Pedido de Compra #{po_numero_formatado}</title>
                                    <style>
                                        body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
                                        h2, h3 {{ color: #111; }}
                                        .header, .section {{ margin-bottom: 20px; }}
                                        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                                        th, td {{ border: 1px solid #ccc; padding: 10px; text-align: left; font-size: 14px; }}
                                        th {{ background-color: #f4f4f4; }}
                                        .totals {{ margin-top: 20px; text-align: right; font-size: 15px; }}
                                    </style>
                                </head>
                                <body>
                                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ccc; padding-bottom: 15px; margin-bottom: 20px;">
                                        <div>
                                            <img src="data:image/png;base64,{logo_b64}" style="max-height: 60px; width: auto;">
                                        </div>
                                        <div style="text-align: right;">
                                            <h2 style="margin: 0; color: #111;">Pedido de Compra N° {po_numero_formatado}</h2>
                                        </div>
                                    </div>
                                    <div class="header">
                                        <strong>Comprador:</strong> {nome_comprador}<br>
                                        CNPJ: {cnpj_emitente} | IE: {ie_emitente}<br>
                                        Endereço: {endereco_emitente}
                                    </div>
                                    <hr>
                                    <div class="section">
                                        <strong>Fornecedor:</strong> {forn_atual}<br>
                                        CNPJ: {cnpj_forn}<br>
                                        Endereço: {end_forn}<br>
                                        Telefone: {tel_forn}
                                    </div>
                                    <p><strong>Data do Pedido:</strong> {data_ped} &nbsp;&nbsp;|&nbsp;&nbsp; <strong>Condição de Pagamento:</strong> {cond_pgto}</p>
                                    
                                    <h3>Itens do Pedido</h3>
                                    <table>
                                        <tr>
                                            <th>Descrição do produto/serviço</th>
                                            <th>Un</th>
                                            <th>Qtde</th>
                                            <th>Valor Unitário (R$)</th>
                                            <th>Valor Total (R$)</th>
                                        </tr>
                                """
                                for _, r in df_itens_po.iterrows():
                                    val_tot = r['quantidade'] * r['preco_escolhido']
                                    html_content += f"""
                                        <tr>
                                            <td>{r['item']}</td>
                                            <td>{r['unidade']}</td>
                                            <td>{r['quantidade']:,.2f}</td>
                                            <td>R$ {r['preco_escolhido']:,.2f}</td>
                                            <td>R$ {val_tot:,.2f}</td>
                                        </tr>
                                    """
                                html_content += f"""
                                    </table>
                                    <div class="totals">
                                        <p><strong>Soma das Quantidades:</strong> {soma_qtd:,.2f}</p>
                                        <p><strong>Total do Pedido:</strong> R$ {total_geral:,.2f}</p>
                                    </div>
                                    <p><strong>Observações:</strong> Pagamento em {cond_pgto}. Entrega conforme especificado.</p>
                                </body>
                                </html>
                                """
                                
                                st.download_button(
                                    label="Baixar Pedido de Compra (HTML para Impressão/PDF)",
                                    data=html_content,
                                    file_name=f"Pedido_Compra_{po_numero_formatado}.html",
                                    mime="text/html",
                                    type="primary",
                                    key=f"download_po_btn_{sc_po}"
                                )
            except Exception as e:
                st.error(f"Erro: {e}")

    aba_receber_idx = 0 if is_visitante else 6
    with abas[aba_receber_idx]:
        st.subheader("Materiais a Receber (Trânsito Logístico de POs)")
        st.info("ℹ️ Esta aba exibe os pedidos aprovados aguardando chegada física. A entrada oficial no estoque definitivo ocorre posteriormente via importação de XML pelo setor fiscal.")
        try:
            df_transito = pd.read_sql_query(
                "SELECT numero_sc, projeto, item, quantidade, unidade, fornecedor_escolhido, preco_escolhido, data_pedido, condicao_pagamento FROM compras WHERE status = 'Aprovado - Pronto para Emitir Pedido'",
                conn
            )
            if df_transito.empty:
                st.info("Nenhum material em trânsito no momento.")
            else:
                st.dataframe(df_transito.rename(columns={
                    "numero_sc": "SC",
                    "projeto": "Projeto/Centro Custo",
                    "item": "Material",
                    "quantidade": "Qtd",
                    "unidade": "Un",
                    "fornecedor_escolhido": "Fornecedor",
                    "preco_escolhido": "Preço Unit.",
                    "data_pedido": "Data",
                    "condicao_pagamento": "Pgto"
                }), use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao carregar materiais a receber: {e}")
            
    conn.close()
