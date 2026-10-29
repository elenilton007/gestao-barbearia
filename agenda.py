"""
agenda.py

Agenda do MeuBarber: unidades da barbearia, horário de funcionamento,
bloqueios dos barbeiros, horários livres e agendamentos.

Como no resto do sistema, toda função recebe o barbearia_id primeiro e só
enxerga os dados daquela barbearia.

Fluxo de um agendamento (o mesmo que o cliente vai usar no link público):
  unidade -> serviço(s) -> barbeiro ou "sem preferência" -> dia -> horário

Um agendamento pode ter vários serviços (corte + barba + sobrancelha), como
uma comanda. A duração é a soma das durações. Ao concluir, cada serviço
vira um atendimento na gestão, com o preço combinado e a comissão do
barbeiro naquele momento.

Datas e horas são o horário local da barbearia (variável FUSO_HORARIO,
padrão America/Sao_Paulo), gravadas como texto 'AAAA-MM-DD HH:MM'.
"""

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import database
from database import get_connection

STATUS = ("marcado", "concluido", "faltou", "cancelado")
FORMAS_PAGAMENTO = ("dinheiro", "cartao", "pix")
DIAS_DA_SEMANA = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
DIAS_CURTOS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# De quantos em quantos minutos a agenda oferece horários (9:00, 9:15...).
PASSO_MINUTOS = 15
# Até quantos dias à frente dá para marcar.
JANELA_DIAS = 90
# Status que ocupam a agenda do barbeiro.
_OCUPAM = ("marcado", "concluido")

_FORMATO = "%Y-%m-%d %H:%M"


# ---------- DATAS E HORAS ----------

def fuso():
    return ZoneInfo(os.environ.get("FUSO_HORARIO", "America/Sao_Paulo"))


def agora():
    """Data e hora local da barbearia, sem fuso (para comparar com a agenda)."""
    return datetime.now(fuso()).replace(tzinfo=None, second=0, microsecond=0)


def hoje():
    return agora().date()


def _texto(momento):
    return momento.strftime(_FORMATO)


