"""
models.py

Funções de acesso aos dados (barbearias, clientes, barbeiros, serviços,
atendimentos e usuários) do MeuBarber. A agenda fica em agenda.py.

Cada barbearia só vê os próprios dados: as funções recebem o barbearia_id
como primeiro argumento e filtram (ou gravam) sempre por ele.
"""

import math
import os
import time
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

import agenda
import telefones
from database import criar_unidade_padrao, gerar_slug, get_connection

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
    Cadastra uma barbearia nova junto com o usuário dono dela e a unidade
    "Principal" (com o horário padrão). Se o usuário não puder ser criado
    (nome repetido, por exemplo), a barbearia também não é. Retorna o id da
    barbearia.
    """
    nome = _validar_nome(nome, "O nome da barbearia")
    usuario = _validar_nome(usuario, "O nome de usuário")
    _validar_senha(senha)
    conn = get_connection()
    try:
        barbearia_id = conn.execute(
            "INSERT INTO barbearias (nome, slug) VALUES (?, ?) RETURNING id",
            (nome, gerar_slug(conn, nome)),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO usuarios (barbearia_id, usuario, senha_hash, papel)
            VALUES (?, ?, ?, 'dono')
            """,
            (barbearia_id, usuario, generate_password_hash(senha)),
        )
        criar_unidade_padrao(conn, barbearia_id)
        # Conta nova começa no teste grátis (veja assinatura.py).
        conn.execute(
            "UPDATE barbearias SET assinatura_status = 'teste', teste_ate = ? WHERE id = ?",
            ((agenda.hoje() + timedelta(days=int(os.environ.get("TESTE_DIAS", "14")))).isoformat(),
             barbearia_id),
        )
        conn.commit()
    finally:
        conn.close()
    return barbearia_id


# ---------- CLIENTES ----------
# O WhatsApp é guardado no formato padrão (telefones.py) e não se repete
# dentro da mesma barbearia: é por ele que o cliente é reconhecido.

