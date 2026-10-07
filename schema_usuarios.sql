-- schema_usuarios.sql
-- Tabela de usuários (login) do Sistema de Gestão de Barbearia.
-- Fica separada do schema.sql e usa IF NOT EXISTS para poder ser aplicada
-- em um banco que já tem dados, sem apagar nada (veja database.py).
--
-- Todo usuário pertence a uma barbearia e só vê os dados dela.
--
-- Papéis:
--   dono     -> acesso total aos dados da própria barbearia
--   barbeiro -> vê só os próprios atendimentos e comissões; precisa estar
--               vinculado a um registro da tabela barbeiros da mesma
--               barbearia (models.criar_usuario confere isso)

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    usuario TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'barbeiro')),
    barbeiro_id INTEGER,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id),
    CHECK (papel = 'dono' OR barbeiro_id IS NOT NULL)
);

-- Erros de senha seguidos por nome de usuário, para o limite de tentativas
-- do login (models.registrar_falha_de_login). Nomes que não existem também
-- são contados, para o bloqueio não revelar quais usuários existem.
-- Os horários são segundos desde 1970 (time.time()).
CREATE TABLE IF NOT EXISTS tentativas_login (
    usuario TEXT PRIMARY KEY,
    falhas INTEGER NOT NULL,
    ultima_falha REAL NOT NULL,
    bloqueado_ate REAL
);