def ler_data(texto):
    """'AAAA-MM-DD' -> date. ValueError com mensagem para o usuário."""
    if isinstance(texto, date):
        return texto
    try:
        return datetime.strptime(str(texto).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Data inválida. Use o formato AAAA-MM-DD.") from None


def ler_hora(texto):
    """'HH:MM' -> 'HH:MM' normalizado. ValueError com mensagem para o usuário."""
    try:
        return datetime.strptime(str(texto).strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ValueError(f"Horário inválido: {texto!r}. Use HH:MM.") from None


def ler_momento(texto):
    """'AAAA-MM-DD HH:MM' ou 'AAAA-MM-DDTHH:MM' (campo datetime-local) -> datetime."""
    texto = str(texto or "").strip().replace("T", " ")[:16]
    try:
        return datetime.strptime(texto, _FORMATO)
    except ValueError:
        raise ValueError("Data e hora inválidas.") from None


def _ids(valores, mensagem):
    try:
        return [int(valor) for valor in valores]
    except (TypeError, ValueError):
        raise ValueError(mensagem) from None


def _id(valor, mensagem):
    return _ids([valor], mensagem)[0]


def _iniciar_transacao_exclusiva(conn, barbearia_id):
    """
    Impede que dois agendamentos sejam gravados ao mesmo tempo para a mesma
    barbearia (dois clientes pegando o último horário). No SQLite trava o
    banco para escrita; no PostgreSQL trava a linha da barbearia.
    """
    if database.usando_postgres():
        conn.execute(
            "SELECT id FROM barbearias WHERE id = ? FOR UPDATE", (barbearia_id,)
        )
    else:
        conn.execute("BEGIN IMMEDIATE")


# ---------- UNIDADES ----------

def listar_unidades(barbearia_id, somente_ativas=False):
    filtro = "AND ativo = 1" if somente_ativas else ""
    conn = get_connection()
    unidades = conn.execute(
        f"SELECT * FROM unidades WHERE barbearia_id = ? {filtro} ORDER BY id",
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return unidades


def buscar_unidade(barbearia_id, unidade_id):
    """A unidade, ou None se ela não existir ou for de outra barbearia."""
    conn = get_connection()
    unidade = conn.execute(
        "SELECT * FROM unidades WHERE id = ? AND barbearia_id = ?",
        (unidade_id, barbearia_id),
    ).fetchone()
    conn.close()
    return unidade


def _validar_unidade(nome, endereco):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("O nome da unidade não pode ficar em branco.")
    return nome, (endereco or "").strip() or None


def criar_unidade(barbearia_id, nome, endereco=None):
    """Cadastra uma unidade já com o horário padrão. Retorna o id."""
    nome, endereco = _validar_unidade(nome, endereco)
    conn = get_connection()
    try:
        unidade_id = database.criar_unidade_padrao(conn, barbearia_id, nome)
        conn.execute(
            "UPDATE unidades SET endereco = ? WHERE id = ?", (endereco, unidade_id)
        )
        conn.commit()
    finally:
        conn.close()
    return unidade_id


def editar_unidade(barbearia_id, unidade_id, nome, endereco=None):
    nome, endereco = _validar_unidade(nome, endereco)
    conn = get_connection()
    conn.execute(
        "UPDATE unidades SET nome = ?, endereco = ? WHERE id = ? AND barbearia_id = ?",
        (nome, endereco, unidade_id, barbearia_id),
    )
    conn.commit()
    conn.close()


def definir_unidade_ativa(barbearia_id, unidade_id, ativo):
    """
    Desativa (ou reativa) a unidade. Desativada, ela some da agenda, mas os
    agendamentos antigos continuam. A barbearia precisa de uma unidade ativa.
    """
    conn = get_connection()
    try:
        if not ativo:
            outras = conn.execute(
                """
                SELECT COUNT(*) FROM unidades
                WHERE barbearia_id = ? AND ativo = 1 AND id != ?
                """,
                (barbearia_id, unidade_id),
            ).fetchone()[0]
            if outras == 0:
                raise ValueError("A barbearia precisa ter pelo menos uma unidade ativa.")
        conn.execute(
            "UPDATE unidades SET ativo = ? WHERE id = ? AND barbearia_id = ?",
            (1 if ativo else 0, unidade_id, barbearia_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- HORÁRIO DE FUNCIONAMENTO ----------

def horarios_da_unidade(barbearia_id, unidade_id):
    """{dia_semana: [(abre, fecha), ...]} com os 7 dias (lista vazia = fechado)."""
    conn = get_connection()
    linhas = conn.execute(
        """
        SELECT dia_semana, abre, fecha FROM horarios_funcionamento
        WHERE barbearia_id = ? AND unidade_id = ?
        ORDER BY dia_semana, abre
        """,
        (barbearia_id, unidade_id),
    ).fetchall()
    conn.close()
    horarios = {dia: [] for dia in range(7)}
    for linha in linhas:
        horarios[linha["dia_semana"]].append((linha["abre"], linha["fecha"]))
    return horarios


def salvar_horarios(barbearia_id, unidade_id, horarios):
    """
    Troca o horário de funcionamento da unidade. horarios é
    {dia_semana: [(abre, fecha), ...]}; dia ausente ou lista vazia = fechado.
    As faixas de um dia não podem se sobrepor. Agendamentos já marcados não
    são mexidos.
    """
    if buscar_unidade(barbearia_id, unidade_id) is None:
        raise ValueError("Unidade não encontrada.")
    faixas = []
    for dia, lista in horarios.items():
        if dia not in range(7):
            raise ValueError("Dia da semana inválido.")
        do_dia = sorted((ler_hora(abre), ler_hora(fecha)) for abre, fecha in lista)
        for abre, fecha in do_dia:
            if abre >= fecha:
                raise ValueError(
                    f"{DIAS_DA_SEMANA[dia]}: o horário de abrir ({abre}) precisa "
                    f"ser antes do de fechar ({fecha})."
                )
        for (_, fecha_antes), (abre_depois, _) in zip(do_dia, do_dia[1:]):
            if abre_depois < fecha_antes:
                raise ValueError(f"{DIAS_DA_SEMANA[dia]}: as faixas de horário se sobrepõem.")
        faixas.extend((dia, abre, fecha) for abre, fecha in do_dia)

    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM horarios_funcionamento WHERE barbearia_id = ? AND unidade_id = ?",
            (barbearia_id, unidade_id),
        )
        for dia, abre, fecha in faixas:
            conn.execute(
                """
                INSERT INTO horarios_funcionamento
                    (barbearia_id, unidade_id, dia_semana, abre, fecha)
                VALUES (?, ?, ?, ?, ?)
                """,
                (barbearia_id, unidade_id, dia, abre, fecha),
            )
        conn.commit()
    finally:
        conn.close()


# ---------- BARBEIROS NA UNIDADE ----------

def definir_unidade_do_barbeiro(barbearia_id, barbeiro_id, unidade_id):
    """Liga o barbeiro a uma unidade; None (ou "") = atende em todas."""
    if unidade_id in (None, ""):
        unidade_id = None
    else:
        unidade_id = _id(unidade_id, "Unidade inválida.")
        if buscar_unidade(barbearia_id, unidade_id) is None:
            raise ValueError("Unidade não encontrada.")
    conn = get_connection()
    conn.execute(
        "UPDATE barbeiros SET unidade_id = ? WHERE id = ? AND barbearia_id = ?",
        (unidade_id, barbeiro_id, barbearia_id),
    )
    conn.commit()
    conn.close()


def barbeiros_da_unidade(barbearia_id, unidade_id):
    """Barbeiros ativos que atendem na unidade (os dela e os de todas)."""
    conn = get_connection()
    barbeiros = conn.execute(
        """
        SELECT * FROM barbeiros
        WHERE barbearia_id = ? AND ativo = 1
          AND (unidade_id IS NULL OR unidade_id = ?)
        ORDER BY nome
        """,
        (barbearia_id, unidade_id),
    ).fetchall()
    conn.close()
    return barbeiros


# ---------- BLOQUEIOS ----------

def criar_bloqueio(barbearia_id, barbeiro_id, inicio, fim, motivo=None):
    """Período em que o barbeiro não atende. Não mexe no que já está marcado."""
    barbeiro_id = _id(barbeiro_id, "Barbeiro inválido.")
    inicio, fim = ler_momento(inicio), ler_momento(fim)
    if fim <= inicio:
        raise ValueError("O fim do bloqueio precisa ser depois do início.")
    conn = get_connection()
    try:
        if conn.execute(
            "SELECT 1 FROM barbeiros WHERE id = ? AND barbearia_id = ?",
            (barbeiro_id, barbearia_id),
        ).fetchone() is None:
            raise ValueError("Barbeiro não encontrado.")
        bloqueio_id = conn.execute(
            """
            INSERT INTO bloqueios (barbearia_id, barbeiro_id, inicio, fim, motivo)
            VALUES (?, ?, ?, ?, ?) RETURNING id
            """,
            (barbearia_id, barbeiro_id, _texto(inicio), _texto(fim),
             (motivo or "").strip() or None),
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return bloqueio_id


def listar_bloqueios(barbearia_id, a_partir, barbeiro_id=None):
    """Bloqueios que terminam depois de a_partir (date ou datetime)."""
    if isinstance(a_partir, date) and not isinstance(a_partir, datetime):
        a_partir = datetime.combine(a_partir, datetime.min.time())
    filtro, parametros = "", [barbearia_id, _texto(a_partir)]
    if barbeiro_id is not None:
        filtro = "AND bloqueios.barbeiro_id = ?"
        parametros.append(barbeiro_id)
    conn = get_connection()
    bloqueios = conn.execute(
        f"""
        SELECT bloqueios.*, barbeiros.nome AS barbeiro
        FROM bloqueios JOIN barbeiros ON barbeiros.id = bloqueios.barbeiro_id
        WHERE bloqueios.barbearia_id = ? AND bloqueios.fim > ? {filtro}
        ORDER BY bloqueios.inicio
        """,
        parametros,
    ).fetchall()
    conn.close()
    return bloqueios


def buscar_bloqueio(barbearia_id, bloqueio_id):
    conn = get_connection()
    bloqueio = conn.execute(
        "SELECT * FROM bloqueios WHERE id = ? AND barbearia_id = ?",
        (bloqueio_id, barbearia_id),
    ).fetchone()
    conn.close()
    return bloqueio


def marcados_no_periodo(barbearia_id, barbeiro_id, inicio, fim):
    """Horários ainda marcados do barbeiro que batem com o período (para avisar)."""
    inicio, fim = ler_momento(inicio), ler_momento(fim)
    conn = get_connection()
    try:
        linhas = conn.execute(
            _SELECT_AGENDAMENTO + """
            WHERE agendamentos.barbearia_id = ? AND agendamentos.barbeiro_id = ?
              AND agendamentos.status = 'marcado'
              AND agendamentos.inicio < ? AND agendamentos.fim > ?
            ORDER BY agendamentos.inicio
            """,
            (barbearia_id, barbeiro_id, _texto(fim), _texto(inicio)),
        ).fetchall()
        return _com_servicos(conn, linhas)
    finally:
        conn.close()


def marcados_fora_do_horario(barbearia_id, unidade_id):
    """Horários marcados daqui para a frente que ficaram fora do funcionamento da unidade."""
    conn = get_connection()
    try:
        linhas = conn.execute(
            _SELECT_AGENDAMENTO + """
            WHERE agendamentos.barbearia_id = ? AND agendamentos.unidade_id = ?
              AND agendamentos.status = 'marcado' AND agendamentos.inicio >= ?
            ORDER BY agendamentos.inicio
            """,
            (barbearia_id, unidade_id, _texto(agora())),
        ).fetchall()
        fora = []
        for linha in linhas:
            inicio, fim = ler_momento(linha["inicio"]), ler_momento(linha["fim"])
            faixas = _faixas_do_dia(conn, barbearia_id, unidade_id, inicio.date())
            if not any(abre <= inicio and fim <= fecha for abre, fecha in faixas):
                fora.append(linha)
        return _com_servicos(conn, fora)
    finally:
        conn.close()


def proximos_do_cliente(barbearia_id, cliente_id):
    """Horários ainda marcados do cliente, de agora em diante."""
    conn = get_connection()
    try:
        linhas = conn.execute(
            _SELECT_AGENDAMENTO + """
            WHERE agendamentos.barbearia_id = ? AND agendamentos.cliente_id = ?
              AND agendamentos.status = 'marcado' AND agendamentos.fim > ?
            ORDER BY agendamentos.inicio
            """,
            (barbearia_id, cliente_id, _texto(agora())),
        ).fetchall()
        return _com_servicos(conn, linhas)
    finally:
        conn.close()


def marcado_hoje(barbearia_id, cliente_id, barbeiro_id):
    """O horário ainda marcado hoje do cliente com o barbeiro, ou None."""
    dia = hoje()
    conn = get_connection()
    try:
        linha = conn.execute(
            _SELECT_AGENDAMENTO + """
            WHERE agendamentos.barbearia_id = ? AND agendamentos.cliente_id = ?
              AND agendamentos.barbeiro_id = ? AND agendamentos.status = 'marcado'
              AND agendamentos.inicio >= ? AND agendamentos.inicio < ?
            ORDER BY agendamentos.inicio
            """,
            (barbearia_id, cliente_id, barbeiro_id,
             _texto(datetime.combine(dia, datetime.min.time())),
             _texto(datetime.combine(dia + timedelta(days=1), datetime.min.time()))),
        ).fetchone()
        return _com_servicos(conn, [linha])[0] if linha else None
    finally:
        conn.close()


def remover_bloqueio(barbearia_id, bloqueio_id):
    conn = get_connection()
    conn.execute(
        "DELETE FROM bloqueios WHERE id = ? AND barbearia_id = ?",
        (bloqueio_id, barbearia_id),
    )
    conn.commit()
    conn.close()


# ---------- HORÁRIOS LIVRES ----------

def _servicos_escolhidos(conn, barbearia_id, servico_ids):
    """Serviços ativos da barbearia, na ordem escolhida. ValueError se algum não servir."""
    servico_ids = _ids(servico_ids, "Serviço inválido.")
    if not servico_ids:
        raise ValueError("Escolha pelo menos um serviço.")
    if len(set(servico_ids)) != len(servico_ids):
        raise ValueError("O mesmo serviço foi escolhido duas vezes.")
    servicos = []
    for servico_id in servico_ids:
        servico = conn.execute(
            "SELECT * FROM servicos WHERE id = ? AND barbearia_id = ? AND ativo = 1",
            (servico_id, barbearia_id),
        ).fetchone()
        if servico is None:
            raise ValueError(f"Serviço {servico_id} não está disponível.")
        servicos.append(servico)
    return servicos


def _faixas_do_dia(conn, barbearia_id, unidade_id, dia):
    linhas = conn.execute(
        """
        SELECT abre, fecha FROM horarios_funcionamento
        WHERE barbearia_id = ? AND unidade_id = ? AND dia_semana = ?
        ORDER BY abre
        """,
        (barbearia_id, unidade_id, dia.weekday()),
    ).fetchall()
    base = datetime.combine(dia, datetime.min.time())
    return [
        (
            base + timedelta(hours=int(l["abre"][:2]), minutes=int(l["abre"][3:5])),
            base + timedelta(hours=int(l["fecha"][:2]), minutes=int(l["fecha"][3:5])),
        )
        for l in linhas
    ]


def _ocupacao(conn, barbearia_id, barbeiro_ids, dia, ignorar_agendamento=None):
    """{barbeiro_id: [(inicio, fim), ...]} com agendamentos e bloqueios que tocam o dia."""
    comeco = _texto(datetime.combine(dia, datetime.min.time()))
    fim_do_dia = _texto(datetime.combine(dia + timedelta(days=1), datetime.min.time()))
    ocupado = {barbeiro_id: [] for barbeiro_id in barbeiro_ids}
    if not barbeiro_ids:
        return ocupado
    marcas = ",".join("?" * len(barbeiro_ids))
    status = ",".join("?" * len(_OCUPAM))
    linhas = conn.execute(
        f"""
        SELECT barbeiro_id, inicio, fim FROM agendamentos
        WHERE barbearia_id = ? AND barbeiro_id IN ({marcas})
          AND status IN ({status}) AND inicio < ? AND fim > ? AND id != ?
        UNION ALL
        SELECT barbeiro_id, inicio, fim FROM bloqueios
        WHERE barbearia_id = ? AND barbeiro_id IN ({marcas})
          AND inicio < ? AND fim > ?
        """,
        (barbearia_id, *barbeiro_ids, *_OCUPAM, fim_do_dia, comeco,
         ignorar_agendamento or 0,
         barbearia_id, *barbeiro_ids, fim_do_dia, comeco),
    ).fetchall()
    for linha in linhas:
        ocupado[linha["barbeiro_id"]].append(
            (ler_momento(linha["inicio"]), ler_momento(linha["fim"]))
        )
    return ocupado


def _livre(periodos, inicio, fim):
    return all(fim <= ocupado_inicio or inicio >= ocupado_fim
               for ocupado_inicio, ocupado_fim in periodos)


def _calcular_livres(conn, barbearia_id, unidade_id, dia, duracao, barbeiros):
    """[(inicio, [barbeiro_ids livres])] do dia, sem horários já passados."""
    if dia < hoje() or dia > hoje() + timedelta(days=JANELA_DIAS):
        return []
    agora_local = agora()
    ids = [b["id"] for b in barbeiros]
    ocupado = _ocupacao(conn, barbearia_id, ids, dia)
    livres = []
    passo = timedelta(minutes=PASSO_MINUTOS)
    duracao = timedelta(minutes=duracao)
    for abre, fecha in _faixas_do_dia(conn, barbearia_id, unidade_id, dia):
        inicio = abre
        while inicio + duracao <= fecha:
            if inicio >= agora_local:
                quem = [i for i in ids if _livre(ocupado[i], inicio, inicio + duracao)]
                if quem:
                    livres.append((inicio, quem))
            inicio += passo
    return livres


def _barbeiros_candidatos(conn, barbearia_id, unidade_id, barbeiro_id):
    """Barbeiros que podem atender: o escolhido (se atende na unidade) ou todos da unidade."""
    parametros = [barbearia_id, unidade_id]
    filtro = ""
    if barbeiro_id is not None:
        filtro = "AND id = ?"
        parametros.append(barbeiro_id)
    return conn.execute(
        f"""
        SELECT * FROM barbeiros
        WHERE barbearia_id = ? AND ativo = 1
          AND (unidade_id IS NULL OR unidade_id = ?) {filtro}
        ORDER BY id
        """,
        parametros,
    ).fetchall()


def _unidade_ativa(conn, barbearia_id, unidade_id):
    unidade_id = _id(unidade_id, "Unidade inválida.")
    unidade = conn.execute(
        "SELECT * FROM unidades WHERE id = ? AND barbearia_id = ? AND ativo = 1",
        (unidade_id, barbearia_id),
    ).fetchone()
    if unidade is None:
        raise ValueError("Unidade não disponível.")
    return unidade_id


def horarios_livres(barbearia_id, unidade_id, dia, servico_ids, barbeiro_id=None):
    """
    Horários em que dá para marcar os serviços no dia, como lista de
    {"hora": "HH:MM", "barbeiros": [ids livres]}. Sem barbeiro_id ("sem
    preferência"), vale qualquer barbeiro da unidade.
    """
    dia = ler_data(dia)
    if barbeiro_id in ("", None):
        barbeiro_id = None
    else:
        barbeiro_id = _id(barbeiro_id, "Barbeiro inválido.")
    conn = get_connection()
    try:
        unidade_id = _unidade_ativa(conn, barbearia_id, unidade_id)
        servicos = _servicos_escolhidos(conn, barbearia_id, servico_ids)
        duracao = sum(s["duracao_minutos"] for s in servicos)
        barbeiros = _barbeiros_candidatos(conn, barbearia_id, unidade_id, barbeiro_id)
        livres = _calcular_livres(conn, barbearia_id, unidade_id, dia, duracao, barbeiros)
    finally:
        conn.close()
    return [{"hora": inicio.strftime("%H:%M"), "barbeiros": quem} for inicio, quem in livres]


# ---------- AGENDAMENTOS ----------

def _menos_ocupado(conn, barbearia_id, barbeiro_ids, dia):
    """
    "Sem preferência": entre os barbeiros livres, o que tem menos horários
    marcados no dia (divide o trabalho); empate fica com o de menor id.
    """
    comeco = _texto(datetime.combine(dia, datetime.min.time()))
    fim_do_dia = _texto(datetime.combine(dia + timedelta(days=1), datetime.min.time()))

    def carga(barbeiro_id):
        total = conn.execute(
            """
            SELECT COUNT(*) FROM agendamentos
            WHERE barbearia_id = ? AND barbeiro_id = ? AND status = 'marcado'
              AND inicio >= ? AND inicio < ?
            """,
            (barbearia_id, barbeiro_id, comeco, fim_do_dia),
        ).fetchone()[0]
        return (total, barbeiro_id)

    return min(barbeiro_ids, key=carga)


def criar_agendamento(barbearia_id, unidade_id, cliente_id, servico_ids, dia, hora,
                      barbeiro_id=None, observacao=None, origem="balcao"):
    """
    Marca um horário e retorna o id do agendamento. Sem barbeiro_id ("sem
    preferência"), escolhe o barbeiro livre menos ocupado no dia.

    Recusa (ValueError, nada gravado): unidade, cliente, barbeiro ou serviço
    de outra barbearia ou desativado; horário que já passou, além da
    JANELA_DIAS, fora do funcionamento da unidade, ou que bate com outro
    agendamento ou bloqueio do barbeiro.
    """
    dia = ler_data(dia)
    hora = ler_hora(hora)
    cliente_id = _id(cliente_id, "Cliente inválido.")
    if barbeiro_id in ("", None):
        barbeiro_id = None
    else:
        barbeiro_id = _id(barbeiro_id, "Barbeiro inválido.")
    inicio = datetime.combine(dia, datetime.strptime(hora, "%H:%M").time())
    if inicio < agora():
        raise ValueError("Esse horário já passou.")
    if dia > hoje() + timedelta(days=JANELA_DIAS):
        raise ValueError(f"Só dá para marcar até {JANELA_DIAS} dias à frente.")

    conn = get_connection()
    try:
        _iniciar_transacao_exclusiva(conn, barbearia_id)
        unidade_id = _unidade_ativa(conn, barbearia_id, unidade_id)
        if conn.execute(
            "SELECT 1 FROM clientes WHERE id = ? AND barbearia_id = ?",
            (cliente_id, barbearia_id),
        ).fetchone() is None:
            raise ValueError("Cliente não encontrado.")
        servicos = _servicos_escolhidos(conn, barbearia_id, servico_ids)
        duracao = sum(s["duracao_minutos"] for s in servicos)
        fim = inicio + timedelta(minutes=duracao)

        barbeiros = _barbeiros_candidatos(conn, barbearia_id, unidade_id, barbeiro_id)
        if barbeiro_id is not None and not barbeiros:
            raise ValueError("Esse barbeiro não atende nesta unidade.")
        if not any(abre <= inicio and fim <= fecha
                   for abre, fecha in _faixas_do_dia(conn, barbearia_id, unidade_id, dia)):
            raise ValueError("Fora do horário de funcionamento da unidade.")
        ocupado = _ocupacao(conn, barbearia_id, [b["id"] for b in barbeiros], dia)
        livres = [i for i, periodos in ocupado.items() if _livre(periodos, inicio, fim)]
        if not livres:
            if barbeiro_id is not None:
                raise ValueError("O barbeiro já tem compromisso nesse horário.")
            raise ValueError("Nenhum barbeiro livre nesse horário.")
        escolhido = livres[0] if barbeiro_id is not None else _menos_ocupado(
            conn, barbearia_id, livres, dia
        )

        agendamento_id = conn.execute(
            """
            INSERT INTO agendamentos
                (barbearia_id, unidade_id, cliente_id, barbeiro_id,
                 inicio, fim, origem, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            (barbearia_id, unidade_id, cliente_id, escolhido, _texto(inicio),
             _texto(fim), origem, (observacao or "").strip() or None),
        ).fetchone()[0]
        for servico in servicos:
            conn.execute(
                """
                INSERT INTO agendamento_servicos
                    (agendamento_id, servico_id, preco, duracao_minutos)
                VALUES (?, ?, ?, ?)
                """,
                (agendamento_id, servico["id"], servico["preco"], servico["duracao_minutos"]),
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return agendamento_id


def _com_servicos(conn, agendamentos):
    """Junta a cada agendamento a lista de serviços e o total, como dicionários."""
    resultado = []
    for agendamento in agendamentos:
        servicos = conn.execute(
            """
            SELECT servicos.nome, agendamento_servicos.preco,
                   agendamento_servicos.duracao_minutos
            FROM agendamento_servicos
            JOIN servicos ON servicos.id = agendamento_servicos.servico_id
            WHERE agendamento_servicos.agendamento_id = ?
            ORDER BY agendamento_servicos.id
            """,
            (agendamento["id"],),
        ).fetchall()
        item = {chave: agendamento[chave] for chave in agendamento.keys()}
        item["servicos"] = [s["nome"] for s in servicos]
        item["total"] = sum(s["preco"] for s in servicos)
        item["hora"] = agendamento["inicio"][11:16]
        item["hora_fim"] = agendamento["fim"][11:16]
        resultado.append(item)
    return resultado


_SELECT_AGENDAMENTO = """
    SELECT agendamentos.*, clientes.nome AS cliente, clientes.telefone,
           barbeiros.nome AS barbeiro, unidades.nome AS unidade
    FROM agendamentos
    JOIN clientes ON clientes.id = agendamentos.cliente_id
    JOIN barbeiros ON barbeiros.id = agendamentos.barbeiro_id
    JOIN unidades ON unidades.id = agendamentos.unidade_id
"""


def listar_agenda(barbearia_id, dia, unidade_id=None, barbeiro_id=None):
    """Agendamentos do dia (de todos os status), em ordem de horário."""
    dia = ler_data(dia)
    filtro, parametros = "", [
        barbearia_id,
        _texto(datetime.combine(dia, datetime.min.time())),
        _texto(datetime.combine(dia + timedelta(days=1), datetime.min.time())),
    ]
    if unidade_id is not None:
        filtro += " AND agendamentos.unidade_id = ?"
        parametros.append(unidade_id)
    if barbeiro_id is not None:
        filtro += " AND agendamentos.barbeiro_id = ?"
        parametros.append(barbeiro_id)
    conn = get_connection()
    try:
        linhas = conn.execute(
            _SELECT_AGENDAMENTO + f"""
            WHERE agendamentos.barbearia_id = ?
              AND agendamentos.inicio >= ? AND agendamentos.inicio < ? {filtro}
            ORDER BY agendamentos.inicio, barbeiros.nome
            """,
            parametros,
        ).fetchall()
        return _com_servicos(conn, linhas)
    finally:
        conn.close()


def contar_por_dia(barbearia_id, primeiro_dia, dias, unidade_id=None, barbeiro_id=None):
    """{date: quantos horários (sem os cancelados)} de primeiro_dia em diante."""
    primeiro_dia = ler_data(primeiro_dia)
    filtro, parametros = "", [
        barbearia_id,
        _texto(datetime.combine(primeiro_dia, datetime.min.time())),
        _texto(datetime.combine(primeiro_dia + timedelta(days=dias), datetime.min.time())),
    ]
    if unidade_id is not None:
        filtro += " AND unidade_id = ?"
        parametros.append(unidade_id)
    if barbeiro_id is not None:
        filtro += " AND barbeiro_id = ?"
        parametros.append(barbeiro_id)
    conn = get_connection()
    linhas = conn.execute(
        f"""
        SELECT substr(inicio, 1, 10) AS dia, COUNT(*) AS total FROM agendamentos
        WHERE barbearia_id = ? AND inicio >= ? AND inicio < ?
          AND status != 'cancelado' {filtro}
        GROUP BY substr(inicio, 1, 10)
        """,
        parametros,
    ).fetchall()
    conn.close()
    contagem = {primeiro_dia + timedelta(days=i): 0 for i in range(dias)}
    for linha in linhas:
        contagem[ler_data(linha["dia"])] = linha["total"]
    return contagem


def bloqueios_do_dia(barbearia_id, dia, barbeiro_id=None):
    """Bloqueios que tocam o dia, já cortados no começo e no fim do dia."""
    dia = ler_data(dia)
    comeco = datetime.combine(dia, datetime.min.time())
    fim_do_dia = comeco + timedelta(days=1)
    resultado = []
    for bloqueio in listar_bloqueios(barbearia_id, comeco, barbeiro_id):
        inicio, fim = ler_momento(bloqueio["inicio"]), ler_momento(bloqueio["fim"])
        if inicio >= fim_do_dia:
            continue
        resultado.append({
            "id": bloqueio["id"],
            "barbeiro_id": bloqueio["barbeiro_id"],
            "motivo": bloqueio["motivo"],
            "inicio": max(inicio, comeco),
            "fim": min(fim, fim_do_dia),
        })
    return resultado


def buscar_agendamento(barbearia_id, agendamento_id):
    """O agendamento (dicionário com serviços e total), ou None."""
    conn = get_connection()
    try:
        linha = conn.execute(
            _SELECT_AGENDAMENTO
            + " WHERE agendamentos.id = ? AND agendamentos.barbearia_id = ?",
            (agendamento_id, barbearia_id),
        ).fetchone()
        return _com_servicos(conn, [linha])[0] if linha else None
    finally:
        conn.close()


def _mudar_status(conn, barbearia_id, agendamento_id, novo_status):
    atualizado = conn.execute(
        """
        UPDATE agendamentos SET status = ?
        WHERE id = ? AND barbearia_id = ? AND status = 'marcado'
        """,
        (novo_status, agendamento_id, barbearia_id),
    ).rowcount
    if atualizado != 1:
        raise ValueError("Só dá para mudar um agendamento que ainda está marcado.")


def concluir_agendamento(barbearia_id, agendamento_id, forma_pagamento):
    """
    O cliente foi atendido: o agendamento vira um atendimento na gestão
    para cada serviço, com o preço combinado, a data e hora marcadas e a
    comissão atual do barbeiro.
    """
    if forma_pagamento not in FORMAS_PAGAMENTO:
        raise ValueError("Forma de pagamento inválida.")
    agendamento = buscar_agendamento(barbearia_id, agendamento_id)
    if agendamento is None:
        raise ValueError("Agendamento não encontrado.")
    if ler_momento(agendamento["inicio"]).date() > hoje():
        raise ValueError("Só dá para concluir no dia do atendimento.")
    conn = get_connection()
    try:
        _mudar_status(conn, barbearia_id, agendamento_id, "concluido")
        conn.execute(
            """
            INSERT INTO atendimentos
                (barbearia_id, cliente_id, barbeiro_id, servico_id, data_hora,
                 valor_cobrado, forma_pagamento, comissao_percentual, agendamento_id)
            SELECT agendamentos.barbearia_id, agendamentos.cliente_id,
                   agendamentos.barbeiro_id, agendamento_servicos.servico_id,
                   agendamentos.inicio || ':00', agendamento_servicos.preco, ?,
                   barbeiros.comissao_percentual, agendamentos.id
            FROM agendamentos
            JOIN agendamento_servicos ON agendamento_servicos.agendamento_id = agendamentos.id
            JOIN barbeiros ON barbeiros.id = agendamentos.barbeiro_id
            WHERE agendamentos.id = ? AND agendamentos.barbearia_id = ?
            ORDER BY agendamento_servicos.id
            """,
            (forma_pagamento, agendamento_id, barbearia_id),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def marcar_falta(barbearia_id, agendamento_id):
    """O cliente não veio. Só depois do horário marcado."""
    agendamento = buscar_agendamento(barbearia_id, agendamento_id)
    if agendamento is None:
        raise ValueError("Agendamento não encontrado.")
    if ler_momento(agendamento["inicio"]) > agora():
        raise ValueError("Só dá para marcar falta depois do horário.")
    conn = get_connection()
    try:
        _mudar_status(conn, barbearia_id, agendamento_id, "faltou")
        conn.commit()
    finally:
        conn.close()


def cancelar_agendamento(barbearia_id, agendamento_id):
    """Desmarca e libera o horário."""
    conn = get_connection()
    try:
        _mudar_status(conn, barbearia_id, agendamento_id, "cancelado")
        conn.commit()
    finally:
        conn.close()
