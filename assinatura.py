"""
assinatura.py

Assinatura do MeuBarber: a barbearia paga a mensalidade e pode usar o
sistema. A cobrança é feita pelo Asaas (Pix, boleto ou cartão, à escolha
de quem paga) e o dinheiro cai na conta PJ do dono do MeuBarber.

Situações de uma barbearia (coluna assinatura_status):
  teste     -> período grátis até teste_ate (TESTE_DIAS a partir do cadastro)
  ativa     -> pagamento em dia
  atrasada  -> fatura vencida; continua liberada por TOLERANCIA_DIAS
  cancelada -> assinatura encerrada no Asaas
  isenta    -> nunca é cobrada (contas criadas antes da cobrança existir)

A cobrança só vale com COBRANCA_ATIVA=1. Sem ela, todo mundo fica
liberado (é assim nos testes e enquanto a conta do Asaas não está pronta).

Configuração (variáveis de ambiente, no Render):
  COBRANCA_ATIVA=1          liga o bloqueio de quem não paga
  ASAAS_API_KEY             chave da API do Asaas (segredo, nunca no código)
  ASAAS_URL                 https://api.asaas.com/v3 (produção) ou
                            https://api-sandbox.asaas.com/v3 (testes)
  ASAAS_WEBHOOK_TOKEN       token que o Asaas manda no cabeçalho
                            asaas-access-token de cada aviso
  PLANO_VALOR               mensalidade em reais (padrão 49.90)
  TESTE_DIAS                dias grátis (padrão 7; 0 = paga no cadastro)
  ANTECIPAR_CARTAO=1        pede ao Asaas a antecipação de cada pagamento
                            de cartão assim que ele é confirmado (o dinheiro
                            cai em até 2 dias úteis em vez de 32 dias). A
                            antecipação automática do painel do Asaas é só
                            para PJ; por aqui funciona também para conta PF.
"""

import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date, timedelta

import agenda
import telefones
from database import get_connection

TOLERANCIA_DIAS = 3
STATUS_LIBERADOS = ("ativa", "isenta")
EVENTOS_PAGO = ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED")
EVENTOS_ATRASO = ("PAYMENT_OVERDUE",)
EVENTOS_FIM = ("SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED")


class ErroCobranca(Exception):
    """Falha ao falar com o Asaas; a mensagem pode ser mostrada ao dono."""


# ---------- CONFIGURAÇÃO ----------

def cobranca_ativa():
    return os.environ.get("COBRANCA_ATIVA") == "1"


def valor_plano():
    return round(float(os.environ.get("PLANO_VALOR", "49.90").replace(",", ".")), 2)


def dias_de_teste():
    """Dias grátis de conta nova. 0 = paga no cadastro para liberar o acesso."""
    return max(int(os.environ.get("TESTE_DIAS", "7")), 0)


def _hoje():
    return agenda.hoje()


def _ler_data(texto):
    return date.fromisoformat(str(texto)[:10]) if texto else None


# ---------- SITUAÇÃO DA BARBEARIA ----------

def situacao(barbearia):
    """
    {"liberado": bool, "status": str, "dias": int|None, "mensagem": str}
    dias = quantos dias faltam (teste ou tolerância), quando faz sentido.
    """
    status = barbearia["assinatura_status"] or "teste"
    if not cobranca_ativa():
        return {"liberado": True, "status": status, "dias": None, "mensagem": ""}
    hoje = _hoje()
    if status in STATUS_LIBERADOS:
        return {"liberado": True, "status": status, "dias": None, "mensagem": ""}
    if status == "teste":
        fim = _ler_data(barbearia["teste_ate"]) or hoje
        dias = (fim - hoje).days
        if dias >= 0:
            return {
                "liberado": True, "status": status, "dias": dias,
                "mensagem": (
                    "Último dia do teste grátis." if dias == 0
                    else f"Teste grátis: falta{'m' if dias > 1 else ''} {dias} dia{'s' if dias > 1 else ''}."
                ),
            }
        return {"liberado": False, "status": status, "dias": 0,
                "mensagem": "O teste grátis terminou. Assine para continuar usando."}
    if status == "pendente":
        return {"liberado": False, "status": status, "dias": 0,
                "mensagem": "Falta só o pagamento para liberar o MeuBarber."}
    if status == "atrasada":
        desde = _ler_data(barbearia["atrasada_desde"]) or hoje
        dias = (desde + timedelta(days=TOLERANCIA_DIAS) - hoje).days
        if dias >= 0:
            return {"liberado": True, "status": status, "dias": dias,
                    "mensagem": "A mensalidade está vencida. Pague para não perder o acesso."}
        return {"liberado": False, "status": status, "dias": 0,
                "mensagem": "A mensalidade está vencida e o acesso foi suspenso. Pague para liberar."}
    return {"liberado": False, "status": status, "dias": 0,
            "mensagem": "A assinatura foi cancelada. Assine de novo para voltar a usar."}


