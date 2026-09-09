import streamlit as st
import pandas as pd
from database import get_db_connection, obter_opcoes_destino

def render_modulo_compras():
    st.header("🛒 Módulo de Compras")
    
    aba_solicitacao, aba_aprovacao_gestor, aba_cotacao, aba_aprovacao_final = st.tabs([
        "📝 Nova Solicitação", 
        "👀 1ª Aprovação (Gestor)", 
        "💰 Cotações (Compras)",
        "👑 Aprovação Final (Gestor + Diretoria)"
    ])
    
    conn = get_db_connection()
    
    with aba_solicitacao:
        st.subheader("Criar Solicitação de Compra")
        opcoes_projetos = obter_opcoes_destino(conn)
        
        with st.form("form_solicitacao_compra"):
            col1, col2 = st.columns(2)
            with col1:
                projeto = st.selectbox("Projeto / Centro de Custo *", options=opcoes_projetos)
                item = st.text_input("Nome do Item / Material *")
                quantidade = st.number_input("Quantidade *", min_value=0.01, step=1.0)
            with col2:
                unidade = st.selectbox("Unidade", options=["UN", "KG", "M", "PCT", "CX", "L", "JG"], index=0)
                fornecedor_sugerido = st.text_input("Fornecedor Sugerido (Opcional)")
                
            solicitante = st.text_input("Seu Nome / Solicitante *", value=st.session_state.get("user_token", ""))
            
            submitted = st.form_submit_button("Enviar Solicitação")
            
            if submitted:
                if not item or not projeto or not solicitante:
                    st.error("Preencha todos os campos obrigatórios (*).")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO compras (projeto, item, quantidade, unidade, fornecedor_sugerido, status, solicitante)
                            VALUES (%s, %s, %s, %s, %s, 'Pendente Aprovação Gestor', %s);
                        """, (projeto, item, quantidade, unidade, fornecedor_sugerido, solicitante))
                        conn.commit()
                        cursor.close()
                        st.success("🎉 Solicitação de compra enviada com sucesso! Aguardando aprovação do gestor.")
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao salvar solicitação: {e}")

    with aba_aprovacao_gestor:
        st.subheader("Aprovações Pendentes (Gestor da Área)")
        try:
            df_pendentes = pd.read_sql_query(
                "SELECT id, data_pedido, projeto, item, quantidade, unidade, fornecedor_sugerido, solicitante FROM compras WHERE status = 'Pendente Aprovação Gestor'", 
                conn
            )
            
            if df_pendentes.empty:
                st.info("Nenhuma solicitação pendente para o gestor no momento.")
            else:
                st.dataframe(df_pendentes, use_container_width=True)
                id_aprovar = st.selectbox("Selecione o ID da Solicitação para Ação", options=df_pendentes["id"].tolist(), key="apr_gestor")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("✅ Aprovar Solicitação", type="primary", key="btn_aprov_gestor"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação' WHERE id = %s;", (id_aprovar,))
                            conn.commit()
                            cursor.close()
                            st.success(f"Solicitação #{id_aprovar} aprovada! Enviada para o setor de compras.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao aprovar: {e}")
                            
                with col_btn2:
                    if st.button("❌ Rejeitar Solicitação", key="btn_rej_gestor"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Rejeitado pelo Gestor' WHERE id = %s;", (id_aprovar,))
                            conn.commit()
                            cursor.close()
                            st.warning(f"Solicitação #{id_aprovar} rejeitada.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao rejeitar: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar solicitações: {e}")

    with aba_cotacao:
        st.subheader("Cotações de Compras (3 Fornecedores)")
        try:
            df_cotacoes = pd.read_sql_query(
                "SELECT id, projeto, item, quantidade, unidade, solicitante FROM compras WHERE status = 'Aprovado pelo Gestor - Aguardando Cotação'", 
                conn
            )
            
            if df_cotacoes.empty:
                st.info("Nenhuma solicitação aguardando cotação no momento.")
            else:
                st.dataframe(df_cotacoes, use_container_width=True)
                id_cotar = st.selectbox("Selecione o ID do Item para Inserir Cotações", options=df_cotacoes["id"].tolist(), key="sel_cotacao")
                
                item_selecionado = df_cotacoes[df_cotacoes["id"] == id_cotar].iloc[0]
                st.info(f"Cotando para: **{item_selecionado['item']}** ({item_selecionado['quantidade']} {item_selecionado['unidade']}) - Projeto: {item_selecionado['projeto']}")
                
                with st.form("form_3_cotacoes"):
                    st.markdown("#### Preencha os dados dos 3 Fornecedores:")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("**Fornecedor 1**")
                        f1_nome = st.text_input("Nome F1")
                        f1_preco = st.number_input("Preço Unit. F1 (R$)", min_value=0.0, step=0.1)
                    with c2:
                        st.markdown("**Fornecedor 2**")
                        f2_nome = st.text_input("Nome F2")
                        f2_preco = st.number_input("Preço Unit. F2 (R$)", min_value=0.0, step=0.1)
                    with c3:
                        st.markdown("**Fornecedor 3**")
                        f3_nome = st.text_input("Nome F3")
                        f3_preco = st.number_input("Preço Unit. F3 (R$)", min_value=0.0, step=0.1)
                        
                    btn_enviar_aprovacao = st.form_submit_button("Enviar Cotações para Aprovação Final", type="primary")
                    
                    if btn_enviar_aprovacao:
                        if not f1_nome or not f2_nome or not f3_nome or f1_preco <= 0 or f2_preco <= 0 or f3_preco <= 0:
                            st.error("Preencha o nome e um preço válido para todos os 3 fornecedores.")
                        else:
                            try:
                                cursor = conn.cursor()
                                resumo_cotacoes = f"F1: {f1_nome} (R$ {f1_preco}) | F2: {f2_nome} (R$ {f2_preco}) | F3: {f3_nome} (R$ {f3_preco})"
                                cursor.execute("""
                                    UPDATE compras 
                                    SET fornecedor_sugerido = %s, status = 'Aguardando Aprovação Final (Gestor + Diretoria)' 
                                    WHERE id = %s;
                                """, (resumo_cotacoes, id_cotar))
                                conn.commit()
                                cursor.close()
                                st.success("🎉 Cotações registradas e enviadas para Aprovação Final!")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao salvar cotações: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar cotações: {e}")

    with aba_aprovacao_final:
        st.subheader("Aprovação Final de Cotações (Gestor + Diretoria)")
        try:
            df_final = pd.read_sql_query(
                "SELECT id, projeto, item, quantidade, unidade, fornecedor_sugerido, solicitante FROM compras WHERE status = 'Aguardando Aprovação Final (Gestor + Diretoria)'", 
                conn
            )
            
            if df_final.empty:
                st.info("Nenhuma cotação aguardando aprovação final no momento.")
            else:
                st.dataframe(df_final, use_container_width=True)
                id_final = st.selectbox("Selecione o ID para Avaliar Cotações", options=df_final["id"].tolist(), key="sel_apr_final")
                
                item_final = df_final[df_final["id"] == id_final].iloc[0]
                st.markdown(f"**Item:** {item_final['item']} | **Qtd:** {item_final['quantidade']} {item_final['unidade']} | **Projeto:** {item_final['projeto']}")
                st.warning(f"📋 **Cotações Recebidas:**\n\n {item_final['fornecedor_sugerido']}")
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    if st.button("✅ Aprovar Definitivamente (Gerar Pedido)", type="primary", key="btn_aprov_final"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Aprovado - Pronto para Emitir Pedido' WHERE id = %s;", (id_final,))
                            conn.commit()
                            cursor.close()
                            st.success(f"Cotação #{id_final} aprovada pela Diretoria/Gestor! Liberado para emissão do Pedido de Compras.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao aprovar final: {e}")
                            
                with col_f2:
                    if st.button("❌ Reprovar Cotações", key="btn_repro_final"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Cotação Reprovada - Retorna ao Compras' WHERE id = %s;", (id_final,))
                            conn.commit()
                            cursor.close()
                            st.warning(f"Cotação #{id_final} reprovada e retornada para revisão do compras.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao reprovar: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar aprovação final: {e}")
            
    conn.close()
