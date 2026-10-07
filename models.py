"""
models.py

Funções de acesso aos dados (barbearias, clientes, barbeiros, serviços,
atendimentos e usuários) do Sistema de Gestão de Barbearia.

Cada barbearia só vê os próprios dados: as funções recebem o barbearia_id
como primeiro argumento e filtram (ou gravam) sempre por ele.
"""

import time

from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection

PAPEIS = ("dono", "barbeiro")
TAMANHO_MINIMO_SENHA = 8
MAXIMO_FALHAS_LOGIN = 5
TEMPO_BLOQUEIO_LOGIN = 15 * 60  # segundos


def _agora():
    return time.time()


def _validar_senha(senha):
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(
            f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )


# ---------- BARBEARIAS ----------

def listar_barbearias():
    conn = get_connection()
    barbearias = conn.execute("SELECT * FROM barbearias ORDER BY id").fetchall()
    conn.close()
    return barbearias


def buscar_barbearia(barbearia_id):
    conn = get_connection()
    barbearia = conn.execute(
        "SELECT * FROM barbearias WHERE id = ?", (barbearia_id,)
    ).fetchone()
    conn.close()
    return barbearia


def criar_barbearia_com_dono(nome, usuario, senha):
    """
    Cadastra uma barbearia nova junto com o usuário dono dela. Se o usuário
    não puder ser criado (nome repetido, por exemplo), a barbearia também
    não é. Retorna o id da barbearia.
    """
    _validar_senha(senha)
    conn = get_connection()
    try:
        barbearia_id = conn.execute(
            "INSERT INTO barbearias (nome) VALUES (?)", (nome,)
        ).lastrowid
        conn.execute(
            """
            INSERT INTO usuarios (barbearia_id, usuario, senha_hash, papel)
            VALUES (?, ?, ?, 'dono')
            """,
            (barbearia_id, usuario, generate_password_hash(senha)),
        )
        conn.commit()
    finally:
        conn.close()
    return barbearia_id


# ---------- CLIENTES ----------

