-- schema.sql
-- Esquema do banco de dados do Sistema de Gestão de Barbearia
-- Modelo relacional simples, normalizado, cobrindo clientes, serviços,
-- barbeiros e atendimentos (agendamentos/vendas realizadas).

DROP TABLE IF EXISTS atendimentos;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS servicos;
DROP TABLE IF EXISTS barbeiros;

CREATE TABLE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE barbeiros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    comissao_percentual REAL NOT NULL DEFAULT 40.0
);

CREATE TABLE servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    duracao_minutos INTEGER NOT NULL DEFAULT 30
);

CREATE TABLE atendimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    barbeiro_id INTEGER NOT NULL,
    servico_id INTEGER NOT NULL,
    data_hora TEXT NOT NULL DEFAULT (datetime('now')),
    valor_cobrado REAL NOT NULL,
    forma_pagamento TEXT NOT NULL DEFAULT 'dinheiro',
    FOREIGN KEY (cliente_id) REFERENCES clientes (id),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id),
    FOREIGN KEY (servico_id) REFERENCES servicos (id)
);

-- Dados iniciais de exemplo (seed) para demonstração
INSERT INTO barbeiros (nome, comissao_percentual) VALUES
    ('Elenilton Silveira', 50.0),
    ('João Pereira', 40.0);

INSERT INTO servicos (nome, preco, duracao_minutos) VALUES
    ('Corte Masculino', 35.00, 30),
    ('Barba', 25.00, 20),
    ('Corte + Barba', 55.00, 50),
    ('Sobrancelha', 15.00, 10),
    ('Coloração', 60.00, 60);

INSERT INTO clientes (nome, telefone) VALUES
    ('Carlos Souza', '(71) 90000-0001'),
    ('Rafael Lima', '(71) 90000-0002'),
    ('Bruno Andrade', '(71) 90000-0003');