def listar_clientes(barbearia_id, busca=None):
    """Clientes da barbearia por nome; com busca, só os que batem no nome ou no telefone."""
    conn = get_connection()
    clientes = conn.execute(
        "SELECT * FROM clientes WHERE barbearia_id = ? ORDER BY nome",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    busca = (busca or "").strip()
    if not busca:
        return clientes
    termo = busca.casefold()
    digitos = telefones.so_digitos(busca)
    return [
        c for c in clientes
        if termo in c["nome"].casefold()
        or (len(digitos) >= 3 and digitos in telefones.so_digitos(c["telefone"]))
    ]


def buscar_cliente(barbearia_id, cliente_id):
    """O cliente, ou None se ele não existir ou for de outra barbearia."""
    conn = get_connection()
    cliente = conn.execute(
        "SELECT * FROM clientes WHERE id = ? AND barbearia_id = ?",
        (cliente_id, barbearia_id),
    ).fetchone()
    conn.close()
    return cliente


def buscar_cliente_por_telefone(barbearia_id, telefone):
    """O cliente com esse WhatsApp (em qualquer formato), ou None."""
    try:
        telefone = telefones.normalizar(telefone)
    except ValueError:
        return None
    if telefone is None:
        return None
    conn = get_connection()
    cliente = conn.execute(
        "SELECT * FROM clientes WHERE barbearia_id = ? AND telefone = ? ORDER BY id",
        (barbearia_id, telefone),
    ).fetchone()
    conn.close()
    return cliente


def _validar_cliente(barbearia_id, nome, telefone, cliente_id=None):
    nome = _validar_nome(nome, "O nome do cliente")
    telefone = telefones.normalizar(telefone)
    if telefone is not None:
        outro = buscar_cliente_por_telefone(barbearia_id, telefone)
        if outro is not None and outro["id"] != cliente_id:
            raise ValueError(f"Esse WhatsApp já é do cliente {outro['nome']}.")
    return nome, telefone


def criar_cliente(barbearia_id, nome, telefone=None):
    """
    Cadastra um cliente e retorna o id dele. Nome em branco, WhatsApp
    inválido ou WhatsApp de outro cliente dão ValueError.
    """
    nome, telefone = _validar_cliente(barbearia_id, nome, telefone)
    conn = get_connection()
    cliente_id = conn.execute(
        "INSERT INTO clientes (barbearia_id, nome, telefone) VALUES (?, ?, ?) RETURNING id",
        (barbearia_id, nome, telefone),
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return cliente_id


def editar_cliente(barbearia_id, cliente_id, nome, telefone=None):
    nome, telefone = _validar_cliente(barbearia_id, nome, telefone, cliente_id)
    conn = get_connection()
    conn.execute(
        "UPDATE clientes SET nome = ?, telefone = ? WHERE id = ? AND barbearia_id = ?",
        (nome, telefone, cliente_id, barbearia_id),
    )
    conn.commit()
    conn.close()


def excluir_cliente(barbearia_id, cliente_id):
    """
    Apaga um cliente cadastrado por engano. Quem já tem atendimento ou
    horário marcado não é apagado (o histórico e o caixa dependem dele).
    """
    conn = get_connection()
    try:
        usado = conn.execute(
            """
            SELECT (SELECT COUNT(*) FROM atendimentos WHERE cliente_id = ? AND barbearia_id = ?)
                 + (SELECT COUNT(*) FROM agendamentos WHERE cliente_id = ? AND barbearia_id = ?)
            """,
            (cliente_id, barbearia_id, cliente_id, barbearia_id),
        ).fetchone()[0]
        if usado:
            raise ValueError(
                "Este cliente tem atendimentos ou horários na agenda e não pode ser "
                "excluído. Corrija o nome ou o WhatsApp, se precisar."
            )
        conn.execute(
            "DELETE FROM clientes WHERE id = ? AND barbearia_id = ?", (cliente_id, barbearia_id)
        )
        conn.commit()
    finally:
        conn.close()


def historico_do_cliente(barbearia_id, cliente_id):
    """Atendimentos do cliente, do mais recente para o mais antigo."""
    conn = get_connection()
    atendimentos = conn.execute(
        """
        SELECT atendimentos.data_hora, atendimentos.valor_cobrado,
               atendimentos.forma_pagamento, servicos.nome AS servico,
               barbeiros.nome AS barbeiro
        FROM atendimentos
        JOIN servicos ON servicos.id = atendimentos.servico_id
        JOIN barbeiros ON barbeiros.id = atendimentos.barbeiro_id
        WHERE atendimentos.barbearia_id = ? AND atendimentos.cliente_id = ?
        ORDER BY atendimentos.data_hora DESC, atendimentos.id DESC
        """,
        (barbearia_id, cliente_id),
    ).fetchall()
    conn.close()
    return atendimentos


# ---------- VALIDAÇÃO ----------

def _validar_nome(nome, campo="O nome"):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError(f"{campo} não pode ficar em branco.")
    return nome


def _numero(valor, mensagem, minimo, maximo=None, tipo=float):
    """Converte o texto do formulário (aceita vírgula) e confere os limites."""
    try:
        numero = tipo(str(valor).strip().replace(",", "."))
    except ValueError:
        raise ValueError(mensagem) from None
    if not math.isfinite(numero) or numero < minimo or (maximo is not None and numero > maximo):
        raise ValueError(mensagem)
    return numero


def _definir_ativo(tabela, barbearia_id, registro_id, ativo):
    conn = get_connection()
    conn.execute(
        f"UPDATE {tabela} SET ativo = ? WHERE id = ? AND barbearia_id = ?",
        (1 if ativo else 0, registro_id, barbearia_id),
    )
    conn.commit()
    conn.close()


# ---------- BARBEIROS ----------

def _validar_barbeiro(nome, comissao_percentual):
    return (
        _validar_nome(nome),
        _numero(
            comissao_percentual,
            "A comissão precisa ser um número entre 0 e 100.",
            0, 100,
        ),
    )


def listar_barbeiros(barbearia_id, somente_ativos=False):
    filtro = "AND ativo = 1" if somente_ativos else ""
    conn = get_connection()
    barbeiros = conn.execute(
        f"SELECT * FROM barbeiros WHERE barbearia_id = ? {filtro} ORDER BY nome",
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
    nome, comissao_percentual = _validar_barbeiro(nome, comissao_percentual)
    conn = get_connection()
    barbeiro_id = conn.execute(
        """
        INSERT INTO barbeiros (barbearia_id, nome, comissao_percentual)
        VALUES (?, ?, ?)
        RETURNING id
        """,
        (barbearia_id, nome, comissao_percentual),
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return barbeiro_id


def editar_barbeiro(barbearia_id, barbeiro_id, nome, comissao_percentual):
    nome, comissao_percentual = _validar_barbeiro(nome, comissao_percentual)
    conn = get_connection()
    conn.execute(
        """
        UPDATE barbeiros SET nome = ?, comissao_percentual = ?
        WHERE id = ? AND barbearia_id = ?
        """,
        (nome, comissao_percentual, barbeiro_id, barbearia_id),
    )
    conn.commit()
    conn.close()


def definir_barbeiro_ativo(barbearia_id, barbeiro_id, ativo):
    """
    Desativa (ou reativa) o barbeiro. Desativado, ele some do formulário de
    atendimento, mas continua nos atendimentos antigos e nos relatórios.
    """
    _definir_ativo("barbeiros", barbearia_id, barbeiro_id, ativo)


# ---------- SERVIÇOS ----------

def _validar_servico(nome, preco, duracao_minutos):
    return (
        _validar_nome(nome),
        round(_numero(preco, "O preço precisa ser um número maior ou igual a zero.", 0), 2),
        _numero(
            duracao_minutos,
            "A duração precisa ser um número inteiro de minutos, maior que zero.",
            1, tipo=int,
        ),
    )


def listar_servicos(barbearia_id, somente_ativos=False):
    filtro = "AND ativo = 1" if somente_ativos else ""
    conn = get_connection()
    servicos = conn.execute(
        f"SELECT * FROM servicos WHERE barbearia_id = ? {filtro} ORDER BY nome",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return servicos


def buscar_servico(barbearia_id, servico_id):
    """O serviço, ou None se ele não existir ou for de outra barbearia."""
    conn = get_connection()
    servico = conn.execute(
        "SELECT * FROM servicos WHERE id = ? AND barbearia_id = ?",
        (servico_id, barbearia_id),
    ).fetchone()
    conn.close()
    return servico


def criar_servico(barbearia_id, nome, preco, duracao_minutos=30):
    """Cadastra um serviço e retorna o id dele."""
    nome, preco, duracao_minutos = _validar_servico(nome, preco, duracao_minutos)
    conn = get_connection()
    servico_id = conn.execute(
        """
        INSERT INTO servicos (barbearia_id, nome, preco, duracao_minutos)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (barbearia_id, nome, preco, duracao_minutos),
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return servico_id


def editar_servico(barbearia_id, servico_id, nome, preco, duracao_minutos):
    nome, preco, duracao_minutos = _validar_servico(nome, preco, duracao_minutos)
    conn = get_connection()
    conn.execute(
        """
        UPDATE servicos SET nome = ?, preco = ?, duracao_minutos = ?
        WHERE id = ? AND barbearia_id = ?
        """,
        (nome, preco, duracao_minutos, servico_id, barbearia_id),
    )
    conn.commit()
    conn.close()


def definir_servico_ativo(barbearia_id, servico_id, ativo):
    """Como em definir_barbeiro_ativo: some do formulário, fica no histórico."""
    _definir_ativo("servicos", barbearia_id, servico_id, ativo)


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
            atendimentos.forma_pagamento,
            atendimentos.comissao_percentual
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
    da mesma barbearia, e o barbeiro e o serviço precisam estar ativos;
    senão, levanta ValueError e nada é gravado.

    O percentual de comissão do barbeiro é copiado para o atendimento, para
    que mudar a comissão depois não altere os atendimentos já registrados.
    """
    # Os valores chegam do formulário como texto. O SQLite guardaria um
    # texto inválido como está; o PostgreSQL daria erro. Confere antes.
    try:
        cliente_id, barbeiro_id, servico_id = (
            int(registro_id) for registro_id in (cliente_id, barbeiro_id, servico_id)
        )
    except (TypeError, ValueError):
        raise ValueError("Cliente, barbeiro e serviço inválidos.") from None
    valor_cobrado = round(_numero(
        valor_cobrado, "O valor cobrado precisa ser um número maior ou igual a zero.", 0
    ), 2)

    conn = get_connection()
    try:
        for tabela, nome, registro_id in (
            ("clientes", "Cliente", cliente_id),
            ("barbeiros", "Barbeiro", barbeiro_id),
            ("servicos", "Serviço", servico_id),
        ):
            encontrado = conn.execute(
                f"SELECT * FROM {tabela} WHERE id = ? AND barbearia_id = ?",
                (registro_id, barbearia_id),
            ).fetchone()
            if encontrado is None:
                raise ValueError(
                    f"{nome} {registro_id} não existe nesta barbearia."
                )
            if "ativo" in encontrado.keys() and not encontrado["ativo"]:
                raise ValueError(f"{nome} {registro_id} está desativado.")
        # VALUES (e não INSERT ... SELECT ?, ...): no PostgreSQL, parâmetros
        # na lista do SELECT viram texto e não entram em colunas numéricas.
        # Data e hora local da barbearia, como na agenda (o padrão do banco
        # seria o horário UTC).
        conn.execute(
            """
            INSERT INTO atendimentos
                (barbearia_id, cliente_id, barbeiro_id, servico_id, data_hora,
                 valor_cobrado, forma_pagamento, comissao_percentual)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    (SELECT comissao_percentual FROM barbeiros WHERE id = ?))
            """,
            (barbearia_id, cliente_id, barbeiro_id, servico_id,
             agenda.agora().strftime("%Y-%m-%d %H:%M:%S"),
             valor_cobrado, forma_pagamento, barbeiro_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- USUÁRIOS ----------

def _validar_papel(barbearia_id, papel, barbeiro_id):
    """Confere o papel e devolve o barbeiro_id a gravar (None para o dono)."""
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido: {papel!r}. Use 'dono' ou 'barbeiro'.")
    if papel == "dono":
        return None
    if barbeiro_id in (None, ""):
        raise ValueError("Usuário barbeiro precisa de um barbeiro_id.")
    try:
        barbeiro_id = int(barbeiro_id)
    except (TypeError, ValueError):
        raise ValueError(f"Barbeiro {barbeiro_id} não existe nesta barbearia.") from None
    if buscar_barbeiro(barbearia_id, barbeiro_id) is None:
        raise ValueError(f"Barbeiro {barbeiro_id} não existe nesta barbearia.")
    return barbeiro_id


def criar_usuario(barbearia_id, usuario, senha, papel, barbeiro_id=None):
    """
    Cadastra um usuário da barbearia com a senha guardada em hash. Usuário
    do papel 'barbeiro' precisa estar vinculado a um barbeiro da mesma
    barbearia. Nome de usuário repetido levanta database.IntegrityError.
    """
    usuario = _validar_nome(usuario, "O nome de usuário")
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido: {papel!r}. Use 'dono' ou 'barbeiro'.")
    _validar_senha(senha)
    if buscar_barbearia(barbearia_id) is None:
        raise ValueError(f"Barbearia {barbearia_id} não existe.")
    barbeiro_id = _validar_papel(barbearia_id, papel, barbeiro_id)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO usuarios (barbearia_id, usuario, senha_hash, papel, barbeiro_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (barbearia_id, usuario, generate_password_hash(senha), papel, barbeiro_id),
        )
        conn.commit()
    finally:
        conn.close()


def listar_usuarios(barbearia_id):
    """Usuários da barbearia, com o nome do barbeiro vinculado (se houver)."""
    conn = get_connection()
    usuarios = conn.execute(
        """
        SELECT usuarios.*, barbeiros.nome AS barbeiro
        FROM usuarios
        LEFT JOIN barbeiros ON barbeiros.id = usuarios.barbeiro_id
        WHERE usuarios.barbearia_id = ?
        ORDER BY usuarios.usuario
        """,
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return usuarios


def buscar_usuario(usuario_id):
    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    conn.close()
    return usuario


def buscar_usuario_da_barbearia(barbearia_id, usuario_id):
    """O usuário, ou None se ele não existir ou for de outra barbearia."""
    usuario = buscar_usuario(usuario_id)
    if usuario is None or usuario["barbearia_id"] != barbearia_id:
        return None
    return usuario


def _confere_outro_dono_ativo(conn, barbearia_id, usuario_id):
    """A barbearia não pode ficar sem nenhum dono ativo."""
    outros = conn.execute(
        """
        SELECT COUNT(*) FROM usuarios
        WHERE barbearia_id = ? AND papel = 'dono' AND ativo = 1 AND id != ?
        """,
        (barbearia_id, usuario_id),
    ).fetchone()[0]
    if outros == 0:
        raise ValueError("A barbearia precisa ter pelo menos um dono ativo.")


def editar_usuario(barbearia_id, usuario_id, papel, barbeiro_id=None, nova_senha=""):
    """
    Muda o papel (e o barbeiro vinculado) do usuário; com nova_senha, troca
    também a senha. Tirar o papel de dono do último dono ativo é recusado.
    """
    barbeiro_id = _validar_papel(barbearia_id, papel, barbeiro_id)
    if nova_senha:
        _validar_senha(nova_senha)
    conn = get_connection()
    try:
        if papel != "dono":
            _confere_outro_dono_ativo(conn, barbearia_id, usuario_id)
        conn.execute(
            """
            UPDATE usuarios SET papel = ?, barbeiro_id = ?
            WHERE id = ? AND barbearia_id = ?
            """,
            (papel, barbeiro_id, usuario_id, barbearia_id),
        )
        if nova_senha:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ? WHERE id = ? AND barbearia_id = ?",
                (generate_password_hash(nova_senha), usuario_id, barbearia_id),
            )
        conn.commit()
    finally:
        conn.close()


def definir_usuario_ativo(barbearia_id, usuario_id, ativo):
    """
    Desativa (ou reativa) o usuário. Desativado, ele não consegue entrar.
    Desativar o último dono ativo é recusado.
    """
    if not ativo:
        conn = get_connection()
        try:
            usuario = conn.execute(
                "SELECT papel FROM usuarios WHERE id = ? AND barbearia_id = ?",
                (usuario_id, barbearia_id),
            ).fetchone()
            if usuario is not None and usuario["papel"] == "dono":
                _confere_outro_dono_ativo(conn, barbearia_id, usuario_id)
        finally:
            conn.close()
    _definir_ativo("usuarios", barbearia_id, usuario_id, ativo)


def buscar_usuario_por_nome(usuario):
    conn = get_connection()
    encontrado = conn.execute(
        "SELECT * FROM usuarios WHERE usuario = ?", (usuario,)
    ).fetchone()
    conn.close()
    return encontrado


def autenticar_existe(usuario):
    """True se já existe um usuário com esse nome (em qualquer barbearia)."""
    return buscar_usuario_por_nome(usuario) is not None


def autenticar(usuario, senha):
    """Retorna o usuário se a senha estiver correta e ele estiver ativo; senão, None."""
    conn = get_connection()
    encontrado = conn.execute(
        "SELECT * FROM usuarios WHERE usuario = ?", (usuario,)
    ).fetchone()
    conn.close()
    if (
        encontrado
        and encontrado["ativo"]
        and check_password_hash(encontrado["senha_hash"], senha)
    ):
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