def listar_clientes(barbearia_id):
    conn = get_connection()
    clientes = conn.execute(
        "SELECT * FROM clientes WHERE barbearia_id = ? ORDER BY nome",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return clientes


def criar_cliente(barbearia_id, nome, telefone=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO clientes (barbearia_id, nome, telefone) VALUES (?, ?, ?)",
        (barbearia_id, nome, telefone),
    )
    conn.commit()
    conn.close()


# ---------- BARBEIROS ----------

def listar_barbeiros(barbearia_id):
    conn = get_connection()
    barbeiros = conn.execute(
        "SELECT * FROM barbeiros WHERE barbearia_id = ? ORDER BY nome",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return barbeiros


def buscar_barbeiro(barbearia_id, barbeiro_id):
    """O barbeiro, ou None se ele não existir ou for de outra barbearia."""
    conn = get_connection()
    barbeiro = conn.execute(
        "SELECT * FROM barbeiros WHERE id = ? AND barbearia_id = ?",
        (barbeiro_id, barbearia_id),
    ).fetchone()
    conn.close()
    return barbeiro


def criar_barbeiro(barbearia_id, nome, comissao_percentual=40.0):
    """Cadastra um barbeiro e retorna o id dele."""
    conn = get_connection()
    barbeiro_id = conn.execute(
        """
        INSERT INTO barbeiros (barbearia_id, nome, comissao_percentual)
        VALUES (?, ?, ?)
        """,
        (barbearia_id, nome, comissao_percentual),
    ).lastrowid
    conn.commit()
    conn.close()
    return barbeiro_id


# ---------- SERVIÇOS ----------

def listar_servicos(barbearia_id):
    conn = get_connection()
    servicos = conn.execute(
        "SELECT * FROM servicos WHERE barbearia_id = ? ORDER BY nome",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return servicos


def criar_servico(barbearia_id, nome, preco, duracao_minutos=30):
    """Cadastra um serviço e retorna o id dele."""
    conn = get_connection()
    servico_id = conn.execute(
        """
        INSERT INTO servicos (barbearia_id, nome, preco, duracao_minutos)
        VALUES (?, ?, ?, ?)
        """,
        (barbearia_id, nome, preco, duracao_minutos),
    ).lastrowid
    conn.commit()
    conn.close()
    return servico_id


# ---------- ATENDIMENTOS ----------

def listar_atendimentos(barbearia_id, barbeiro_id=None):
    """Lista os atendimentos da barbearia; com barbeiro_id, só os dele."""
    filtro = ""
    parametros = (barbearia_id,)
    if barbeiro_id is not None:
        filtro = "AND atendimentos.barbeiro_id = ?"
        parametros = (barbearia_id, barbeiro_id)

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
        WHERE atendimentos.barbearia_id = ? {filtro}
        ORDER BY atendimentos.data_hora DESC
        """,
        parametros,
    ).fetchall()
    conn.close()
    return atendimentos


def criar_atendimento(barbearia_id, cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento="dinheiro"):
    """
    Registra um atendimento. O cliente, o barbeiro e o serviço precisam ser
    da mesma barbearia; senão, levanta ValueError e nada é gravado.
    """
    conn = get_connection()
    try:
        for tabela, nome, registro_id in (
            ("clientes", "Cliente", cliente_id),
            ("barbeiros", "Barbeiro", barbeiro_id),
            ("servicos", "Serviço", servico_id),
        ):
            encontrado = conn.execute(
                f"SELECT 1 FROM {tabela} WHERE id = ? AND barbearia_id = ?",
                (registro_id, barbearia_id),
            ).fetchone()
            if encontrado is None:
                raise ValueError(
                    f"{nome} {registro_id} não existe nesta barbearia."
                )
        conn.execute(
            """
            INSERT INTO atendimentos
                (barbearia_id, cliente_id, barbeiro_id, servico_id,
                 valor_cobrado, forma_pagamento)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (barbearia_id, cliente_id, barbeiro_id, servico_id,
             valor_cobrado, forma_pagamento),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- USUÁRIOS ----------

def criar_usuario(barbearia_id, usuario, senha, papel, barbeiro_id=None):
    """
    Cadastra um usuário da barbearia com a senha guardada em hash. Usuário
    do papel 'barbeiro' precisa estar vinculado a um barbeiro da mesma
    barbearia.
    """
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido: {papel!r}. Use 'dono' ou 'barbeiro'.")
    _validar_senha(senha)
    if buscar_barbearia(barbearia_id) is None:
        raise ValueError(f"Barbearia {barbearia_id} não existe.")
    if papel == "barbeiro":
        if barbeiro_id is None:
            raise ValueError("Usuário barbeiro precisa de um barbeiro_id.")
        if buscar_barbeiro(barbearia_id, barbeiro_id) is None:
            raise ValueError(
                f"Barbeiro {barbeiro_id} não existe nesta barbearia."
            )
    else:
        barbeiro_id = None

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO usuarios (barbearia_id, usuario, senha_hash, papel, barbeiro_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (barbearia_id, usuario, generate_password_hash(senha), papel, barbeiro_id),
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


def trocar_senha(usuario_id, senha_atual, nova_senha):
    """
    Troca a senha do usuário. Dá ValueError se a senha atual estiver
    errada ou se a nova for curta demais ou igual à atual.
    """
    usuario = buscar_usuario(usuario_id)
    if usuario is None or not check_password_hash(usuario["senha_hash"], senha_atual):
        raise ValueError("A senha atual está errada.")
    _validar_senha(nova_senha)
    if nova_senha == senha_atual:
        raise ValueError("A nova senha precisa ser diferente da atual.")
    conn = get_connection()
    conn.execute(
        "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
        (generate_password_hash(nova_senha), usuario_id),
    )
    conn.commit()
    conn.close()


# ---------- LIMITE DE TENTATIVAS DE LOGIN ----------

def segundos_de_bloqueio(usuario):
    """Quantos segundos faltam para o login voltar a ser aceito (0 = liberado)."""
    conn = get_connection()
    linha = conn.execute(
        "SELECT bloqueado_ate FROM tentativas_login WHERE usuario = ?", (usuario,)
    ).fetchone()
    conn.close()
    if linha is None or linha["bloqueado_ate"] is None:
        return 0
    return max(0, linha["bloqueado_ate"] - _agora())


def registrar_falha_login(usuario):
    """
    Conta um erro de login. No MAXIMO_FALHAS_LOGIN-ésimo erro seguido o
    usuário fica bloqueado por TEMPO_BLOQUEIO_LOGIN e a contagem recomeça.
    """
    conn = get_connection()
    linha = conn.execute(
        "SELECT falhas FROM tentativas_login WHERE usuario = ?", (usuario,)
    ).fetchone()
    falhas = (linha["falhas"] if linha else 0) + 1
    bloqueado_ate = None
    if falhas >= MAXIMO_FALHAS_LOGIN:
        falhas = 0
        bloqueado_ate = _agora() + TEMPO_BLOQUEIO_LOGIN
    conn.execute(
        """
        INSERT INTO tentativas_login (usuario, falhas, bloqueado_ate)
        VALUES (?, ?, ?)
        ON CONFLICT (usuario) DO UPDATE
        SET falhas = excluded.falhas, bloqueado_ate = excluded.bloqueado_ate
        """,
        (usuario, falhas, bloqueado_ate),
    )
    conn.commit()
    conn.close()


def limpar_falhas_login(usuario):
    """Login certo: zera a contagem de erros do usuário."""
    conn = get_connection()
    conn.execute("DELETE FROM tentativas_login WHERE usuario = ?", (usuario,))
    conn.commit()
    conn.close()
