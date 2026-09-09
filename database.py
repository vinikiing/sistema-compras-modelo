import os
import streamlit as st
import psycopg2

def get_db_connection():
    db_url = "postgresql://postgres:tmJFapQqfvspySMVyEoGShHsEGrsaTvT@kodama.proxy.rlwy.net:24855/railway"
    if not db_url:
        raise ValueError("URL do banco não informada.")
    return psycopg2.connect(db_url, sslmode='require')

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(100),
            item VARCHAR(255) NOT NULL,
            localizacao VARCHAR(255) NOT NULL,
            setor_categoria VARCHAR(100),
            quantidade NUMERIC(10,2) DEFAULT 0,
            unidade VARCHAR(20) DEFAULT 'UN',
            preco_unitario NUMERIC(10,2) DEFAULT 0.0,
            ultimo_fornecedor VARCHAR(255),
            data_ultima_compra VARCHAR(50),
            usuario_registro VARCHAR(100)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id SERIAL PRIMARY KEY,
            projeto VARCHAR(255) NOT NULL,
            setor VARCHAR(100),
            valor_orcado NUMERIC(12,2) DEFAULT 0.0
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id SERIAL PRIMARY KEY,
            projeto VARCHAR(255) NOT NULL,
            setor VARCHAR(100),
            item VARCHAR(255),
            qtd NUMERIC(10,2) DEFAULT 1,
            preco_inicial NUMERIC(12,2) DEFAULT 0.0,
            preco_fechado NUMERIC(12,2) DEFAULT 0.0,
            fornecedor VARCHAR(255)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS centros_custo (
            id SERIAL PRIMARY KEY,
            nome_centro VARCHAR(255) UNIQUE NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS depara_fornecedor (
            id SERIAL PRIMARY KEY,
            cnpj_fornecedor VARCHAR(20) NOT NULL,
            codigo_fornecedor VARCHAR(100) NOT NULL,
            descricao_nota VARCHAR(255),
            id_estoque INTEGER NOT NULL,
            CONSTRAINT uq_depara UNIQUE (cnpj_fornecedor, codigo_fornecedor)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            perfil VARCHAR(50) NOT NULL,
            pode_ver_saving BOOLEAN DEFAULT TRUE,
            pode_importar_saving BOOLEAN DEFAULT FALSE,
            pode_gerenciar_budgets BOOLEAN DEFAULT FALSE,
            pode_consultar_estoque BOOLEAN DEFAULT TRUE,
            pode_dar_entrada_estoque BOOLEAN DEFAULT FALSE,
            pode_dar_baixa_estoque BOOLEAN DEFAULT FALSE,
            pode_enderecar_estoque BOOLEAN DEFAULT FALSE,
            pode_transferir_estoque BOOLEAN DEFAULT FALSE,
            pode_estornar_estoque BOOLEAN DEFAULT FALSE,
            pode_ver_relatorios BOOLEAN DEFAULT TRUE,
            e_admin BOOLEAN DEFAULT FALSE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_estoque (
            id SERIAL PRIMARY KEY,
            data_movimentacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tipo_movimentacao VARCHAR(50),
            item VARCHAR(255),
            quantidade NUMERIC(10,2),
            unidade VARCHAR(20),
            localizacao VARCHAR(255),
            projeto_motivo VARCHAR(255),
            retirado_por VARCHAR(100),
            usuario_sistema VARCHAR(100)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_logins (
            id SERIAL PRIMARY KEY,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username VARCHAR(100),
            perfil VARCHAR(50)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id SERIAL PRIMARY KEY,
            numero_sc INTEGER DEFAULT 1,
            data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            projeto VARCHAR(255) NOT NULL,
            item VARCHAR(255) NOT NULL,
            quantidade NUMERIC(10,2) NOT NULL,
            unidade VARCHAR(20) DEFAULT 'UN',
            fornecedor_sugerido VARCHAR(255),
            status VARCHAR(100) DEFAULT 'Pendente Aprovação Gestor',
            solicitante VARCHAR(100),
            f1_nome VARCHAR(255),
            f1_preco NUMERIC(12,2) DEFAULT 0.0,
            f2_nome VARCHAR(255),
            f2_preco NUMERIC(12,2) DEFAULT 0.0,
            f3_nome VARCHAR(255),
            f3_preco NUMERIC(12,2) DEFAULT 0.0,
            fornecedor_escolhido VARCHAR(255),
            preco_escolhido NUMERIC(12,2) DEFAULT 0.0
        );
    """)

    cursor.execute("""
        INSERT INTO usuarios (username, password, perfil, e_admin, pode_ver_saving, pode_consultar_estoque, pode_ver_relatorios) 
        VALUES ('admin', '123', 'Administrador', TRUE, TRUE, TRUE, TRUE)
        ON CONFLICT (username) DO NOTHING;
    """)
    conn.commit()

    # Garante todas as colunas necessárias na tabela compras caso ela já existisse sem elas
    colunas_compras = [
        ("numero_sc", "INTEGER DEFAULT 1"),
        ("f1_nome", "VARCHAR(255)"),
        ("f1_preco", "NUMERIC(12,2) DEFAULT 0.0"),
        ("f2_nome", "VARCHAR(255)"),
        ("f2_preco", "NUMERIC(12,2) DEFAULT 0.0"),
        ("f3_nome", "VARCHAR(255)"),
        ("f3_preco", "NUMERIC(12,2) DEFAULT 0.0"),
        ("fornecedor_escolhido", "VARCHAR(255)"),
        ("preco_escolhido", "NUMERIC(12,2) DEFAULT 0.0")
    ]

    for col_nome, col_tipo in colunas_compras:
        try:
            cursor.execute(f"ALTER TABLE compras ADD COLUMN IF NOT EXISTS {col_nome} {col_tipo};")
            conn.commit()
        except Exception:
            conn.rollback()

    cursor.close()
    conn.close()

def obter_opcoes_destino(conn):
    try:
        import pandas as pd
        df_orc = pd.read_sql_query("SELECT DISTINCT projeto FROM orcamentos", conn)
        projs = df_orc["projeto"].dropna().tolist() if not df_orc.empty else []
    except Exception:
        conn.rollback()
        projs = []

    try:
        import pandas as pd
        df_cc = pd.read_sql_query("SELECT DISTINCT nome_centro FROM centros_custo", conn)
        ccs = df_cc["nome_centro"].dropna().tolist() if not df_cc.empty else []
    except Exception:
        conn.rollback()
        ccs = []

    opcoes = sorted(list(set(projs + ccs)))
    if not opcoes:
        opcoes = ["Geral / Sem Projeto"]
    return opcoes
