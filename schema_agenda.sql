-- schema_agenda.sql
-- Tabelas da agenda do MeuBarber: unidades da barbearia, horário de
-- funcionamento, bloqueios dos barbeiros e agendamentos (com um ou mais
-- serviços cada, como uma comanda).
--
-- Fica separado do schema.sql e usa IF NOT EXISTS para poder ser aplicado
-- num banco que já tem dados, sem apagar nada (veja database.py).
--
-- Datas e horas da agenda são o horário local da barbearia, em texto:
-- 'AAAA-MM-DD HH:MM'. Texto nesse formato ordena e compara certo nos dois
-- bancos (SQLite e PostgreSQL).

-- Cada barbearia tem pelo menos uma unidade (a "Principal" é criada junto
-- com a barbearia). Unidade não é apagada, só desativada.
CREATE TABLE IF NOT EXISTS unidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    endereco TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id)
);

-- Faixas de horário em que a unidade atende. dia_semana segue o Python:
-- 0 = segunda ... 6 = domingo. Um dia pode ter mais de uma faixa (manhã e
-- tarde, com o almoço no meio); dia sem faixa = fechado.
CREATE TABLE IF NOT EXISTS horarios_funcionamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    unidade_id INTEGER NOT NULL,
    dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    abre TEXT NOT NULL,
    fecha TEXT NOT NULL,
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id),
    FOREIGN KEY (unidade_id) REFERENCES unidades (id)
);

-- Período em que o barbeiro não atende (folga, almoço, férias, médico).
CREATE TABLE IF NOT EXISTS bloqueios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    barbeiro_id INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    motivo TEXT,
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id)
);

-- Horário marcado. Status:
--   marcado   -> ainda vai acontecer (ocupa a agenda)
--   concluido -> o cliente foi atendido; virou atendimento(s) na gestão
--   faltou    -> o cliente não veio
--   cancelado -> desmarcado (libera o horário)
-- origem: 'balcao' (marcado pela barbearia) ou 'online' (pelo cliente).
CREATE TABLE IF NOT EXISTS agendamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barbearia_id INTEGER NOT NULL,
    unidade_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    barbeiro_id INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'marcado'
        CHECK (status IN ('marcado', 'concluido', 'faltou', 'cancelado')),
    origem TEXT NOT NULL DEFAULT 'balcao',
    observacao TEXT,
    criado_em TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (barbearia_id) REFERENCES barbearias (id),
    FOREIGN KEY (unidade_id) REFERENCES unidades (id),
    FOREIGN KEY (cliente_id) REFERENCES clientes (id),
    FOREIGN KEY (barbeiro_id) REFERENCES barbeiros (id)
);

CREATE INDEX IF NOT EXISTS idx_agendamentos_barbeiro_inicio
    ON agendamentos (barbeiro_id, inicio);

-- Serviços de cada agendamento (a "comanda"). Preço e duração são
-- copiados do serviço na hora de marcar: mudar o preço depois não altera
-- o que já foi combinado com o cliente.
CREATE TABLE IF NOT EXISTS agendamento_servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agendamento_id INTEGER NOT NULL,
    servico_id INTEGER NOT NULL,
    preco REAL NOT NULL,
    duracao_minutos INTEGER NOT NULL,
    FOREIGN KEY (agendamento_id) REFERENCES agendamentos (id),
    FOREIGN KEY (servico_id) REFERENCES servicos (id)
);
