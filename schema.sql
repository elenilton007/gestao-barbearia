-- schema.sql
-- Esquema do banco de dados do Sistema de Gestão de Barbearia
-- Modelo relacional simples, normalizado, cobrindo clientes, serviços,
-- barbeiros e atendimentos (agendamentos/vendas realizadas).
--
-- Cada barbearia só enxerga os próprios dados: toda tabela tem a coluna
-- barbearia_id, e toda consulta em models.py e reports.py filtra por ela.
--
-- Barbeiros, serviços e usuários não são apagados, só desativados
-- (ativo = 0): os atendimentos antigos continuam apontando para eles.
--
-- Escrito para o SQLite; com DATABASE_URL (PostgreSQL), database.py traduz
-- AUTOINCREMENT, datetime('now') e REAL antes de executar.
-- Os dados de exemplo ficam em dados_exemplo.sql (só no python database.py).

DROP TABLE IF EXISTS tentativas_login;
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS atendimentos;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS servicos;
DROP TABLE IF EXISTS barbeiros;
DROP TABLE IF EXISTS barbearias;

CREATE TABLE barbearias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    telefone TEXT,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id)
);

CREATE TABLE barbeiros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    comissao_percentual REAL NOT NULL DEFAULT 40.0,
    ativo INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id)
);

CREATE TABLE servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    duracao_minutos INTEGER NOT NULL DEFAULT 30,
    ativo INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id)
);

CREATE TABLE atendimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    barbeiro_id INTEGER NOT NULL,
    servico_id INTEGER NOT NULL,
    data_hora TEXT NOT NULL DEFAULT (datetime('now')),
    valor_cobrado REAL NOT NULL,
    forma_pagamento TEXT NOT NULL DEFAULT 'dinheiro',
    -- Percentual de comissão do barbeiro no momento do registro: mudar a
    -- comissão do barbeiro depois não altera os atendimentos já feitos.
    comissao_percentual REAL NOT NULL,
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id),
    FOREIGN KEY (cliente_id) REFERENCES clientes (id),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id),
    FOREIGN KEY (servico_id) REFERENCES servicos (id)
);
