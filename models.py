"""
models.py

Funções de acesso aos dados (clientes, barbeiros, serviços e atendimentos)
do Sistema de Gestão de Barbearia.
"""

from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection

PAPEIS = ("dono", "barbeiro")
TAMANHO_MINIMO_SENHA = 8


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


def buscar_barbeiro(barbeiro_id):
    conn = get_connection()
    barbeiro = conn.execute(
        "SELECT * FROM barbeiros WHERE id = ?", (barbeiro_id,)
    ).fetchone()
    conn.close()
    return barbeiro


# ---------- SERVIÇOS ----------

def listar_servicos():
    conn = get_connection()
    servicos = conn.execute("SELECT * FROM servicos ORDER BY nome").fetchall()
    conn.close()
    return servicos


# ---------- ATENDIMENTOS ----------

def listar_atendimentos(barbeiro_id=None):
    """Lista os atendimentos; com barbeiro_id, só os daquele barbeiro."""
    filtro = ""
    parametros = ()
    if barbeiro_id is not None:
        filtro = "WHERE atendimentos.barbeiro_id = ?"
        parametros = (barbeiro_id,)

    conn = get_connection()
    atendimentos = conn.execute(
        f"""
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
        {filtro}
        ORDER BY atendimentos.data_hora DESC
        """,
        parametros,
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


# ---------- USUÁRIOS ----------

def criar_usuario(usuario, senha, papel, barbeiro_id=None):
    """
    Cadastra um usuário com a senha guardada em hash. Usuário do papel
    'barbeiro' precisa estar vinculado a um barbeiro existente.
    """
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido: {papel!r}. Use 'dono' ou 'barbeiro'.")
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(
            f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )
    if papel == "barbeiro":
        if barbeiro_id is None:
            raise ValueError("Usuário barbeiro precisa de um barbeiro_id.")
        if buscar_barbeiro(barbeiro_id) is None:
            raise ValueError(f"Barbeiro {barbeiro_id} não existe.")
    else:
        barbeiro_id = None

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO usuarios (usuario, senha_hash, papel, barbeiro_id)
        VALUES (?, ?, ?, ?)
        """,
        (usuario, generate_password_hash(senha), papel, barbeiro_id),
    )
    conn.commit()
    conn.close()


def buscar_usuario(usuario_id):
    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    conn.close()
    return usuario


def autenticar(usuario, senha):
    """Retorna o usuário se a senha estiver correta; senão, None."""
    conn = get_connection()
    encontrado = conn.execute(
        "SELECT * FROM usuarios WHERE usuario = ?", (usuario,)
    ).fetchone()
    conn.close()
    if encontrado and check_password_hash(encontrado["senha_hash"], senha):
        return encontrado
    return None
