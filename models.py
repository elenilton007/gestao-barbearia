"""
models.py

Funções de acesso aos dados (clientes, barbeiros, serviços e atendimentos)
do Sistema de Gestão de Barbearia.
"""

from database import get_connection


# ---------- CLIENTES ----------

def listar_clientes():
    conn = get_connection()
    clientes = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    conn.close()
    return clientes


def criar_cliente(nome, telefone=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO clientes (nome, telefone) VALUES (?, ?)",
        (nome, telefone),
    )
    conn.commit()
    conn.close()


# ---------- BARBEIROS ----------

def listar_barbeiros():
    conn = get_connection()
    barbeiros = conn.execute("SELECT * FROM barbeiros ORDER BY nome").fetchall()
    conn.close()
    return barbeiros


# ---------- SERVIÇOS ----------

def listar_servicos():
    conn = get_connection()
    servicos = conn.execute("SELECT * FROM servicos ORDER BY nome").fetchall()
    conn.close()
    return servicos


# ---------- ATENDIMENTOS ----------

def listar_atendimentos():
    conn = get_connection()
    atendimentos = conn.execute(
        """
        SELECT
            atendimentos.id,
            clientes.nome AS cliente,
            barbeiros.nome AS barbeiro,
            servicos.nome AS servico,
            atendimentos.data_hora,
            atendimentos.valor_cobrado,
            atendimentos.forma_pagamento
        FROM atendimentos
        JOIN clientes ON clientes.id = atendimentos.cliente_id
        JOIN barbeiros ON barbeiros.id = atendimentos.barbeiro_id
        JOIN servicos ON servicos.id = atendimentos.servico_id
        ORDER BY atendimentos.data_hora DESC
        """
    ).fetchall()
    conn.close()
    return atendimentos


def criar_atendimento(cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento="dinheiro"):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO atendimentos
            (cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento),
    )
    conn.commit()
    conn.close()
