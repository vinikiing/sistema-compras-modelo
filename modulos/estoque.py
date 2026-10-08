import database as db
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
import io
import unicodedata
import re
from datetime import datetime

def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').strip().lower()

def validar_unidade(texto_unidade):
    """Valida e limpa a unidade de medida, garantindo que não contenha números."""
    if not texto_unidade:
        return "UN"
    limpo = str(texto_unidade).strip().upper()
    if any(char.isdigit() for char in limpo):
        return None 
    limpo = re.sub(r'[^A-ZÇÃÕÂÊÎÔÛÁÉÍÓÚÀÈÌÒÙ]', '', limpo)
    return limpo if limpo else "UN"

@st.cache_data(ttl=20)
def carregar_estoque_cached():
    """Carrega os dados do estoque utilizando cache do Streamlit para evitar lentidão e flickering."""
    try:
        conn = db.get_db_connection()
        df = pd.read_sql("SELECT * FROM estoque ORDER BY id DESC;", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=['id', 'codigo', 'item', 'quantidade', 'unidade', 'preco_unitario', 'localizacao', 'ultimo_fornecedor'])

def garantir_tabelas_sistema():
    """Garante que as tabelas necessárias existem no banco de dados."""
    try:
        conn = db.get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS estoque (
                id SERIAL PRIMARY KEY,
                codigo TEXT,
                item TEXT,
                quantidade NUMERIC DEFAULT 0,
                unidade TEXT DEFAULT 'UN',
                preco_unitario NUMERIC DEFAULT 0,
                localizacao TEXT DEFAULT 'A Endereçar',
                ultimo_fornecedor TEXT DEFAULT 'Diversos'
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS historico_estoque (
                id SERIAL PRIMARY KEY,
                tipo_movimentacao TEXT,
                item TEXT,
                quantidade NUMERIC,
                unidade TEXT,
                localizacao TEXT,
                projeto_motivo TEXT,
                retirado_por TEXT,
                usuario_sistema TEXT,
                data_movimentacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS solicitacoes_sa (
                id SERIAL PRIMARY KEY,
                codigo_sa TEXT,
                item_id INT,
                codigo_produto TEXT,
                item TEXT,
                quantidade NUMERIC,
                unidade TEXT,
                localizacao TEXT,
                solicitante TEXT,
                setor_destino TEXT,
                status TEXT DEFAULT 'Pendente',
                data_solicitacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atendido_por TEXT
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Erro ao inicializar tabelas do banco:", e)

def unificar_duplicados_estoque():
    """Une automaticamente itens duplicados já existentes no banco de dados somando suas quantidades."""
    try:
        conn = db.get_db_connection()
        df = pd.read_sql("SELECT id, codigo, item, quantidade, preco_unitario FROM estoque ORDER BY id ASC;", conn)
        if df.empty:
            conn.close()
            return
        
        df['item_norm'] = df['item'].astype(str).apply(strip_accents).str.upper()
        grupos = df.groupby('item_norm')
        cur = conn.cursor()
        
        houve_alteracao = False
        for nome_norm, group in grupos:
            if len(group) > 1:
                id_principal = int(group.iloc[0]['id'])
                total_qtd = group['quantidade'].sum()
                max_preco = group['preco_unitario'].max()
                
                cur.execute("UPDATE estoque SET quantidade = %s, preco_unitario = %s WHERE id = %s;", (float(total_qtd), float(max_preco), id_principal))
                
                ids_para_apagar = group.iloc[1:]['id'].tolist()
                if ids_para_apagar:
                    cur.execute("DELETE FROM estoque WHERE id IN %s;", (tuple(ids_para_apagar),))
                houve_alteracao = True
        
        if houve_alteracao:
            conn.commit()
            st.cache_data.clear()
            
        cur.close()
        conn.close()
    except Exception:
        pass

# --- FRAGMENTOS ISOLADOS POR ABA ---

@st.fragment
def renderizar_aba_consulta(df_estoque, is_almoxarife_ou_gestao, is_gestao_geral):
    st.subheader("Estoque Atual de Materiais e Saldos")
    
    if df_estoque.empty:
        st.info("📦 O estoque está vazio no momento. Utilize a aba 'Lançamento Manual' ou 'Entrada por XML' para cadastrar novos materiais.")
        return

    pesquisa = st.text_input("🔍 Pesquisar material por código, descrição ou localização...", placeholder="Digite para filtrar...", key="pesq_estoque_frag")

    try:
        df_exibicao = df_estoque.copy()
        if pesquisa:
            termo = pesquisa.lower()
            mask = False
            for col in ['codigo', 'item', 'descricao', 'localizacao', 'ultimo_fornecedor']:
                if col in df_exibicao.columns:
                    mask = mask | df_exibicao[col].astype(str).str.lower().str.contains(termo, na=False)
            df_exibicao = df_exibicao[mask]

        column_configs = {col: st.column_config.Column(alignment="center") for col in df_exibicao.columns if col != 'item'}
        if 'item' in df_exibicao.columns:
            column_configs['item'] = st.column_config.Column(alignment="left")

        st.dataframe(df_exibicao, column_config=column_configs, use_container_width=True)

        if is_almoxarife_ou_gestao:
            st.markdown("---")
            with st.expander("✏️ Painel de Edição de Produtos Existentes", expanded=False):
                st.info("💡 Altere diretamente abaixo as informações dos produtos e clique em salvar.")
                
                cols_existentes = [c for c in ['id', 'codigo', 'item', 'quantidade', 'unidade', 'preco_unitario', 'localizacao', 'ultimo_fornecedor'] if c in df_estoque.columns]
                df_editavel = df_estoque[cols_existentes].copy()
                
                edited_df = st.data_editor(
                    df_editavel,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "codigo": st.column_config.TextColumn("Código"),
                        "item": st.column_config.TextColumn("Descrição / Material"),
                        "quantidade": st.column_config.NumberColumn("Qtd", format="%.2f"),
                        "unidade": st.column_config.TextColumn("Un"),
                        "preco_unitario": st.column_config.NumberColumn("Preço Unit. (R$)", format="%.2f"),
                        "localizacao": st.column_config.TextColumn("Localização / Endereço"),
                        "ultimo_fornecedor": st.column_config.TextColumn("Fornecedor")
                    },
                    hide_index=True,
                    key="data_editor_estoque_frag"
                )
                
                if st.button("💾 Salvar Alterações no Estoque", type="primary", key="btn_salvar_edicao_frag"):
                    try:
                        conn_up = db.get_db_connection()
                        cur_up = conn_up.cursor()
                        for _, row in edited_df.iterrows():
                            u_validada = validar_unidade(row['unidade'])
                            if not u_validada:
                                st.error(f"❌ A unidade '{row['unidade']}' contém números ou caracteres inválidos.")
                                raise ValueError("Unidade inválida")
                            
                            cur_up.execute("""
                                UPDATE estoque 
                                SET codigo = %s, item = %s, quantidade = %s, unidade = %s, preco_unitario = %s, localizacao = %s, ultimo_fornecedor = %s
                                WHERE id = %s;
                            """, (
                                str(row['codigo']), str(row['item']), float(row['quantidade']),
                                u_validada, float(row['preco_unitario']), str(row['localizacao']),
                                str(row['ultimo_fornecedor']), int(row['id'])
                            ))
                        conn_up.commit()
                        cur_up.close()
                        conn_up.close()
                        st.cache_data.clear()
                        st.success("✅ Produtos atualizados com sucesso no sistema!")
                    except Exception as err_ed:
                        if str(err_ed) != "Unidade inválida":
                            st.error(f"Erro ao salvar alterações: {err_ed}")

            if is_gestao_geral:
                with st.expander("🗑️ Área de Exclusão de Produtos (Restrito a Gestão Geral)", expanded=False):
                    st.warning("⚠️ Atenção: A exclusão de um produto é permanente e removerá o item da base de dados.")
                    
                    dict_produtos_del = {f"ID {r['id']} | [{r['codigo']}] {r['item']} (Qtd: {r['quantidade']})": r['id'] for _, r in df_estoque.iterrows()}
                    
                    with st.form("form_excluir_produto_estoque_frag"):
                        produto_escolhido = st.selectbox("Selecione o produto que deseja excluir *", options=list(dict_produtos_del.keys()))
                        confirmacao_exclusao = st.checkbox("Confirmo que desejo excluir permanentemente este item do estoque")
                        
                        btn_exec_exclusao = st.form_submit_button("🔴 Excluir Produto Definitivamente", type="primary")
                        
                        if btn_exec_exclusao:
                            if not confirmacao_exclusao:
                                st.error("Marque a caixa de confirmação para prosseguir com a exclusão.")
                            else:
                                id_alvo = dict_produtos_del[produto_escolhido]
                                try:
                                    conn_del = db.get_db_connection()
                                    cur_del = conn_del.cursor()
                                    cur_del.execute("DELETE FROM estoque WHERE id = %s;", (id_alvo,))
                                    conn_del.commit()
                                    cur_del.close()
                                    conn_del.close()
                                    st.cache_data.clear()
                                    st.success("🗑️ Produto excluído com sucesso do sistema!")
                                except Exception as err_del:
                                    st.error(f"Erro ao excluir produto: {err_del}")
    except Exception as e:
        st.error(f"Erro ao carregar visualização de estoque: {e}")

@st.fragment
def renderizar_aba_enderecamento(usuario_atual, is_almoxarife_ou_gestao):
    st.subheader("📍 Gestão Logística e Endereçamento Físico")
    conn_almo = db.get_db_connection()
    aba_a1, aba_a2 = st.tabs(["🚚 Materiais Que Vão Chegar (A Chegar)", "📦 Materiais Recebidos / A Endereçar (Guardar em Lote)"])

    with aba_a1:
        st.subheader("Materiais Solicitados / A Caminho (Via Pedidos de Compra)")
        try:
            df_vai_chegar = pd.read_sql_query("SELECT id, item, quantidade, unidade, localizacao, ultimo_fornecedor, preco_unitario FROM estoque WHERE localizacao LIKE '%A Chegar%' ORDER BY id DESC;", conn_almo)
        except Exception:
            df_vai_chegar = pd.DataFrame()

        if df_vai_chegar.empty:
            st.info("Nenhum material pendente de chegada no momento.")
        else:
            st.dataframe(df_vai_chegar.rename(columns={"id": "ID", "item": "Material / Descrição", "quantidade": "Qtd", "unidade": "Un.", "localizacao": "Status / Origem", "ultimo_fornecedor": "Fornecedor", "preco_unitario": "Preço Unit."}), use_container_width=True, hide_index=True)

            if is_almoxarife_ou_gestao:
                st.divider()
                col_rec, col_canc = st.columns(2)
                with col_rec:
                    st.markdown("### 📥 Confirmar Chegada na Fábrica")
                    dict_chegar = {f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": r for _, r in df_vai_chegar.iterrows()}
                    with st.form("form_confirmar_recebimento_lote_frag"):
                        itens_rec_lote = st.multiselect("Selecione os materiais que chegaram *", options=list(dict_chegar.keys()))
                        if st.form_submit_button("✅ Marcar Como Recebidos (Mover para 'A Endereçar')", type="primary"):
                            if itens_rec_lote:
                                cursor = conn_almo.cursor()
                                count_recebidos = 0
                                for item_str in itens_rec_lote:
                                    obj_rec = dict_chegar[item_str]
                                    proj_origem = str(obj_rec["localizacao"]).replace("(A Chegar)", "").replace("Projeto:", "").strip()
                                    novo_st = f"Projeto: {proj_origem} (A Endereçar)"
                                    cursor.execute("UPDATE estoque SET localizacao = %s WHERE id = %s;", (novo_st, obj_rec["id"]))
                                    count_recebidos += 1
                                conn_almo.commit()
                                cursor.close()
                                st.cache_data.clear()
                                st.success(f"🎉 {count_recebidos} material(is) movido(s) para 'A Endereçar'!")
                            else:
                                st.error("Selecione pelo menos um material.")

                with col_canc:
                    st.markdown("### 🗑️ Cancelar / Apagar Itens")
                    dict_canc = {f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": r["id"] for _, r in df_vai_chegar.iterrows()}
                    with st.form("form_cancelar_itens_a_chegar_frag"):
                        itens_canc_lote = st.multiselect("Selecione os materiais para cancelar/excluir *", options=list(dict_canc.keys()))
                        if st.form_submit_button("🔴 Cancelar / Excluir Itens Selecionados", type="primary"):
                            if itens_canc_lote:
                                cursor = conn_almo.cursor()
                                ids_apagar = [dict_canc[k] for k in itens_canc_lote]
                                cursor.execute("DELETE FROM estoque WHERE id IN %s;", (tuple(ids_apagar),))
                                conn_almo.commit()
                                cursor.close()
                                st.cache_data.clear()
                                st.success(f"🗑️ {len(ids_apagar)} item(ns) apagado(s) com sucesso!")
                            else:
                                st.error("Selecione pelo menos um item para excluir.")

    with aba_a2:
        st.subheader("Materiais Recebidos / Aguardando Endereçamento no Armário")
        try:
            df_enderecar = pd.read_sql_query("SELECT id, item, quantidade, unidade, localizacao, ultimo_fornecedor FROM estoque WHERE localizacao LIKE '%A Endereçar%' ORDER BY id DESC;", conn_almo)
        except Exception:
            df_enderecar = pd.DataFrame()

        if df_enderecar.empty:
            st.success("🎉 Nenhum material aguardando endereçamento no momento.")
        else:
            st.dataframe(df_enderecar.rename(columns={"id": "ID", "item": "Material / Descrição", "quantidade": "Qtd", "unidade": "Un.", "localizacao": "Status / Origem", "ultimo_fornecedor": "Fornecedor"}), use_container_width=True, hide_index=True)
            st.divider()
            if is_almoxarife_ou_gestao:
                st.markdown("### 📍 Guardar Material no Endereço Físico (Em Lote)")
                try:
                    df_locs_exist = pd.read_sql_query("SELECT DISTINCT localizacao FROM estoque WHERE localizacao NOT LIKE '%A Chegar%' AND localizacao NOT LIKE '%A Endereçar%' AND localizacao NOT LIKE 'Projeto:%' ORDER BY localizacao ASC;", conn_almo)
                    locs_fiscais_existentes = df_locs_exist["localizacao"].dropna().tolist() if not df_locs_exist.empty else []
                except Exception:
                    locs_fiscais_existentes = []

                dict_end = {f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": r for _, r in df_enderecar.iterrows()}
                itens_sel_lote = st.multiselect("Selecione os materiais para guardar juntos *", options=list(dict_end.keys()), key="multiselect_enderecar_lote_frag")
                is_novo_local = st.checkbox("✍️ Cadastrar um NOVO Endereço Físico (Armário e Prateleira)", value=False if locs_fiscais_existentes else True, key="check_cadastrar_novo_local_frag")

                local_final_sel = ""
                if not is_novo_local and locs_fiscais_existentes:
                    local_final_sel = st.selectbox("Selecione um Endereço Existente *", locs_fiscais_existentes, key="select_loc_exist_frag")
                else:
                    col_arm, col_prat = st.columns(2)
                    armario_input = col_arm.text_input("Armário / Corredor *", placeholder="Ex: ARMÁRIO A", key="armario_frag")
                    prateleira_input = col_prat.text_input("Prateleira / Gaveta *", placeholder="Ex: PRATELEIRA 2", key="prat_frag")
                    if armario_input and prateleira_input:
                        local_final_sel = f"{armario_input.strip()} - {prateleira_input.strip()}"
                    elif armario_input:
                        local_final_sel = armario_input.strip()
                    else:
                        local_final_sel = prateleira_input.strip()

                st.write("")
                if st.button("📍 Confirmar Endereçamento do Lote", type="primary", use_container_width=True, key="btn_conf_end_frag"):
                    if itens_sel_lote and local_final_sel.strip():
                        cursor = conn_almo.cursor()
                        count_guardados = 0
                        for item_str in itens_sel_lote:
                            obj_item = dict_end[item_str]
                            cursor.execute("UPDATE estoque SET localizacao = %s WHERE id = %s;", (local_final_sel.strip(), obj_item["id"]))
                            cursor.execute("INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);", ('ENDEREÇAMENTO', obj_item["item"], obj_item["quantidade"], obj_item["unidade"], local_final_sel.strip(), 'Armazenamento Físico', 'Almoxarife/Gestão', usuario_atual))
                            count_guardados += 1
                        conn_almo.commit()
                        cursor.close()
                        st.cache_data.clear()
                        st.success(f"🎉 {count_guardados} material(is) guardado(s) em '{local_final_sel.strip()}'!")
                    else:
                        st.error("Selecione ao menos um material e preencha o endereço físico.")
    conn_almo.close()

@st.fragment
def renderizar_carrinho_sa(df_estoque, usuario_atual):
    st.subheader("🛒 Carrinho de Materiais & Geração de Solicitação (SA)")
    st.markdown("Monte seu carrinho com os materiais desejados e envie para a aprovação/separação do almoxarifado.")
    
    if not df_estoque.empty:
        df_disp = df_estoque[(df_estoque['quantidade'] > 0) & (~df_estoque['localizacao'].astype(str).str.contains('A Chegar|A Endereçar', na=False))]
    else:
        df_disp = pd.DataFrame()

    if df_disp.empty:
        st.warning("Não há itens com saldo disponível em estoque físico no momento.")
        return

    if "carrinho_baixa" not in st.session_state:
        st.session_state["carrinho_baixa"] = []
    
    col_b1, col_b2 = st.columns([2, 1])
    with col_b1:
        item_selecionado = st.selectbox("Selecione o Item para Adicionar ao Carrinho", options=df_disp.index, format_func=lambda x: f"{df_disp.loc[x, 'codigo']} - {df_disp.loc[x, 'item']} (Disp: {df_disp.loc[x, 'quantidade']} | Loc: {df_disp.loc[x, 'localizacao']})", key="select_item_carrinho_frag")
    with col_b2:
        qtd_baixa = st.number_input("Quantidade Desejada", min_value=0.01, step=1.0, value=1.0, key="qtd_input_frag")

    if st.button("➕ Adicionar ao Carrinho", key="btn_add_carrinho_frag"):
        it = df_disp.loc[item_selecionado]
        if qtd_baixa > it['quantidade']:
            st.error("Quantidade solicitada maior do que o saldo disponível.")
        else:
            st.session_state["carrinho_baixa"].append({
                "id": int(it['id']), 
                "codigo": it['codigo'], 
                "item": it['item'], 
                "quantidade": float(qtd_baixa), 
                "unidade": it['unidade'], 
                "localizacao": it['localizacao']
            })
            st.success("Item adicionado ao carrinho!")

    if st.session_state["carrinho_baixa"]:
        st.markdown("### 📋 Itens no Carrinho Atual")
        
        itens_para_remover = []
        for idx, item in enumerate(st.session_state["carrinho_baixa"]):
            c_desc, c_qtd, c_loc, c_del = st.columns([2.5, 1, 1.2, 0.8])
            c_desc.markdown(f"**{item['codigo']}** - {item['item']}")
            c_qtd.markdown(f"{item['quantidade']} {item['unidade']}")
            c_loc.markdown(f"📍 {item['localizacao']}")
            if c_del.button("❌ Excluir", key=f"del_carrinho_{idx}_{item['id']}"):
                itens_para_remover.append(idx)
        
        if itens_para_remover:
            for idx in sorted(itens_para_remover, reverse=True):
                st.session_state["carrinho_baixa"].pop(idx)

        st.divider()
        destino_sa = st.text_input("Setor / Projeto Destino da Solicitação (SA) *", placeholder="Ex: Manutenção Elétrica / Obra X", key="destino_sa_input_frag")
        
        col_acao1, col_acao2 = st.columns(2)
        with col_acao1:
            if st.button("🗑️ Limpar Carrinho Inteiro", use_container_width=True, key="limpar_carrinho_frag"):
                st.session_state["carrinho_baixa"] = []
        with col_acao2:
            if st.button("📤 Gerar Solicitação de Almoxarifado (SA)", type="primary", use_container_width=True, key="gerar_sa_frag"):
                if not destino_sa.strip():
                    st.warning("Informe o setor ou projeto de destino.")
                else:
                    try:
                        conn_sa = db.get_db_connection()
                        cur_sa = conn_sa.cursor()
                        codigo_sa_gerado = f"SA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        for item in st.session_state["carrinho_baixa"]:
                            cur_sa.execute("""
                                INSERT INTO solicitacoes_sa 
                                (codigo_sa, item_id, codigo_produto, item, quantidade, unidade, localizacao, solicitante, setor_destino, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendente');
                            """, (
                                codigo_sa_gerado, item["id"], item["codigo"], item["item"], 
                                item["quantidade"], item["unidade"], item["localizacao"], 
                                usuario_atual, destino_sa.strip()
                            ))
                        conn_sa.commit()
                        cur_sa.close()
                        conn_sa.close()
                        
                        st.success(f"🎉 Solicitação gerada com sucesso! Código: **{codigo_sa_gerado}**.")
                        st.session_state["carrinho_baixa"] = []
                    except Exception as err_sa:
                        st.error(f"Erro ao gerar SA: {err_sa}")

@st.fragment
def renderizar_aba_gerenciar_sas(usuario_atual, is_almoxarife_ou_gestao):
    st.subheader("📋 Gerenciamento de Solicitações de Almoxarifado (SAs Pendentes)")
    
    try:
        conn_ger = db.get_db_connection()
        df_sas = pd.read_sql("SELECT * FROM solicitacoes_sa WHERE status = 'Pendente' ORDER BY id DESC;", conn_ger)
        conn_ger.close()

        if df_sas.empty:
            st.info("🎉 Nenhuma Solicitação de Almoxarifado (SA) pendente no momento.")
        else:
            sas_unicas = df_sas["codigo_sa"].unique()
            for cod_sa in sas_unicas:
                df_itens_sa = df_sas[df_sas["codigo_sa"] == cod_sa]
                solicitante_sa = df_itens_sa["solicitante"].iloc[0]
                setor_sa = df_itens_sa["setor_destino"].iloc[0]
                data_sa = df_itens_sa["data_solicitacao"].iloc[0]

                with st.expander(f"📌 SA: {cod_sa} | Requisitante: {solicitante_sa} | Setor: {setor_sa} ({data_sa})", expanded=True):
                    st.dataframe(df_itens_sa[["codigo_produto", "item", "quantidade", "unidade", "localizacao"]].rename(columns={"codigo_produto": "Código", "item": "Material", "quantidade": "Qtd", "unidade": "Un", "localizacao": "Local Físico"}), use_container_width=True, hide_index=True)
                    
                    if is_almoxarife_ou_gestao:
                        col_apr, col_rec = st.columns(2)
                        with col_apr:
                            if st.button(f"✅ Separar e Aprovar SA {cod_sa} (Efetuar Baixa)", key=f"aprovar_{cod_sa}_frag", type="primary"):
                                try:
                                    conn_upd = db.get_db_connection()
                                    cur_upd = conn_upd.cursor()
                                    
                                    for _, r_sa in df_itens_sa.iterrows():
                                        cur_upd.execute("UPDATE estoque SET quantidade = quantidade - %s WHERE id = %s;", (float(r_sa["quantidade"]), int(r_sa["item_id"])))
                                        cur_upd.execute("""
                                            INSERT INTO historico_estoque 
                                            (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                        """, (
                                            'BAIXA SA', r_sa["item"], float(r_sa["quantidade"]), r_sa["unidade"], 
                                            r_sa["localizacao"], r_sa["setor_destino"], r_sa["solicitante"], usuario_atual
                                        ))
                                    
                                    cur_upd.execute("UPDATE solicitacoes_sa SET status = 'Concluída', atendido_por = %s WHERE codigo_sa = %s;", (usuario_atual, cod_sa))
                                    
                                    conn_upd.commit()
                                    cur_upd.close()
                                    conn_upd.close()
                                    st.cache_data.clear()
                                    st.success(f"✅ SA {cod_sa} aprovada e baixa efetuada no estoque com sucesso!")
                                except Exception as err_aprov:
                                    st.error(f"Erro ao processar aprovação da SA: {err_aprov}")
                        
                        with col_rec:
                            if st.button(f"❌ Rejeitar / Cancelar SA {cod_sa}", key=f"rejeitar_{cod_sa}_frag"):
                                try:
                                    conn_rej = db.get_db_connection()
                                    cur_rej = conn_rej.cursor()
                                    cur_rej.execute("UPDATE solicitacoes_sa SET status = 'Cancelada', atendido_por = %s WHERE codigo_sa = %s;", (usuario_atual, cod_sa))
                                    conn_rej.commit()
                                    cur_rej.close()
                                    conn_rej.close()
                                    st.warning(f"⚠️ SA {cod_sa} cancelada.")
                                except Exception as err_rej:
                                    st.error(f"Erro ao rejeitar SA: {err_rej}")
    except Exception as e:
        st.info("Nenhuma solicitação encontrada no histórico.")

@st.fragment
def renderizar_aba_lancamento_manual(df_estoque, usuario_atual):
    st.subheader("Lançamento Manual de Entrada")
    try:
        if not df_estoque.empty and 'id' in df_estoque.columns:
            max_id = df_estoque['id'].max()
            next_id = int(max_id) + 1 if pd.notna(max_id) else 1
        else:
            next_id = 1
        codigo_sugerido = f"MAN-{next_id:04d}"
    except Exception:
        codigo_sugerido = "MAN-0001"

    with st.form("form_lancamento_manual_frag"):
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            cod_man = st.text_input("Código do Material *", value=codigo_sugerido).strip()
            desc_man = st.text_input("Descrição do Material *").strip()
            qtd_man = st.number_input("Quantidade *", min_value=0.01, step=1.0)
        with col_l2:
            un_input = st.text_input("Unidade (Ex: UN, PC, KG) *", value="UN").strip()
            preco_man = st.number_input("Preço Unitário (R$)", min_value=0.0, step=0.01)
            proj_man = st.text_input("Projeto de Destino", value="GERAL / ALMOXARIFADO").strip()
        
        fornecedor_man = st.text_input("Fornecedor", value="Diversos").strip()
        btn_salvar_manual = st.form_submit_button("💾 Salvar Entrada Manual", type="primary", use_container_width=True)
        
        if btn_salvar_manual:
            un_man = validar_unidade(un_input)
            if not un_man:
                st.error("⚠️ A unidade de medida não pode conter números! Utilize apenas letras (ex: UN, PC, KG).")
            elif not cod_man or not desc_man or qtd_man <= 0:
                st.warning("Preencha o código, a descrição e uma quantidade válida.")
            else:
                try:
                    conn = db.get_db_connection()
                    cursor = conn.cursor()
                    
                    desc_norm = strip_accents(desc_man).upper()
                    item_encontrado_id = None
                    
                    if not df_estoque.empty:
                        for _, r_chk in df_estoque.iterrows():
                            if strip_accents(r_chk['item']).upper() == desc_norm or str(r_chk['codigo']).strip().upper() == str(cod_man).strip().upper():
                                item_encontrado_id = int(r_chk['id'])
                                break
                    
                    loc_inicial = f"Projeto: {proj_man} - (A Endereçar)"
                    
                    if item_encontrado_id:
                        cursor.execute("""
                            UPDATE estoque 
                            SET quantidade = quantidade + %s, unidade = %s, preco_unitario = %s, ultimo_fornecedor = %s, localizacao = %s 
                            WHERE id = %s;
                        """, (float(qtd_man), un_man, float(preco_man), fornecedor_man, loc_inicial, item_encontrado_id))
                    else:
                        cursor.execute("""
                            INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """, (cod_man, desc_man, float(qtd_man), un_man, float(preco_man), fornecedor_man, loc_inicial))
                        
                    cursor.execute("""
                        INSERT INTO historico_estoque 
                        (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, ('ENTRADA MANUAL', desc_man, float(qtd_man), un_man, loc_inicial, proj_man, 'Manual', usuario_atual))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    st.cache_data.clear()
                    st.success("Entrada manual registrada e somada ao estoque com sucesso! O item foi enviado para a aba de Endereçamento.")
                except Exception as e:
                    st.error(f"Erro ao salvar lançamento manual: {e}")

@st.fragment
def renderizar_aba_xml(df_estoque, usuario_atual):
    st.subheader("Entrada Automatizada via XML de Nota Fiscal (NF-e) — Setor Fiscal")
    if "limpar_xml" not in st.session_state:
        st.session_state["limpar_xml"] = False

    arquivo_xml = st.file_uploader("Faça o upload do arquivo XML da NF-e", type=["xml"], key="uploader_xml_ativo_frag" if not st.session_state["limpar_xml"] else "uploader_xml_limpo_frag")
    if arquivo_xml is not None:
        st.session_state["limpar_xml"] = False
        try:
            bytes_xml = arquivo_xml.read()
            tree = ET.parse(io.BytesIO(bytes_xml))
            root = tree.getroot()
            ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
            emit = root.find('.//nfe:emit', ns)
            nome_fornecedor = emit.find('nfe:xNome', ns).text if emit is not None and emit.find('nfe:xNome', ns) is not None else "Fornecedor Desconhecido"
            st.markdown(f"**Fornecedor Identificado:** {nome_fornecedor}")
            det_items = root.findall('.//nfe:det', ns)
            lista_produtos = []
            for det in det_items:
                prod = det.find('nfe:prod', ns)
                if prod is not None:
                    codigo = prod.find('nfe:cProd', ns).text if prod.find('nfe:cProd', ns) is not None else ""
                    descricao = prod.find('nfe:xProd', ns).text if prod.find('nfe:xProd', ns) is not None else ""
                    quantidade = float(prod.find('nfe:qCom', ns).text) if prod.find('nfe:qCom', ns) is not None else 0.0
                    
                    raw_unidade = prod.find('nfe:uCom', ns).text if prod.find('nfe:uCom', ns) is not None else "UN"
                    unidade = validar_unidade(raw_unidade)

                    valor_unit = float(prod.find('nfe:vUnCom', ns).text) if prod.find('nfe:vUnCom', ns) is not None else 0.0
                    lista_produtos.append({"codigo": codigo, "descricao": descricao, "quantidade": quantidade, "unidade": unidade, "preco_unitario": valor_unit, "fornecedor": nome_fornecedor})
            
            df_xml = pd.DataFrame(lista_produtos)
            st.dataframe(df_xml, use_container_width=True)
            with st.form("form_xml_entrada_frag"):
                projeto_destino = st.text_input("Projeto de Destino para os Itens", value="GERAL / ALMOXARIFADO")
                btn_confirma_xml = st.form_submit_button("Confirmar Importação Fiscal e Enviar para A Endereçar", type="primary")
                if btn_confirma_xml:
                    try:
                        conn = db.get_db_connection()
                        cursor = conn.cursor()
                        
                        for item in lista_produtos:
                            loc_recebido = f"Projeto: {projeto_destino} - (A Endereçar)"
                            item_qtd = float(item["quantidade"])
                            item_preco = float(item["preco_unitario"])
                            
                            desc_norm = strip_accents(item["descricao"]).upper()
                            item_encontrado_id = None
                            
                            if not df_estoque.empty:
                                for _, r_chk in df_estoque.iterrows():
                                    if strip_accents(r_chk['item']).upper() == desc_norm or str(r_chk['codigo']).strip().upper() == str(item["codigo"]).strip().upper():
                                        item_encontrado_id = int(r_chk['id'])
                                        break
                            
                            if item_encontrado_id:
                                cursor.execute("""
                                    UPDATE estoque 
                                    SET quantidade = quantidade + %s, unidade = %s, preco_unitario = %s, ultimo_fornecedor = %s, localizacao = %s 
                                    WHERE id = %s;
                                """, (item_qtd, item["unidade"], item_preco, item["fornecedor"], loc_recebido, item_encontrado_id))
                            else:
                                cursor.execute("""
                                    INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                                """, (item["codigo"], item["descricao"], item_qtd, item["unidade"], item_preco, item["fornecedor"], loc_recebido))
                                
                            cursor.execute("""
                                INSERT INTO historico_estoque 
                                (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) 
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                            """, ('ENTRADA XML', item["descricao"], item_qtd, item["unidade"], loc_recebido, projeto_destino, 'Fiscal', usuario_atual))
                            
                        conn.commit()
                        cursor.close()
                        conn.close()
                        st.cache_data.clear()
                        st.session_state["limpar_xml"] = True
                        st.success("Nota Fiscal importada com sucesso! Os itens já aparecem na aba de Endereçamento do Almoxarifado.")
                    except Exception as ex_db:
                        st.error(f"Erro ao salvar no banco de dados: {ex_db}")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo XML: {e}")

@st.fragment
def renderizar_aba_transferencia(df_estoque, usuario_atual):
    st.subheader("Transferência de Saldo entre Projetos / Localizações")
    try:
        if not df_estoque.empty:
            df_trans = df_estoque[df_estoque['quantidade'] > 0].copy()
        else:
            df_trans = pd.DataFrame()

        if df_trans.empty:
            st.warning("Não há itens com saldo disponível para transferência.")
        else:
            with st.form("form_transferencia_frag"):
                item_trans_idx = st.selectbox("Selecione o Item", options=df_trans.index, format_func=lambda x: f"{df_trans.loc[x, 'codigo']} - {df_trans.loc[x, 'item']} (Qtd: {df_trans.loc[x, 'quantidade']} | Loc: {df_trans.loc[x, 'localizacao']})")
                qtd_trans = st.number_input("Quantidade a Transferir", min_value=0.01, step=1.0)
                novo_projeto = st.text_input("Novo Projeto / Destino *").strip()
                btn_exec_trans = st.form_submit_button("🔄 Efetuar Transferência", type="primary", use_container_width=True)
                if btn_exec_trans:
                    if not novo_projeto:
                        st.warning("Informe o novo projeto de destino.")
                    else:
                        it = df_trans.loc[item_trans_idx]
                        item_qtd_trans = float(qtd_trans)
                        if item_qtd_trans > float(it['quantidade']):
                            st.error("Quantidade superior ao saldo atual.")
                        else:
                            try:
                                conn = db.get_db_connection()
                                cursor = conn.cursor()
                                cursor.execute("UPDATE estoque SET quantidade = quantidade - %s WHERE id = %s;", (item_qtd_trans, int(it['id'])))
                                loc_novo = f"Projeto: {novo_projeto}"
                                cursor.execute("INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao) VALUES (%s, %s, %s, %s, %s, %s, %s);", (it['codigo'], it['item'], item_qtd_trans, 'UN', 0.0, 'Transferência', loc_novo))
                                cursor.execute("INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);", ('TRANSFERENCIA', it['item'], item_qtd_trans, 'UN', loc_novo, it['localizacao'], 'Sistema', usuario_atual))
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.cache_data.clear()
                                st.success("Transferência realizada com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao executar transferência: {e}")
    except Exception as e:
        st.error(f"Erro: {e}")

@st.fragment
def renderizar_aba_estorno(perfil_norm, is_admin, usuario_atual):
    st.subheader("⚠️ Painel de Estorno e Histórico de Movimentações")
    is_gestao = "gestao" in perfil_norm or "administrador" in perfil_norm or "admin" in perfil_norm or is_admin
    try:
        conn = db.get_db_connection()
        df_hist = pd.read_sql("SELECT * FROM historico_estoque ORDER BY data_movimentacao DESC LIMIT 100;", conn)
        conn.close()
        if df_hist.empty:
            st.info("Nenhum histórico de movimentação encontrado.")
        else:
            st.dataframe(df_hist, use_container_width=True)
            if is_gestao:
                st.divider()
                st.markdown("### 🔴 Área de Estorno de Lançamento")
                st.warning("Atenção: O estorno anula a movimentação e reverte os saldos no estoque.")
                with st.form("form_estorno_frag"):
                    dict_hist = {f"ID {r['id']} | [{r['tipo_movimentacao']}] {r['item']} - Qtd: {r['quantidade']} ({r['data_movimentacao']})": r for _, r in df_hist.iterrows()}
                    item_estornar_str = st.selectbox("Selecione a movimentação para estornar", options=list(dict_hist.keys()))
                    motivo_estorno = st.text_input("Motivo do Estorno *", placeholder="Ex: Erro de digitação")
                    btn_exec_estorno = st.form_submit_button("⚠️ Confirmar Estorno da Movimentação", type="primary")
                    if btn_exec_estorno:
                        if not motivo_estorno.strip():
                            st.error("Informe o motivo do estorno.")
                        else:
                            reg = dict_hist[item_estornar_str]
                            reg_id = int(reg['id'])
                            tipo_mov = reg['tipo_movimentacao']
                            nome_item = reg['item']
                            qtd_mov = float(reg['quantidade'])
                            loc_mov = reg['localizacao']
                            try:
                                conn_est = db.get_db_connection()
                                cur_est = conn_est.cursor()
                                if tipo_mov in ['ENTRADA MANUAL', 'ENTRADA XML', 'ENDEREÇAMENTO', 'BAIXA SA']:
                                    cur_est.execute("UPDATE estoque SET quantidade = quantidade - %s WHERE item ILIKE %s AND quantidade >= %s;", (qtd_mov, nome_item, qtd_mov))
                                elif tipo_mov == 'BAIXA':
                                    cur_est.execute("UPDATE estoque SET quantidade = quantidade + %s WHERE item ILIKE %s;", (qtd_mov, nome_item))
                                cur_est.execute("INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);", ('ESTORNO', nome_item, qtd_mov, 'UN', loc_mov, f"Estorno Ref. ID {reg_id}: {motivo_estorno}", 'Gestão', usuario_atual))
                                conn_est.commit()
                                cur_est.close()
                                conn_est.close()
                                st.cache_data.clear()
                                st.success("Movimentação estornada com sucesso!")
                            except Exception as err_est:
                                st.error(f"Erro ao processar estorno: {err_est}")
            else:
                st.info("🔒 A função de estorno é restrita aos perfis de Gestão e Administração.")
    except Exception:
        st.info("Tabela de histórico de movimentações ainda não inicializada ou vazia.")


# --- FUNÇÃO PRINCIPAL DE RENDERIZAÇÃO ---

def render(perfil_atual="Administrador"):
    st.markdown("## 📦 Controle de Estoque & Almoxarifado")
    
    garantir_tabelas_sistema()
    unificar_duplicados_estoque()

    usuario_atual = (
        st.session_state.get("usuario_logado") 
        or st.session_state.get("user_token") 
        or "Sistema"
    )

    perfil_real = str(perfil_atual)
    try:
        conn_p = db.get_db_connection()
        df_user = pd.read_sql_query("SELECT perfil FROM usuarios WHERE username = %s OR usuario = %s", conn_p, params=(str(usuario_atual), str(usuario_atual)))
        conn_p.close()
        if not df_user.empty and df_user["perfil"].iloc[0]:
            perfil_real = str(df_user["perfil"].iloc[0])
    except Exception:
        pass

    perfil_norm = strip_accents(perfil_real)
    is_admin = "admin" in perfil_norm
    
    is_almoxarife_ou_gestao = (
        "almoxarife" in perfil_norm
        or "gestao" in perfil_norm
        or "gestor" in perfil_norm
        or "admin" in perfil_norm
        or is_admin
        or st.session_state.get("permissoes", {}).get("pode_enderecar_estoque", False)
    )

    is_gestao_geral = (
        "gestao" in perfil_norm
        or "admin" in perfil_norm
        or is_admin
        or "geral" in perfil_norm
        or perfil_real == "Gestão Geral"
    )

    df_estoque = carregar_estoque_cached()

    try:
        if not df_estoque.empty and 'localizacao' in df_estoque.columns:
            df_metricas = df_estoque[~df_estoque['localizacao'].astype(str).str.contains('A Chegar|A Endereçar', na=False)]
            total_skus = len(df_metricas)
            skus_zerados = len(df_metricas[df_metricas['quantidade'] <= 0]) if 'quantidade' in df_metricas.columns else 0
            if 'quantidade' in df_metricas.columns and 'preco_unitario' in df_metricas.columns:
                valor_total = (df_metricas['quantidade'] * df_metricas['preco_unitario']).sum()
            else:
                valor_total = 0.0
        else:
            total_skus = 0
            skus_zerados = 0
            valor_total = 0.0
    except Exception:
        total_skus = 0
        skus_zerados = 0
        valor_total = 0.0

    st.markdown("""
        <style>
        .metric-card {
            background-color: #161b22;
            border: 1px solid #30363d;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .metric-title {
            color: #8b949e; font-size: 16px; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;
        }
        .metric-value { color: #58a6ff; font-size: 26px; font-weight: 700; }
        .metric-value-alert { color: #f85149; font-size: 26px; font-weight: 700; }
        </style>
    """, unsafe_allow_html=True)

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>Valor Total em Estoque</div><div class='metric-value'>R$ {valor_total:,.2f}</div></div>", unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>Total de SKUs Ativos</div><div class='metric-value'>{total_skus}</div></div>", unsafe_allow_html=True)
    with col_m3:
        val_class = "metric-value-alert" if skus_zerados > 0 else "metric-value"
        st.markdown(f"<div class='metric-card'><div class='metric-title'>SKUs Zerados</div><div class='{val_class}'>{skus_zerados}</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if is_almoxarife_ou_gestao:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "Consultar Estoque", 
            "Endereçamento & Trânsito", 
            "Montar Carrinho / SA", 
            "Gerenciar SAs (Almoxarifado)",
            "Lançamento Manual", 
            "Entrada por XML", 
            "Transferência de Saldo", 
            "Estorno & Histórico"
        ])
    else:
        tab1, tab3 = st.tabs([
            "Consultar Estoque", 
            "Montar Carrinho / SA"
        ])

    with tab1:
        renderizar_aba_consulta(df_estoque, is_almoxarife_ou_gestao, is_gestao_geral)

    if is_almoxarife_ou_gestao:
        with tab2:
            renderizar_aba_enderecamento(usuario_atual, is_almoxarife_ou_gestao)

    with tab3:
        renderizar_carrinho_sa(df_estoque, usuario_atual)

    if is_almoxarife_ou_gestao:
        with tab4:
            renderizar_aba_gerenciar_sas(usuario_atual, is_almoxarife_ou_gestao)

        with tab5:
            renderizar_aba_lancamento_manual(df_estoque, usuario_atual)

        with tab6:
            renderizar_aba_xml(df_estoque, usuario_atual)

        with tab7:
            renderizar_aba_transferencia(df_estoque, usuario_atual)

        with tab8:
            renderizar_aba_estorno(perfil_norm, is_admin, usuario_atual)