# ---------- CPF / CNPJ ----------

def _digito(numeros, pesos):
    soma = sum(int(n) * p for n, p in zip(numeros, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def normalizar_documento(texto):
    """CPF ou CNPJ só com números, conferindo os dígitos. ValueError se não servir."""
    numeros = re.sub(r"\D", "", texto or "")
    if len(numeros) == 11 and len(set(numeros)) > 1:
        d1 = _digito(numeros[:9], range(10, 1, -1))
        d2 = _digito(numeros[:9] + d1, range(11, 1, -1))
        if numeros[9:] == d1 + d2:
            return numeros
    if len(numeros) == 14 and len(set(numeros)) > 1:
        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        d1 = _digito(numeros[:12], pesos1)
        d2 = _digito(numeros[:12] + d1, [6] + pesos1)
        if numeros[12:] == d1 + d2:
            return numeros
    raise ValueError("CPF ou CNPJ inválido. Confira os números.")


# ---------- ASAAS ----------

def _chamar(metodo, caminho, dados=None, formulario=False):
    """
    Chama a API do Asaas. formulario=True manda os campos como
    multipart/form-data (o pedido de antecipação aceita anexar documentos
    e é documentado nesse formato); o resto vai em JSON.
    """
    chave = os.environ.get("ASAAS_API_KEY", "")
    if not chave:
        raise ErroCobranca("A cobrança ainda não foi configurada. Fale com o MeuBarber.")
    url = os.environ.get("ASAAS_URL", "https://api-sandbox.asaas.com/v3").rstrip("/") + caminho
    tipo = "application/json"
    corpo = json.dumps(dados).encode() if dados is not None else None
    if formulario and dados is not None:
        fronteira = "meubarber" + os.urandom(8).hex()
        tipo = f"multipart/form-data; boundary={fronteira}"
        corpo = b"".join(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode()
            for nome, valor in dados.items()
        ) + f"--{fronteira}--\r\n".encode()
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers={
        "access_token": chave,
        "Content-Type": tipo,
        "User-Agent": "MeuBarber",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=20) as resposta:
            return json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as erro:
        try:
            detalhes = json.loads(erro.read() or b"{}").get("errors") or []
            texto = "; ".join(d.get("description", "") for d in detalhes if d.get("description"))
        except ValueError:
            texto = ""
        raise ErroCobranca(texto or "O sistema de pagamento recusou o pedido. Tente de novo.") from None
    except (urllib.error.URLError, TimeoutError):
        raise ErroCobranca("Não foi possível falar com o sistema de pagamento. Tente de novo.") from None


def _gravar(barbearia_id, **campos):
    colunas = ", ".join(f"{c} = ?" for c in campos)
    conn = get_connection()
    conn.execute(f"UPDATE barbearias SET {colunas} WHERE id = ?", (*campos.values(), barbearia_id))
    conn.commit()
    conn.close()


def assinar(barbearia, documento, email):
    """
    Cria (ou reaproveita) o cliente e a assinatura mensal no Asaas e devolve
    o endereço da fatura, onde o dono escolhe Pix, boleto ou cartão. Se a
    barbearia ainda está no teste grátis, a primeira cobrança vence no fim
    do teste: assinar cedo não faz perder dias.
    """
    documento = normalizar_documento(documento)
    email = (email or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("E-mail inválido.")

    cliente_id = barbearia["asaas_cliente_id"]
    if not cliente_id:
        cliente = _chamar("POST", "/customers", {
            "name": barbearia["nome"],
            "cpfCnpj": documento,
            "email": email,
            "mobilePhone": telefones.so_digitos(barbearia["whatsapp"]) or None,
            "externalReference": str(barbearia["id"]),
        })
        cliente_id = cliente["id"]
        _gravar(barbearia["id"], asaas_cliente_id=cliente_id)

    if barbearia["asaas_assinatura_id"] and barbearia["assinatura_status"] in ("ativa", "atrasada", "teste", "pendente"):
        assinatura_id = barbearia["asaas_assinatura_id"]
    else:
        vencimento = _hoje()
        fim_teste = _ler_data(barbearia["teste_ate"])
        if barbearia["assinatura_status"] == "teste" and fim_teste and fim_teste > vencimento:
            vencimento = fim_teste
        criada = _chamar("POST", "/subscriptions", {
            "customer": cliente_id,
            "billingType": "UNDEFINED",  # quem paga escolhe Pix, boleto ou cartão
            "value": valor_plano(),
            "nextDueDate": vencimento.isoformat(),
            "cycle": "MONTHLY",
            "description": "Assinatura MeuBarber",
            "externalReference": str(barbearia["id"]),
        })
        assinatura_id = criada["id"]
        _gravar(barbearia["id"], asaas_assinatura_id=assinatura_id)

    cobrancas = _chamar("GET", f"/subscriptions/{assinatura_id}/payments").get("data") or []
    abertas = [c for c in cobrancas if c.get("status") in ("PENDING", "OVERDUE")]
    if not abertas:
        raise ErroCobranca("A fatura ainda está sendo gerada. Atualize a página em instantes.")
    link = sorted(abertas, key=lambda c: c.get("dueDate", ""))[0]["invoiceUrl"]
    _gravar(barbearia["id"], link_pagamento=link)
    return link


# ---------- AVISOS DO ASAAS (WEBHOOK) ----------

def token_valido(recebido):
    esperado = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")
    return bool(esperado) and hmac.compare_digest(esperado, recebido or "")


def _barbearia_do_evento(conn, evento):
    recurso = evento.get("payment") or evento.get("subscription") or {}
    assinatura_id = recurso.get("subscription") or (
        recurso.get("id") if "subscription" in evento else None
    )
    if assinatura_id:
        linha = conn.execute(
            "SELECT id FROM barbearias WHERE asaas_assinatura_id = ?", (assinatura_id,)
        ).fetchone()
        if linha:
            return linha["id"]
    referencia = recurso.get("externalReference")
    if referencia and str(referencia).isdigit():
        linha = conn.execute("SELECT id FROM barbearias WHERE id = ?", (int(referencia),)).fetchone()
        if linha:
            return linha["id"]
    return None


log = logging.getLogger(__name__)


def antecipar_cartao(evento):
    """
    Com ANTECIPAR_CARTAO=1, pede a antecipação de um pagamento de cartão
    recém-confirmado. Falha aqui nunca derruba o aviso: o pagamento já foi
    registrado e o dinheiro só demora mais a cair.
    """
    pagamento = evento.get("payment") or {}
    if (
        os.environ.get("ANTECIPAR_CARTAO") != "1"
        or evento.get("event") != "PAYMENT_CONFIRMED"
        or pagamento.get("billingType") != "CREDIT_CARD"
        or not pagamento.get("id")
    ):
        return "sem antecipação"
    try:
        _chamar("POST", "/anticipations", {"payment": pagamento["id"]}, formulario=True)
        return "antecipação pedida"
    except ErroCobranca as erro:
        log.warning("Antecipação do pagamento %s recusada: %s", pagamento["id"], erro)
        return "antecipação recusada"


def processar_evento(evento):
    """
    Aplica um aviso do Asaas. Cada evento é processado uma vez só (o Asaas
    pode reenviar). Devolve o que foi feito, para o registro.
    """
    evento_id = str(evento.get("id") or "")
    tipo = evento.get("event") or ""
    if not evento_id:
        return "ignorado: sem id"
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM eventos_pagamento WHERE id = ?", (evento_id,)).fetchone():
            return "repetido"
        conn.execute(
            "INSERT INTO eventos_pagamento (id, tipo) VALUES (?, ?)", (evento_id, tipo[:60])
        )
        barbearia_id = _barbearia_do_evento(conn, evento)
        if barbearia_id is None:
            conn.commit()
            return "ignorado: barbearia desconhecida"
        if tipo in EVENTOS_PAGO:
            conn.execute(
                "UPDATE barbearias SET assinatura_status = 'ativa', atrasada_desde = NULL, "
                "link_pagamento = NULL WHERE id = ? AND assinatura_status != 'isenta'",
                (barbearia_id,),
            )
            resultado = "ativa"
        elif tipo in EVENTOS_ATRASO:
            link = (evento.get("payment") or {}).get("invoiceUrl")
            # Quem nunca pagou (pendente) continua bloqueado: a tolerância
            # de atraso é só para quem já é assinante.
            conn.execute(
                "UPDATE barbearias SET link_pagamento = COALESCE(?, link_pagamento) "
                "WHERE id = ? AND assinatura_status = 'pendente'",
                (link, barbearia_id),
            )
            conn.execute(
                "UPDATE barbearias SET assinatura_status = 'atrasada', "
                "atrasada_desde = COALESCE(atrasada_desde, ?), link_pagamento = COALESCE(?, link_pagamento) "
                "WHERE id = ? AND assinatura_status NOT IN ('isenta', 'cancelada', 'pendente')",
                (_hoje().isoformat(), link, barbearia_id),
            )
            resultado = "atrasada"
        elif tipo in EVENTOS_FIM:
            conn.execute(
                "UPDATE barbearias SET assinatura_status = 'cancelada', asaas_assinatura_id = NULL "
                "WHERE id = ? AND assinatura_status != 'isenta'",
                (barbearia_id,),
            )
            resultado = "cancelada"
        else:
            resultado = "ignorado: " + tipo
        conn.commit()
        return resultado
    finally:
        conn.close()
