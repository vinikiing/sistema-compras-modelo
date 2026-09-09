import psycopg2

# Conecta direto no banco do Railway que está funcionando
conn = psycopg2.connect(
    "postgresql://postgres:tmJFapQqfvspySMVyEoGShHsEGrsaTvT@kodama.proxy.rlwy.net:24855/railway",
    sslmode="require",
)
cursor = conn.cursor()

# Cria um usuário admin padrão (usuário: admin / senha: 123)
cursor.execute("""
    INSERT INTO usuarios (username, password, perfil, e_admin, pode_ver_saving, pode_consultar_estoque, pode_ver_relatorios) 
    VALUES ('admin', '123', 'Administrador', TRUE, TRUE, TRUE, TRUE)
    ON CONFLICT (username) DO NOTHING;
""")

conn.commit()
cursor.close()
conn.close()

print("✅ Usuário admin criado com sucesso! Pode logar com 'admin' e senha '123'.")
