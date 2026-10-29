"""
publico.py

Link público de agendamento do MeuBarber: a página /b/<endereço> em que o
cliente da barbearia marca sozinho, sem login.

Regras (o dono muda em "Link de agendamento"):
  - online_ativo: liga e desliga o agendamento pelo link;
  - cancelamento_horas: até quantas horas antes o cliente pode cancelar;
  - limite_por_cliente: quantos horários futuros um mesmo WhatsApp pode ter.

O cliente é reconhecido pelo WhatsApp: se já existe na barbearia, o
horário vai para o cadastro dele (e o nome cadastrado não muda). Cada
agendamento feito pelo link ganha um código secreto (token) que forma o
endereço onde o cliente vê e cancela o horário.
"""

import re
import secrets
import time
from datetime import timedelta

import agenda
import models
import telefones
from database import gerar_slug, get_connection

SLUG_VALIDO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")
HORAS_CANCELAMENTO = (0, 1, 2, 3, 6, 12, 24, 48)
LIMITES_POR_CLIENTE = (1, 2, 3, 5, 10)
DIAS_NA_FAIXA = 14  # dias mostrados na faixa de escolha do dia


# ---------- BARBEARIA PELO ENDEREÇO ----------

def buscar_por_slug(slug):
    conn = get_connection()
    barbearia = conn.execute(
        "SELECT * FROM barbearias WHERE slug = ?", ((slug or "").lower(),)
    ).fetchone()
    conn.close()
    return barbearia


def salvar_configuracao(barbearia_id, slug, whatsapp, online_ativo,
                        cancelamento_horas, limite_por_cliente, nome=None):
    """
    Grava o nome da barbearia (se vier), o endereço e as regras do link.
    ValueError com mensagem se algo não servir.
    """
    if nome is not None:
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome da barbearia não pode ficar em branco.")
        if len(nome) > 80:
            raise ValueError("O nome da barbearia pode ter até 80 letras.")
    slug = (slug or "").strip().lower()
    if not SLUG_VALIDO.match(slug) or "--" in slug:
        raise ValueError(
            "Endereço inválido. Use de 3 a 40 letras minúsculas, números e hífen, "
            "sem acento e sem espaço (exemplo: barbearia-centro)."
        )
    try:
        cancelamento_horas = int(cancelamento_horas)
        limite_por_cliente = int(limite_por_cliente)
    except (TypeError, ValueError):
        raise ValueError("Regras do agendamento inválidas.") from None
    if cancelamento_horas not in HORAS_CANCELAMENTO or limite_por_cliente not in LIMITES_POR_CLIENTE:
        raise ValueError("Regras do agendamento inválidas.")
    whatsapp = telefones.normalizar(whatsapp)

    conn = get_connection()
    try:
        if conn.execute(
            "SELECT 1 FROM barbearias WHERE slug = ? AND id != ?", (slug, barbearia_id)
        ).fetchone():
            raise ValueError(
                f"O endereço {slug!r} já é de outra barbearia. "
                f"Sugestão: {gerar_slug(conn, slug, barbearia_id)}"
            )
        conn.execute(
            """
            UPDATE barbearias SET slug = ?, whatsapp = ?, online_ativo = ?,
                   cancelamento_horas = ?, limite_por_cliente = ?
            WHERE id = ?
            """,
            (slug, whatsapp, 1 if online_ativo else 0, cancelamento_horas,
             limite_por_cliente, barbearia_id),
        )
        if nome is not None:
            conn.execute("UPDATE barbearias SET nome = ? WHERE id = ?", (nome, barbearia_id))
        conn.commit()
    finally:
        conn.close()


# ---------- LIMITE DE PEDIDOS ----------

def _agora_segundos():
    return time.time()


def pode_tentar(chave, maximo, janela_segundos):
    """
    Conta um pedido para a chave e diz se ainda está dentro do limite
    (maximo pedidos a cada janela_segundos). Protege as páginas públicas
    de robôs que marcariam a agenda inteira.
    """
    agora = _agora_segundos()
    conn = get_connection()
    try:
        linha = conn.execute(
            "SELECT contagem, janela_inicio FROM limites_publicos WHERE chave = ?", (chave,)
        ).fetchone()
        if linha is None or agora - linha["janela_inicio"] >= janela_segundos:
            contagem, inicio = 1, agora
        else:
            contagem, inicio = linha["contagem"] + 1, linha["janela_inicio"]
        conn.execute(
            """
            INSERT INTO limites_publicos (chave, contagem, janela_inicio) VALUES (?, ?, ?)
            ON CONFLICT (chave) DO UPDATE
            SET contagem = excluded.contagem, janela_inicio = excluded.janela_inicio
            """,
            (chave, contagem, inicio),
        )
        conn.commit()
    finally:
        conn.close()
    return contagem <= maximo


