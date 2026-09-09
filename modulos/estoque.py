import streamlit as st
import pandas as pd
import database as db
import xml.etree.ElementTree as ET
import io

def render(perfil_atual):
    st.markdown("## 📦 Controle de Estoque")
    
    # Cálculo das Métricas (Valor Total, Total de SKUs e SKUs Zerados)
    try:
        conn = db.get_db_connection()
        df_metricas = pd.read_sql("SELECT quantidade, preco_unitario FROM estoque;", conn)
        conn.close()
        
        if not df_metricas.empty:
            total_skus = len(df_metricas)
            # Conta quantos SKUs estão com quantidade igual ou menor que zero
            skus_zerados = len(df_metricas[df_metricas['quantidade'] <= 0]) if 'quantidade' in df_metricas.columns else 0
            
            if 'quantidade' in df_metricas.columns and 'preco_unitario' in df_metricas.columns:
                df_metricas['total_linha'] = df_metricas['quantidade'] * df_metricas['preco_unitario']
                valor_total = df_metricas['total_linha'].sum()
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
            color: #8b949e;
            font-size: 29px;
            font-weight: 600;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .metric-value {
            color: #58a6ff;
            font-size: 29px;
            font-weight: 700;
        }
        .metric-value-alert {
            color: #f85149;
            font-size: 29px;
            font-weight: 700;
        }
        </style>
    """, unsafe_allow_html=True)

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Valor Total em Estoque</div>
                <div class='metric-value'>R$ {valor_total:,.2f}</div>
            </div>
        """, unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Total de SKUs</div>
                <div class='metric-value'>{total_skus}</div>
            </div>
        """, unsafe_allow_html=True)
    with col_m3:
        # Card de SKUs Zerados ganha cor de alerta se houver rupturas
        val_class = "metric-value-alert" if skus_zerados > 0 else "metric-value"
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>SKUs Zerados</div>
                <div class='{val_class}'>{skus_zerados}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Abas do Módulo de Estoque
    abas = [
        "Consultar Estoque", 
        "Dar Baixa (Carrinho)", 
        "Lançamento Manual", 
        "Entrada por XML", 
        "Transferência de Saldo", 
        "Estorno de Movimentações"
    ]
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(abas)

    # ---------------------------------------------------------
    # TAB 1: CONSULTAR ESTOQUE
    # ---------------------------------------------------------
    with tab1:
        st.subheader("Estoque Atual de Materiais")
        
        pesquisa = st.text_input("🔍 Pesquisar material por código, descrição ou localização...", placeholder="Digite para filtrar...")

        try:
            conn = db.get_db_connection()
            df_estoque = pd.read_sql("SELECT * FROM estoque;", conn)
            conn.close()
            
            if not df_estoque.empty:
                if pesquisa:
                    termo = pesquisa.lower()
                    mask = False
                    for col in ['codigo', 'item', 'descricao', 'localizacao']:
                        if col in df_estoque.columns:
                            mask = mask | df_estoque[col].astype(str).str.lower().str.contains(termo, na=False)
                    df_estoque = df_estoque[mask]

                st.dataframe(df_estoque, use_container_width=True)
            else:
                st.info("Nenhum item cadastrado no estoque atualmente.")
        except Exception as e:
            st.error(f"Erro ao carregar estoque: {e}")

    # ---------------------------------------------------------
    # TAB 2: DAR BAIXA (CARRINHO)
    # ---------------------------------------------------------
    with tab2:
        st.subheader("Saída de Materiais (Carrinho)")
        try:
            conn = db.get_db_connection()
            df_cols = pd.read_sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'estoque';", conn)
            cols = df_cols['column_name'].tolist()
            
            col_desc = "item" if "item" in cols else ("descricao" if "descricao" in cols else "nome")
            
            query = f"SELECT id, codigo, {col_desc} as item, quantidade, unidade, localizacao FROM estoque WHERE quantidade > 0;"
            df_estoque = pd.read_sql(query, conn)
            conn.close()

            if df_estoque.empty:
                st.warning("Não há itens com saldo em estoque para dar baixa.")
            else:
                if "carrinho_baixa" not in st.session_state:
                    st.session_state["carrinho_baixa"] = []

                col_b1, col_b2 = st.columns([2, 1])
                with col_b1:
                    item_selecionado = st.selectbox(
                        "Selecione o Item para Adicionar ao Carrinho",
                        options=df_estoque.index,
                        format_func=lambda x: f"{df_estoque.loc[x, 'codigo']} - {df_estoque.loc[x, 'item']} (Disp: {df_estoque.loc[x, 'quantidade']})"
                    )
                with col_b2:
                    qtd_baixa = st.number_input("Quantidade", min_value=1.0, step=1.0, value=1.0)

                if st.button("➕ Adicionar ao Carrinho"):
                    it = df_estoque.loc[item_selecionado]
                    if qtd_baixa > it['quantidade']:
                        st.error("Quantidade solicitada maior do que o saldo disponível em estoque.")
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
                    st.markdown("### 🛒 Itens no Carrinho de Baixa")
                    df_carrinho = pd.DataFrame(st.session_state["carrinho_baixa"])
                    st.dataframe(df_carrinho, use_container_width=True)

                    destino_baixa = st.text_input("Destino / Setor Requisitante da Baixa *", placeholder="Ex: Manutenção Elétrica")

                    col_acao1, col_acao2 = st.columns(2)
                    with col_acao1:
                        if st.button("🗑️ Limpar Carrinho", use_container_width=True):
                            st.session_state["carrinho_baixa"] = []
                            st.rerun()
                    with col_acao2:
                        if st.button("✅ Confirmar e Efetuar Baixa", type="primary", use_container_width=True):
                            if not destino_baixa.strip():
                                st.warning("Informe o destino/setor requisitante.")
                            else:
                                try:
                                    conn = db.get_db_connection()
                                    cursor = conn.cursor()
                                    usuario_atual = st.session_state.get("usuario_logado", "Sistema")
                                    
                                    for item in st.session_state["carrinho_baixa"]:
                                        item_id = int(item["id"])
                                        item_qtd = float(item["quantidade"])
                                        
                                        cursor.execute("UPDATE estoque SET quantidade = quantidade - %s WHERE id = %s;", (item_qtd, item_id))
                                        
                                        cursor.execute("""
                                            INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                        """, ('BAIXA', item["item"], item_qtd, item.get('unidade', 'UN'), item["localizacao"], destino_baixa, destino_baixa, usuario_atual))
                                        
                                    conn.commit()
                                    cursor.close()
                                    conn.close()

                                    st.success("Baixa realizada com sucesso!")
                                    st.session_state["carrinho_baixa"] = []
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao processar baixa: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar dados para baixa: {e}")

    # ---------------------------------------------------------
    # TAB 3: LANÇAMENTO MANUAL
    # ---------------------------------------------------------
    with tab3:
        st.subheader("Lançamento Manual de Entrada")
        
        try:
            conn_temp = db.get_db_connection()
            df_max = pd.read_sql("SELECT MAX(id) as max_id FROM estoque;", conn_temp)
            conn_temp.close()
            next_id = int(df_max['max_id'].iloc[0]) + 1 if not df_max.empty and pd.notna(df_max['max_id'].iloc[0]) else 1
            codigo_sugerido = f"MAN-{next_id:04d}"
        except Exception:
            codigo_sugerido = "MAN-0001"

        with st.form("form_lancamento_manual"):
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                cod_man = st.text_input("Código do Material *", value=codigo_sugerido).strip()
                desc_man = st.text_input("Descrição do Material *").strip()
                qtd_man = st.number_input("Quantidade *", min_value=0.01, step=1.0)
            with col_l2:
                un_man = st.text_input("Unidade (Ex: UN, PC, KG) *", value="UN").strip()
                preco_man = st.number_input("Preço Unitário (R$)", min_value=0.0, step=0.01)
                proj_man = st.text_input("Projeto de Destino", value="GERAL / ALMOXARIFADO").strip()
            
            fornecedor_man = st.text_input("Fornecedor", value="Diversos").strip()
            
            btn_salvar_manual = st.form_submit_button("💾 Salvar Entrada Manual", type="primary", use_container_width=True)
            
            if btn_salvar_manual:
                if not cod_man or not desc_man or qtd_man <= 0:
                    st.warning("Preencha o código, o item/descrição e uma quantidade válida.")
                else:
                    try:
                        conn = db.get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM estoque WHERE codigo = %s;", (cod_man,))
                        existe = cursor.fetchone()
                        
                        loc_inicial = f"Projeto: {proj_man} - (A Endereçar)"
                        usuario_atual = st.session_state.get("usuario_logado", "Sistema")
                        
                        if existe:
                            cursor.execute("""
                                UPDATE estoque 
                                SET quantidade = quantidade + %s, 
                                    preco_unitario = %s, 
                                    ultimo_fornecedor = %s,
                                    localizacao = %s
                                WHERE codigo = %s;
                            """, (float(qtd_man), float(preco_man), fornecedor_man, loc_inicial, cod_man))
                        else:
                            cursor.execute("""
                                INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao)
                                VALUES (%s, %s, %s, %s, %s, %s, %s);
                            """, (cod_man, desc_man, float(qtd_man), un_man, float(preco_man), fornecedor_man, loc_inicial))
                        
                        cursor.execute("""
                            INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                        """, ('ENTRADA MANUAL', desc_man, float(qtd_man), un_man, loc_inicial, proj_man, 'Manual', usuario_atual))
                        
                        conn.commit()
                        cursor.close()
                        conn.close()
                        st.success("Entrada manual registrada com sucesso! O item foi enviado para a aba de Endereçamento.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar lançamento manual: {e}")

    # ---------------------------------------------------------
    # TAB 4: ENTRADA POR XML
    # ---------------------------------------------------------
    with tab4:
        st.subheader("Entrada Automatizada via XML de Nota Fiscal (NF-e)")
        
        if "limpar_xml" not in st.session_state:
            st.session_state["limpar_xml"] = False

        arquivo_xml = st.file_uploader(
            "Faça o upload do arquivo XML da NF-e", 
            type=["xml"], 
            key="uploader_xml_ativo" if not st.session_state["limpar_xml"] else "uploader_xml_limpo"
        )
        
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
                        unidade = prod.find('nfe:uCom', ns).text if prod.find('nfe:uCom', ns) is not None else "UN"
                        valor_unit = float(prod.find('nfe:vUnCom', ns).text) if prod.find('nfe:vUnCom', ns) is not None else 0.0
                        
                        lista_produtos.append({
                            "codigo": codigo,
                            "descricao": descricao,
                            "quantidade": quantidade,
                            "unidade": unidade,
                            "preco_unitario": valor_unit,
                            "fornecedor": nome_fornecedor
                        })
                
                df_xml = pd.DataFrame(lista_produtos)
                st.dataframe(df_xml, use_container_width=True)
                
                with st.form("form_xml_entrada"):
                    projeto_destino = st.text_input("Projeto de Destino para os Itens", value="GERAL / ALMOXARIFADO")
                    
                    btn_confirma_xml = st.form_submit_button("Confirmar Importação e Enviar para A Endereçar", type="primary")
                    
                    if btn_confirma_xml:
                        try:
                            conn = db.get_db_connection()
                            cursor = conn.cursor()
                            usuario_atual = st.session_state.get("usuario_logado", "Sistema")
                            
                            for item in lista_produtos:
                                loc_recebido = f"Projeto: {projeto_destino} - (A Endereçar)"
                                item_qtd = float(item["quantidade"])
                                item_preco = float(item["preco_unitario"])
                                
                                cursor.execute("SELECT id FROM estoque WHERE codigo = %s;", (item["codigo"],))
                                existe = cursor.fetchone()
                                
                                if existe:
                                    cursor.execute("""
                                        UPDATE estoque 
                                        SET quantidade = quantidade + %s, 
                                            preco_unitario = %s, 
                                            ultimo_fornecedor = %s,
                                            localizacao = %s
                                        WHERE codigo = %s;
                                    """, (item_qtd, item_preco, item["fornecedor"], loc_recebido, item["codigo"]))
                                else:
                                    cursor.execute("""
                                        INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                                    """, (item["codigo"], item["descricao"], item_qtd, item["unidade"], item_preco, item["fornecedor"], loc_recebido))
                                
                                cursor.execute("""
                                    INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                """, ('ENTRADA XML', item["descricao"], item_qtd, item["unidade"], loc_recebido, projeto_destino, 'Fiscal', usuario_atual))
                            
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            st.session_state["limpar_xml"] = True
                            st.success("Nota Fiscal importada com sucesso! Os itens já aparecem na aba 'Materiais Recebidos / A Endereçar' do Almoxarifado.")
                            st.rerun()
                        except Exception as ex_db:
                            st.error(f"Erro ao salvar no banco de dados: {ex_db}")
                            
            except Exception as e:
                st.error(f"Erro ao ler o arquivo XML. Verifique se o formato é uma NF-e válida: {e}")

    # ---------------------------------------------------------
    # TAB 5: TRANSFERÊNCIA DE SALDO
    # ---------------------------------------------------------
    with tab5:
        st.subheader("Transferência de Saldo entre Projetos")
        try:
            conn = db.get_db_connection()
            df_cols = pd.read_sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'estoque';", conn)
            cols = df_cols['column_name'].tolist()
            col_desc = "item" if "item" in cols else ("descricao" if "descricao" in cols else "nome")
            
            query = f"SELECT id, codigo, {col_desc} as item, quantidade, unidade, localizacao FROM estoque WHERE quantidade > 0;"
            df_trans = pd.read_sql(query, conn)
            conn.close()

            if df_trans.empty:
                st.warning("Não há itens disponíveis para transferência.")
            else:
                with st.form("form_transferencia"):
                    item_trans_idx = st.selectbox(
                        "Selecione o Item",
                        options=df_trans.index,
                        format_func=lambda x: f"{df_trans.loc[x, 'codigo']} - {df_trans.loc[x, 'item']} (Qtd: {df_trans.loc[x, 'quantidade']} | Loc: {df_trans.loc[x, 'localizacao']})"
                    )
                    
                    qtd_trans = st.number_input("Quantidade a Transferir", min_value=0.01, step=1.0)
                    novo_projeto = st.text_input("Novo Projeto de Destino *").strip()
                    
                    btn_exec_trans = st.form_submit_button("🔄 Efetuar Transferência", type="primary", use_container_width=True)
                    
                    if btn_exec_trans:
                        if not novo_projeto:
                            st.warning("Informe o novo projeto de destino.")
                        else:
                            it = df_trans.loc[item_trans_idx]
                            item_qtd_trans = float(qtd_trans)
                            item_id = int(it['id'])
                            
                            if item_qtd_trans > float(it['quantidade']):
                                st.error("Quantidade para transferência superior ao saldo atual do item.")
                            else:
                                try:
                                    conn = db.get_db_connection()
                                    cursor = conn.cursor()
                                    usuario_atual = st.session_state.get("usuario_logado", "Sistema")
                                    
                                    cursor.execute("UPDATE estoque SET quantidade = quantidade - %s WHERE id = %s;", (item_qtd_trans, item_id))
                                    
                                    loc_novo = f"Projeto: {novo_projeto}"
                                    cursor.execute("""
                                        INSERT INTO estoque (codigo, item, quantidade, unidade, preco_unitario, ultimo_fornecedor, localizacao)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                                    """, (it['codigo'], it['item'], item_qtd_trans, 'UN', 0.0, 'Transferência', loc_novo))
                                    
                                    cursor.execute("""
                                        INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                    """, ('TRANSFERENCIA', it['item'], item_qtd_trans, 'UN', loc_novo, it['localizacao'], 'Sistema', usuario_atual))
                                    
                                    conn.commit()
                                    cursor.close()
                                    conn.close()
                                    
                                    st.success("Transferência realizada com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao executar transferência: {e}")
        except Exception as e:
            st.error(f"Erro ao carregar dados para transferência: {e}")

    # ---------------------------------------------------------
    # TAB 6: ESTORNO E HISTÓRICO DE MOVIMENTAÇÕES (RESTRITO PARA GESTÃO)
    # ---------------------------------------------------------
    with tab6:
        st.subheader("⚠️ Painel de Estorno e Histórico de Movimentações")
        
        is_gestao = perfil_atual in ["Gestão Geral", "Gestor"] or st.session_state.get("permissoes", {}).get("e_admin", False)

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

                    with st.form("form_estorno"):
                        dict_hist = {
                            f"ID {r['id']} | [{r['tipo_movimentacao']}] {r['item']} - Qtd: {r['quantidade']} ({r['data_movimentacao']})": r
                            for _, r in df_hist.iterrows()
                        }
                        
                        item_estornar_str = st.selectbox("Selecione a movimentação para estornar", options=list(dict_hist.keys()))
                        motivo_estorno = st.text_input("Motivo do Estorno *", placeholder="Ex: Erro de digitação na nota")
                        
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
                                usuario_atual = st.session_state.get("usuario_logado", "Sistema")
                                
                                try:
                                    conn_est = db.get_db_connection()
                                    cur_est = conn_est.cursor()
                                    
                                    if tipo_mov in ['ENTRADA MANUAL', 'ENTRADA XML', 'ENDEREÇAMENTO']:
                                        cur_est.execute("""
                                            UPDATE estoque 
                                            SET quantidade = quantidade - %s 
                                            WHERE item ILIKE %s AND quantidade >= %s;
                                        """, (qtd_mov, nome_item, qtd_mov))
                                    elif tipo_mov == 'BAIXA':
                                        cur_est.execute("""
                                            UPDATE estoque 
                                            SET quantidade = quantidade + %s 
                                            WHERE item ILIKE %s;
                                        """, (qtd_mov, nome_item))
                                        
                                    cur_est.execute("""
                                        INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                    """, ('ESTORNO', nome_item, qtd_mov, 'UN', loc_mov, f"Estorno Ref. ID {reg_id}: {motivo_estorno}", 'Gestão', usuario_atual))
                                    
                                    conn_est.commit()
                                    cur_est.close()
                                    conn_est.close()
                                    
                                    st.success(f"Movimentação estornada com sucesso! Saldos revertidos.")
                                    st.rerun()
                                except Exception as err_est:
                                    st.error(f"Erro ao processar estorno: {err_est}")
                else:
                    st.info("🔒 A visualização do histórico está liberada, mas a função de **Estorno** é restrita aos perfis de Gestão Geral e Gestores.")
        except Exception:
            st.info("Tabela de histórico de movimentações ainda não inicializada ou vazia.")
