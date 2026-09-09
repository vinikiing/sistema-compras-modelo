import streamlit as st
import pandas as pd
from database import get_db_connection, obter_opcoes_destino

def render_modulo_compras():
    st.header("🛒 Módulo de Compras")
    
    # Abas internas para separar as etapas do fluxo de compras
    aba_solicitacao, aba_aprovacao = st.tabs(["📝 Nova Solicitação", "👀 Aprovação do Gestor"])
    
    conn = get_db_connection()
    
    with aba_solicitacao:
        st.subheader("Criar Solicitação de Compra")
        
        # Pega os projetos/centros de custo cadastrados para o selectbox
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

    with aba_aprovacao:
        st.subheader("Aprovações Pendentes (Gestor)")
        try:
            df_pendentes = pd.read_sql_query(
                "SELECT id, data_pedido, projeto, item, quantidade, unidade, fornecedor_sugerido, solicitante FROM compras WHERE status = 'Pendente Aprovação Gestor'", 
                conn
            )
            
            if df_pendentes.empty:
                st.info("Nenhuma solicitação pendente no momento.")
            else:
                st.dataframe(df_pendentes, use_container_width=True)
                
                # Selecionar ID para aprovar ou rejeitar
                id_aprovar = st.selectbox("Selecione o ID da Solicitação para Ação", options=df_pendentes["id"].tolist())
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("✅ Aprovar Solicitação", type="primary"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Aprovado pelo Gestor - Aguardando Cotação' WHERE id = %s;", (id_aprovar,))
                            conn.commit()
                            cursor.close()
                            st.success(f"Solicitação #{id_aprovar} aprovada com sucesso! Enviada para o setor de cotações.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao aprovar: {e}")
                            
                with col_btn2:
                    if st.button("❌ Rejeitar Solicitação"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE compras SET status = 'Rejeitado' WHERE id = %s;", (id_aprovar,))
                            conn.commit()
                            cursor.close()
                            st.warning(f"Solicitação #{id_aprovar} rejeitada.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao rejeitar: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar solicitações: {e}")
            
    conn.close()
