-- schema.sql
-- Esquema do banco de dados do Sistema de Gestão de Barbearia
-- Modelo relacional simples, normalizado, cobrindo clientes, serviços,
-- barbeiros e atendimentos (agendamentos/vendas realizadas).
--
-- Cada barbearia só enxerga os próprios dados: toda tabela tem a coluna
-- barbearia_id, e toda consulta em models.py e reports.py filtra por ela.

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
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id)
);

CREATE TABLE servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    duracao_minutos INTEGER NOT NULL DEFAULT 30,
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

-- Dados iniciais de exemplo (seed) para demonstração
INSERT INTO barbearias (nome) VALUES ('Barbearia Exemplo');

INSERT INTO barbeiros (barbearia_id, nome, comissao_percentual) VALUES
    (1, 'Elenilton Silveira', 50.0),
    (1, 'João Pereira', 40.0);

INSERT INTO servicos (barbearia_id, nome, preco, duracao_minutos) VALUES
    (1, 'Corte Masculino', 35.00, 30),
    (1, 'Barba', 25.00, 20),
    (1, 'Corte + Barba', 55.00, 50),
    (1, 'Sobrancelha', 15.00, 10),
    (1, 'Coloração', 60.00, 60);

INSERT INTO clientes (barbearia_id, nome, telefone) VALUES
    (1, 'Carlos Souza', '(71) 90000-0001'),
    (1, 'Rafael Lima', '(71) 90000-0002'),
    (1, 'Bruno Andrade', '(71) 90000-0003');
