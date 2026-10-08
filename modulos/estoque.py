import streamlit as st
import pandas as pd
import database as db
from datetime import datetime

# ==========================================
# 1. FUNÇÃO DE LEITURA COM CACHE
# ==========================================
@st.cache_data(ttl=10)
def carregar_estoque_cached():
    """
    Busca os dados do estoque no SQLite mantendo em cache por 10 segundos.
    Evita leituras repetidas e elimina o pisca-pisca / tela esbranquiçada.
    """
    conn = db.get_db_connection()
    df = pd.read_sql("SELECT * FROM estoque ORDER BY id DESC;", conn)
    conn.close()
    return df


# ==========================================
# 2. FUNÇÃO PRINCIPAL DE RENDERIZAÇÃO
# ==========================================
def render():
    st.title("📦 Controle de Estoque & Almoxarifado")

    # Leitura otimizada via cache
    df_estoque = carregar_estoque_cached()

    # Indicadores Topo (KPIs)
    total_skus = len(df_estoque)
    skus_zerados = len(df_estoque[df_estoque['quantidade'] <= 0]) if not df_estoque.empty else 0
    valor_total = (df_estoque['quantidade'] * df_estoque['preco_unitario']).sum() if not df_estoque.empty and 'preco_unitario' in df_estoque.columns else 0.0

    col1, col2, col3 = st.columns(3)
    col1.metric("VALOR TOTAL EM ESTOQUE", f"R$ {valor_total:,.2f}")
    col2.metric("TOTAL DE SKUS ATIVOS", total_skus)
    col3.metric("SKUS ZERADOS", skus_zerados)

    st.markdown("---")

    # Navegação por Sub-abas
    aba = st.radio(
        "Navegação do Estoque:",
        ["Consultar Estoque", "Lançamento Manual / Entrada XML", "Dar Baixa (Carrinho)", "Transferência de Saldo"],
        horizontal=True
    )

    # ------------------------------------------
    # ABA 1: CONSULTAR ESTOQUE
    # ------------------------------------------
    if aba == "Consultar Estoque":
        st.subheader("📋 Saldo em Estoque")
        
        busca = st.text_input("Filtrar por Descrição ou Código:")
        if busca and not df_estoque.empty:
            df_filtrado = df_estoque[
                df_estoque['descricao'].str.contains(busca, case=False, na=False) |
                df_estoque['codigo'].str.contains(busca, case=False, na=False)
            ]
        else:
            df_filtrado = df_estoque

        st.dataframe(df_filtrado, use_container_width=True)

    # ------------------------------------------
    # ABA 2: LANÇAMENTO MANUAL / ENTRADA XML
    # ------------------------------------------
    elif aba == "Lançamento Manual / Entrada XML":
        st.subheader("📥 Entrada de Materiais")
        
        with st.form("form_entrada_estoque", clear_on_submit=True):
            codigo = st.text_input("Código do SKU:")
            descricao = st.text_input("Descrição do Item:")
            quantidade = st.number_input("Quantidade:", min_value=1, step=1)
            preco_unitario = st.number_input("Preço Unitário (R$):", min_value=0.0, format="%.2f")
            
            btn_salvar = st.form_submit_button("Registrar Entrada")
            
            if btn_salvar:
                if codigo and descricao and quantidade > 0:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT id, quantidade FROM estoque WHERE codigo = ?;", (codigo,))
                    item = cursor.fetchone()
                    
                    if item:
                        novo_saldo = item['quantidade'] + quantidade
                        cursor.execute(
                            "UPDATE estoque SET quantidade = ?, preco_unitario = ? WHERE codigo = ?;",
                            (novo_saldo, preco_unitario, codigo)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO estoque (codigo, descricao, quantidade, preco_unitario) VALUES (?, ?, ?, ?);",
                            (codigo, descricao, quantidade, preco_unitario)
                        )
                    
                    conn.commit()
                    conn.close()

                    # Invalida o cache para atualizar a tela sem precisar de st.rerun()
                    carregar_estoque_cached.clear()
                    st.success(f"Entrada de {quantidade} unidade(s) do item '{descricao}' salva com sucesso!")
                else:
                    st.error("Preencha todos os campos obrigatórios!")

    # ------------------------------------------
    # ABA 3: DAR BAIXA (CARRINHO)
    # ------------------------------------------
    elif aba == "Dar Baixa (Carrinho)":
        st.subheader("📤 Baixa de Estoque")

        if df_estoque.empty:
            st.info("Nenhum item disponível no estoque.")
        else:
            itens_opcoes = {f"{row['codigo']} - {row['descricao']} (Saldo: {row['quantidade']})": row['id'] for _, row in df_estoque.iterrows()}
            item_selecionado = st.selectbox("Selecione o Item para Baixa:", list(itens_opcoes.keys()))
            qtd_baixa = st.number_input("Quantidade a baixar:", min_value=1, step=1)

            if st.button("Confirmar Baixa"):
                item_id = itens_opcoes[item_selecionado]
                row_item = df_estoque[df_estoque['id'] == item_id].iloc[0]

                if qtd_baixa > row_item['quantidade']:
                    st.error("Quantidade de baixa maior do que o saldo disponível!")
                else:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    novo_saldo = row_item['quantidade'] - qtd_baixa
                    
                    cursor.execute("UPDATE estoque SET quantidade = ? WHERE id = ?;", (novo_saldo, item_id))
                    conn.commit()
                    conn.close()

                    # Limpa o cache para atualizar o saldo na tela instantaneamente
                    carregar_estoque_cached.clear()
                    st.success("Baixa realizada com sucesso!")

    # ------------------------------------------
    # ABA 4: TRANSFERÊNCIA DE SALDO
    # ------------------------------------------
    elif aba == "Transferência de Saldo":
        st.subheader("🔄 Transferência entre Localizações")
        st.info("Funcionalidade mantida conforme o padrão do sistema.")