# ---------- AGENDAR E CANCELAR ----------

def _horarios_futuros_do_cliente(barbearia_id, cliente_id):
    conn = get_connection()
    total = conn.execute(
        """
        SELECT COUNT(*) FROM agendamentos
        WHERE barbearia_id = ? AND cliente_id = ? AND status = 'marcado' AND inicio >= ?
        """,
        (barbearia_id, cliente_id, agenda.agora().strftime("%Y-%m-%d %H:%M")),
    ).fetchone()[0]
    conn.close()
    return total


def agendar(barbearia, unidade_id, servico_ids, dia, hora, barbeiro_id, nome, whatsapp):
    """
    Marca um horário pelo link público e devolve o token do agendamento.
    ValueError (com mensagem para o cliente) se algo não servir; nada é gravado.
    """
    if not barbearia["online_ativo"]:
        raise ValueError("O agendamento pelo link está pausado nesta barbearia.")
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o seu nome.")
    telefone = telefones.normalizar(whatsapp)
    if telefone is None:
        raise ValueError("Informe o seu WhatsApp, com DDD.")

    barbearia_id = barbearia["id"]
    # Confere o horário antes de cadastrar alguém, para não deixar cliente sobrando.
    livres = agenda.horarios_livres(barbearia_id, unidade_id, dia, servico_ids, barbeiro_id)
    if hora not in [h["hora"] for h in livres]:
        raise ValueError("Esse horário acabou de ser ocupado. Escolha outro.")

    cliente = models.buscar_cliente_por_telefone(barbearia_id, telefone)
    if cliente is not None:
        limite = barbearia["limite_por_cliente"]
        if _horarios_futuros_do_cliente(barbearia_id, cliente["id"]) >= limite:
            raise ValueError(
                f"Este WhatsApp já tem {limite} horário{'s' if limite > 1 else ''} marcado"
                f"{'s' if limite > 1 else ''}. Cancele um deles ou fale com a barbearia."
            )
        cliente_id = cliente["id"]
    else:
        cliente_id = models.criar_cliente(barbearia_id, nome, telefone)

    token = secrets.token_urlsafe(18)
    agenda.criar_agendamento(
        barbearia_id, unidade_id, cliente_id, servico_ids, dia, hora,
        barbeiro_id or None, origem="online", token=token,
    )
    return token


def buscar_por_token(barbearia_id, token):
    """O agendamento do link do cliente (dicionário com serviços), ou None."""
    if not token or len(token) > 64:
        return None
    conn = get_connection()
    linha = conn.execute(
        "SELECT id FROM agendamentos WHERE barbearia_id = ? AND token = ?",
        (barbearia_id, token),
    ).fetchone()
    conn.close()
    return agenda.buscar_agendamento(barbearia_id, linha["id"]) if linha else None


def prazo_para_cancelar(barbearia, agendamento):
    """Até quando (datetime) o cliente pode cancelar pelo link."""
    return agenda.ler_momento(agendamento["inicio"]) - timedelta(
        hours=barbearia["cancelamento_horas"]
    )


def pode_cancelar(barbearia, agendamento):
    return (
        agendamento["status"] == "marcado"
        and agenda.agora() <= prazo_para_cancelar(barbearia, agendamento)
    )


def cancelar(barbearia, token):
    agendamento = buscar_por_token(barbearia["id"], token)
    if agendamento is None:
        raise ValueError("Horário não encontrado.")
    if agendamento["status"] != "marcado":
        raise ValueError("Este horário não está mais marcado.")
    if not pode_cancelar(barbearia, agendamento):
        horas = barbearia["cancelamento_horas"]
        raise ValueError(
            f"O cancelamento pelo link vai até {horas} hora{'s' if horas != 1 else ''} antes. "
            "Fale com a barbearia."
        )
    agenda.cancelar_agendamento(barbearia["id"], agendamento["id"])
    return agendamento


# ---------- CALENDÁRIO ----------

def arquivo_calendario(barbearia, agendamento, endereco):
    """Arquivo .ics para o cliente salvar o horário na agenda do celular."""
    inicio = agenda.ler_momento(agendamento["inicio"])
    fim = agenda.ler_momento(agendamento["fim"])

    def texto(valor):
        return (str(valor).replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))

    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MeuBarber//Agendamento//PT-BR",
        "BEGIN:VEVENT",
        f"UID:{agendamento['token']}@meubarber",
        f"DTSTAMP:{agenda.agora().strftime('%Y%m%dT%H%M%S')}",
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{fim.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{texto(', '.join(agendamento['servicos']) + ' na ' + barbearia['nome'])}",
        f"DESCRIPTION:{texto('Com ' + agendamento['barbeiro'] + '. Ver ou cancelar: ' + endereco)}",
        f"LOCATION:{texto(agendamento['unidade'])}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(linhas) + "\r\n"
