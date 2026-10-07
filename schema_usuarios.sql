-- schema_usuarios.sql
-- Tabela de usuários (login) do Sistema de Gestão de Barbearia.
-- Fica separada do schema.sql e usa IF NOT EXISTS para poder ser aplicada
-- em um banco que já tem dados, sem apagar nada (veja database.py).
--
-- Papéis:
--   dono     -> acesso total
--   barbeiro -> vê só os próprios atendimentos e comissões; precisa estar
--               vinculado a um registro da tabela barbeiros

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'barbeiro')),
    barbeiro_id INTEGER,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id),
    CHECK (papel = 'dono' OR barbeiro_id IS NOT NULL)
);
