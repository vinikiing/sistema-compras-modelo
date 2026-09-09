import os
import sys
import database as db
import pandas as pd
import streamlit as st

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
  sys.path.insert(0, ROOT_DIR)


def render_enderecamento():
  st.title("📍 Endereçamento de Estoque (Almoxarifado)")

  conn = db.get_db_connection()
  perfil_atual = st.session_state.get("perfil", "Consulta")
  perm = st.session_state.get("permissoes", {})
  is_admin = perm.get("e_admin", False) or perfil_atual in [
      "Gestão Geral",
      "Gestor",
  ]

  pode_guardar = (
      perfil_atual in ["Almoxarife", "Gestão Geral", "Gestor"]
      or is_admin
      or perm.get("pode_enderecar_estoque", False)
  )

  aba_a1, aba_a2 = st.tabs([
      "🚚 Materiais Que Vão Chegar (A Chegar)",
      "📦 Materiais Recebidos / A Endereçar (Guardar em Lote)",
  ])

  # ---------------------------------------------------------
  # 1. MATERIAIS QUE VÃO CHEGAR (CONFIRMAÇÃO E CANCELAMENTO EM LOTE)
  # ---------------------------------------------------------
  with aba_a1:
    st.subheader("Materiais Solicitados / A Caminho (Importados da Manus)")
    try:
      df_vai_chegar = pd.read_sql_query(
          """
                SELECT id, item, quantidade, unidade, localizacao, ultimo_fornecedor 
                FROM estoque 
                WHERE localizacao LIKE '%A Chegar%' 
                ORDER BY id DESC;
            """,
          conn,
      )
    except Exception:
      df_vai_chegar = pd.DataFrame()

    if df_vai_chegar.empty:
      st.info("Nenhum material pendente de chegada no momento.")
    else:
      st.dataframe(
          df_vai_chegar.rename(columns={
              "id": "ID",
              "item": "Material / Descrição",
              "quantidade": "Qtd",
              "unidade": "Un.",
              "localizacao": "Status / Origem",
              "ultimo_fornecedor": "Fornecedor",
          }),
          use_container_width=True,
          hide_index=True,
      )

      if pode_guardar:
        st.divider()

        col_rec, col_canc = st.columns(2)

        # CONFIRMAÇÃO DE CHEGADA
        with col_rec:
          st.markdown("### 📥 Confirmar Chegada na Fábrica")
          dict_chegar = {
              f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": r
              for _, r in df_vai_chegar.iterrows()
          }

          with st.form("form_confirmar_recebimento_lote"):
            itens_rec_lote = st.multiselect(
                "Selecione os materiais que chegaram *",
                options=list(dict_chegar.keys()),
            )

            if st.form_submit_button(
                "✅ Marcar Como Recebidos (Mover para 'A Endereçar')",
                type="primary",
            ):
              if itens_rec_lote:
                cursor = conn.cursor()
                count_recebidos = 0

                for item_str in itens_rec_lote:
                  obj_rec = dict_chegar[item_str]
                  proj_origem = (
                      obj_rec["localizacao"]
                      .replace("(A Chegar)", "")
                      .replace("Projeto:", "")
                      .strip()
                  )
                  novo_st = f"Projeto: {proj_origem} (A Endereçar)"

                  cursor.execute(
                      "UPDATE estoque SET localizacao = %s WHERE id = %s;",
                      (novo_st, obj_rec["id"]),
                  )
                  count_recebidos += 1

                conn.commit()
                cursor.close()
                st.success(
                    f"🎉 {count_recebidos} material(is) movido(s) para 'A"
                    " Endereçar'!"
                )
                st.rerun()
              else:
                st.error("Selecione pelo menos um material.")

        # CANCELAMENTO / EXCLUSÃO DE TESTES
        with col_canc:
          st.markdown("### 🗑️ Cancelar / Apagar Itens de Teste")
          dict_canc = {
              f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": (
                  r["id"]
              )
              for _, r in df_vai_chegar.iterrows()
          }

          with st.form("form_cancelar_itens_a_chegar"):
            itens_canc_lote = st.multiselect(
                "Selecione os materiais para cancelar/excluir *",
                options=list(dict_canc.keys()),
            )

            if st.form_submit_button(
                "🔴 Cancelar / Excluir Itens Selecionados", type="primary"
            ):
              if itens_canc_lote:
                cursor = conn.cursor()
                ids_apagar = [
                    dict_canc[item_key] for item_key in itens_canc_lote
                ]

                cursor.execute(
                    "DELETE FROM estoque WHERE id IN %s;", (tuple(ids_apagar),)
                )
                conn.commit()
                cursor.close()
                st.success(
                    f"🗑️ {len(ids_apagar)} item(ns) de teste apagado(s) do"
                    " estoque com sucesso!"
                )
                st.rerun()
              else:
                st.error("Selecione pelo menos um item para excluir.")

  # ---------------------------------------------------------
  # 2. MATERIAIS RECEBIDOS AGUARDANDO ENDEREÇAMENTO FÍSICO
  # ---------------------------------------------------------
  with aba_a2:
    st.subheader(
        "Materiais Recebidos / Aguardando Endereçamento no Armário"
    )
    try:
      df_enderecar = pd.read_sql_query(
          """
                SELECT id, item, quantidade, unidade, localizacao, ultimo_fornecedor 
                FROM estoque 
                WHERE localizacao LIKE '%A Endereçar%' 
                ORDER BY id DESC;
            """,
          conn,
      )
    except Exception:
      df_enderecar = pd.DataFrame()

    if df_enderecar.empty:
      st.success(
          "🎉 Nenhum material aguardando endereçamento no momento."
      )
    else:
      st.dataframe(
          df_enderecar.rename(columns={
              "id": "ID",
              "item": "Material / Descrição",
              "quantidade": "Qtd",
              "unidade": "Un.",
              "localizacao": "Status / Origem",
              "ultimo_fornecedor": "Fornecedor",
          }),
          use_container_width=True,
          hide_index=True,
      )

      st.divider()

      if pode_guardar:
        st.markdown(
            "### 📍 Guardar Material no Endereço Físico (Em Lote)"
        )

        try:
          df_locs_exist = pd.read_sql_query(
              """
                        SELECT DISTINCT localizacao 
                        FROM estoque 
                        WHERE localizacao NOT LIKE '%A Chegar%' 
                          AND localizacao NOT LIKE '%A Endereçar%' 
                          AND localizacao NOT LIKE 'Projeto:%'
                        ORDER BY localizacao ASC;
                    """,
              conn,
          )
          locs_fiscais_existentes = (
              df_locs_exist["localizacao"].dropna().tolist()
              if not df_locs_exist.empty
              else []
          )
        except Exception:
          locs_fiscais_existentes = []

        dict_end = {
            f"ID {r['id']} | {r['item']} ({r['quantidade']} {r['unidade']})": r
            for _, r in df_enderecar.iterrows()
        }

        # Sem st.form para permitir atualização instantânea da tela ao marcar o checkbox
        itens_sel_lote = st.multiselect(
            "Selecione os materiais para guardar juntos *",
            options=list(dict_end.keys()),
            key="multiselect_enderecar_lote",
        )

        is_novo_local = st.checkbox(
            "✍️ Cadastrar um NOVO Endereço Físico (Armário e Prateleira)",
            value=False if locs_fiscais_existentes else True,
            key="check_cadastrar_novo_local",
        )

        local_final_sel = ""

        if not is_novo_local and locs_fiscais_existentes:
          local_final_sel = st.selectbox(
              "Selecione um Endereço Existente *", locs_fiscais_existentes
          )
        else:
          col_arm, col_prat = st.columns(2)
          armario_input = col_arm.text_input(
              "Armário / Corredor *", placeholder="Ex: ARMÁRIO A"
          )
          prateleira_input = col_prat.text_input(
              "Prateleira / Gaveta *", placeholder="Ex: PRATELEIRA 2"
          )

          if armario_input and prateleira_input:
            local_final_sel = (
                f"{armario_input.strip()} - {prateleira_input.strip()}"
            )
          elif armario_input:
            local_final_sel = armario_input.strip()
          else:
            local_final_sel = prateleira_input.strip()

        st.write("")
        if st.button(
            "📍 Confirmar Endereçamento do Lote",
            type="primary",
            use_container_width=True,
        ):
          if itens_sel_lote and local_final_sel.strip():
            cursor = conn.cursor()
            count_guardados = 0

            for item_str in itens_sel_lote:
              obj_item = dict_end[item_str]
              cursor.execute(
                  "UPDATE estoque SET localizacao = %s WHERE id = %s;",
                  (local_final_sel.strip(), obj_item["id"]),
              )

              cursor.execute(
                  """
                                        INSERT INTO historico_estoque (tipo_movimentacao, item, quantidade, unidade, localizacao, projeto_motivo, retirado_por, usuario_sistema)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                    """,
                  (
                      "ENDEREÇAMENTO",
                      obj_item["item"],
                      obj_item["quantidade"],
                      obj_item["unidade"],
                      local_final_sel.strip(),
                      "Armazenamento Físico em Lote",
                      "Almoxarife/Gestão",
                      st.session_state.get("usuario_logado", "Sistema"),
                  ),
              )

              count_guardados += 1

            conn.commit()
            cursor.close()
            st.success(
                f"🎉 {count_guardados} material(is) guardado(s) em"
                f" '{local_final_sel.strip()}'!"
            )
            st.rerun()
          else:
            st.error(
                "Selecione ao menos um material e preencha o novo endereço"
                " físico."
            )
      else:
        st.info("🔒 Seu perfil possui permissão apenas para visualização.")

  conn.close()
