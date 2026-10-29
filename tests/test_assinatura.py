"""
test_assinatura.py

Assinatura do MeuBarber pelo Asaas: teste grátis, bloqueio de quem não
paga (só com COBRANCA_ATIVA=1), geração da fatura, avisos de pagamento
(webhook) com token, reenvio do mesmo aviso e contas isentas.

O Asaas é simulado: nenhum teste fala com a internet.
"""

from datetime import date

import pytest

import agenda
import assinatura
import database
import models
from conftest import BARBEARIA, logar

CPF_VALIDO = "529.982.247-25"
CNPJ_VALIDO = "11.222.333/0001-81"
TOKEN = "t" * 40


@pytest.fixture
def cobranca(monkeypatch):
    """Cobrança ligada, relógio em 01/03/2030 e o Asaas simulado."""
    monkeypatch.setenv("COBRANCA_ATIVA", "1")
    monkeypatch.setenv("ASAAS_API_KEY", "chave-de-teste")
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("PLANO_VALOR", "59.90")
    relogio = {"hoje": date(2030, 3, 1)}
    monkeypatch.setattr(assinatura, "_hoje", lambda: relogio["hoje"])
    monkeypatch.setattr(agenda, "hoje", lambda: relogio["hoje"])
    chamadas = []

    def falso_asaas(metodo, caminho, dados=None):
        chamadas.append((metodo, caminho, dados))
        if caminho == "/customers":
            return {"id": "cus_1"}
        if caminho == "/subscriptions":
            return {"id": "sub_1"}
        if caminho == "/subscriptions/sub_1/payments":
            return {"data": [{"id": "pay_1", "status": "PENDING", "dueDate": dados or "2030-03-15",
                              "invoiceUrl": "https://www.asaas.com/i/pay_1"}]}
        raise AssertionError(caminho)

    monkeypatch.setattr(assinatura, "_chamar", falso_asaas)
    return type("Cobranca", (), {"relogio": relogio, "chamadas": chamadas})


@pytest.fixture
def conta_nova(cobranca, client_anonimo):
    """Barbearia criada pelo cadastro (começa no teste grátis de 14 dias), já logada."""
    client_anonimo.post("/cadastro", data={
        "nome_barbearia": "Navalha do Bairro", "whatsapp": "71988881234", "usuario": "joao.silva",
        "senha": "senha-forte-1", "confirmacao": "senha-forte-1", "aceite": "1",
    })
    dono = models.buscar_usuario_por_nome("joao.silva")
    return type("Conta", (), {"client": client_anonimo, "id": dono["barbearia_id"]})


def _barbearia(barbearia_id):
    return models.buscar_barbearia(barbearia_id)


def _aviso(client, evento, token=TOKEN):
    return client.post("/webhooks/asaas", json=evento, headers={"asaas-access-token": token})


# ---------- DOCUMENTO ----------

@pytest.mark.parametrize("texto, esperado", [
    (CPF_VALIDO, "52998224725"), (CNPJ_VALIDO, "11222333000181"),
])
def test_documento_valido(texto, esperado):
    assert assinatura.normalizar_documento(texto) == esperado


@pytest.mark.parametrize("texto", ["111.111.111-11", "529.982.247-24", "123", "11.222.333/0001-82", ""])
def test_documento_invalido(texto):
    with pytest.raises(ValueError, match="CPF ou CNPJ inválido"):
        assinatura.normalizar_documento(texto)


# ---------- TESTE GRÁTIS E BLOQUEIO ----------

def test_conta_nova_comeca_no_teste_de_14_dias(conta_nova):
    barbearia = _barbearia(conta_nova.id)
    assert barbearia["assinatura_status"] == "teste"
    assert barbearia["teste_ate"] == "2030-03-15"
    html = conta_nova.client.get("/agenda").get_data(as_text=True)
    assert "Teste grátis: faltam 14 dias" in html


def test_contas_antigas_ficam_isentas():
    assert _barbearia(BARBEARIA)["assinatura_status"] == "isenta"


def test_fim_do_teste_bloqueia_e_manda_para_a_assinatura(conta_nova, cobranca):
    cobranca.relogio["hoje"] = date(2030, 3, 16)
    resposta = conta_nova.client.get("/agenda")
    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/assinatura")
    html = conta_nova.client.get("/assinatura").get_data(as_text=True)
    assert "O teste grátis terminou" in html and "R$ 59,90" in html


def test_bloqueada_ainda_pode_sair_e_trocar_senha(conta_nova, cobranca):
    cobranca.relogio["hoje"] = date(2030, 3, 16)
    assert conta_nova.client.get("/conta/senha").status_code == 200
    assert conta_nova.client.post("/logout").status_code == 302


def test_link_publico_fica_pausado_quando_bloqueada(conta_nova, cobranca, client_anonimo):
    cobranca.relogio["hoje"] = date(2030, 3, 16)
    conta_nova.client.post("/logout")
    assert "pausado" in client_anonimo.get("/b/navalha-do-bairro").get_data(as_text=True)


def test_sem_cobranca_ativa_ninguem_e_bloqueado(conta_nova, cobranca, monkeypatch):
    monkeypatch.setenv("COBRANCA_ATIVA", "0")
    cobranca.relogio["hoje"] = date(2031, 1, 1)
    assert conta_nova.client.get("/agenda").status_code == 200


def test_conta_isenta_nunca_e_bloqueada(cobranca, client):
    cobranca.relogio["hoje"] = date(2040, 1, 1)
    assert client.get("/agenda").status_code == 200


# ---------- GERAR A FATURA ----------

def test_assinar_cria_cliente_assinatura_e_mostra_a_fatura(conta_nova, cobranca):
    resposta = conta_nova.client.post("/assinatura/assinar", data={
        "documento": CNPJ_VALIDO, "email": "dono@navalha.com.br",
    }, follow_redirects=True)
    html = resposta.get_data(as_text=True)
    assert "Fatura gerada" in html and "https://www.asaas.com/i/pay_1" in html

    cliente = [c for c in cobranca.chamadas if c[1] == "/customers"][0][2]
    assert cliente["cpfCnpj"] == "11222333000181" and cliente["email"] == "dono@navalha.com.br"
    plano = [c for c in cobranca.chamadas if c[1] == "/subscriptions"][0][2]
    assert plano["value"] == 59.90 and plano["cycle"] == "MONTHLY"
    assert plano["billingType"] == "UNDEFINED"
    assert plano["nextDueDate"] == "2030-03-15"  # vence no fim do teste: não perde dias
    barbearia = _barbearia(conta_nova.id)
    assert barbearia["asaas_cliente_id"] == "cus_1" and barbearia["asaas_assinatura_id"] == "sub_1"


def test_assinar_com_documento_invalido_nao_chama_o_asaas(conta_nova, cobranca):
    html = conta_nova.client.post("/assinatura/assinar", data={
        "documento": "123", "email": "dono@navalha.com.br",
    }, follow_redirects=True).get_data(as_text=True)
    assert "CPF ou CNPJ inválido" in html
    assert cobranca.chamadas == []


def test_erro_do_asaas_aparece_para_o_dono(conta_nova, cobranca, monkeypatch):
    def falha(*args, **kwargs):
        raise assinatura.ErroCobranca("CPF/CNPJ informado é inválido.")
    monkeypatch.setattr(assinatura, "_chamar", falha)
    html = conta_nova.client.post("/assinatura/assinar", data={
        "documento": CPF_VALIDO, "email": "dono@navalha.com.br",
    }, follow_redirects=True).get_data(as_text=True)
    assert "CPF/CNPJ informado é inválido." in html


def test_sem_chave_do_asaas_explica(monkeypatch):
    monkeypatch.delenv("ASAAS_API_KEY", raising=False)
    with pytest.raises(assinatura.ErroCobranca, match="ainda não foi configurada"):
        assinatura._chamar("GET", "/customers")


def test_barbeiro_nao_assina(cobranca, client_barbeiro):
    assert client_barbeiro.post("/assinatura/assinar", data={}).status_code == 403


# ---------- AVISOS DO ASAAS ----------

def _assinada(conta_nova):
    conta_nova.client.post("/assinatura/assinar", data={"documento": CPF_VALIDO, "email": "a@b.com"})


def test_pagamento_confirmado_libera(conta_nova, cobranca, client_anonimo):
    _assinada(conta_nova)
    cobranca.relogio["hoje"] = date(2030, 3, 20)  # teste acabou
    assert conta_nova.client.get("/agenda").status_code == 302
    resposta = _aviso(client_anonimo, {"id": "evt_1", "event": "PAYMENT_CONFIRMED",
                                       "payment": {"id": "pay_1", "subscription": "sub_1"}})
    assert resposta.status_code == 200 and resposta.get_json() == {"received": True}
    assert _barbearia(conta_nova.id)["assinatura_status"] == "ativa"
    assert conta_nova.client.get("/agenda").status_code == 200


def test_atraso_da_tolerancia_e_depois_bloqueia(conta_nova, cobranca, client_anonimo):
    _assinada(conta_nova)
    _aviso(client_anonimo, {"id": "evt_1", "event": "PAYMENT_RECEIVED",
                            "payment": {"id": "pay_1", "subscription": "sub_1"}})
    cobranca.relogio["hoje"] = date(2030, 4, 16)
    _aviso(client_anonimo, {"id": "evt_2", "event": "PAYMENT_OVERDUE",
                            "payment": {"id": "pay_2", "subscription": "sub_1",
                                        "invoiceUrl": "https://www.asaas.com/i/pay_2"}})
    barbearia = _barbearia(conta_nova.id)
    assert barbearia["assinatura_status"] == "atrasada" and barbearia["atrasada_desde"] == "2030-04-16"
    html = conta_nova.client.get("/agenda").get_data(as_text=True)
    assert "mensalidade está vencida" in html  # ainda liberada (3 dias)
    cobranca.relogio["hoje"] = date(2030, 4, 20)
    assert conta_nova.client.get("/agenda").status_code == 302
    assert "https://www.asaas.com/i/pay_2" in conta_nova.client.get("/assinatura").get_data(as_text=True)


def test_assinatura_cancelada_bloqueia(conta_nova, cobranca, client_anonimo):
    _assinada(conta_nova)
    _aviso(client_anonimo, {"id": "evt_9", "event": "SUBSCRIPTION_DELETED",
                            "subscription": {"id": "sub_1"}})
    assert _barbearia(conta_nova.id)["assinatura_status"] == "cancelada"
    assert conta_nova.client.get("/agenda").status_code == 302


def test_aviso_repetido_e_ignorado(conta_nova, cobranca, client_anonimo):
    _assinada(conta_nova)
    evento = {"id": "evt_1", "event": "PAYMENT_CONFIRMED", "payment": {"subscription": "sub_1"}}
    _aviso(client_anonimo, evento)
    assert assinatura.processar_evento(evento) == "repetido"


def test_aviso_sem_token_ou_com_token_errado_e_recusado(conta_nova, cobranca, client_anonimo):
    _assinada(conta_nova)
    evento = {"id": "evt_1", "event": "PAYMENT_CONFIRMED", "payment": {"subscription": "sub_1"}}
    assert client_anonimo.post("/webhooks/asaas", json=evento).status_code == 401
    assert _aviso(client_anonimo, evento, token="errado").status_code == 401
    assert _barbearia(conta_nova.id)["assinatura_status"] == "teste"


def test_aviso_sem_token_configurado_e_recusado(conta_nova, cobranca, client_anonimo, monkeypatch):
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "")
    assert _aviso(client_anonimo, {"id": "x", "event": "PAYMENT_CONFIRMED"}, token="").status_code == 401


def test_aviso_nao_mexe_em_conta_isenta(cobranca, client_anonimo):
    _aviso(client_anonimo, {"id": "evt_1", "event": "PAYMENT_OVERDUE",
                            "payment": {"externalReference": str(BARBEARIA)}})
    assert _barbearia(BARBEARIA)["assinatura_status"] == "isenta"


def test_aviso_de_barbearia_desconhecida_responde_ok(cobranca, client_anonimo):
    resposta = _aviso(client_anonimo, {"id": "evt_1", "event": "PAYMENT_CONFIRMED",
                                       "payment": {"subscription": "sub_nao_existe"}})
    assert resposta.status_code == 200


def test_banco_antigo_ganha_colunas_e_fica_isento():
    conn = database.get_connection()
    conn.execute("DROP TABLE IF EXISTS eventos_pagamento")
    conn.commit()
    conn.close()
    database.atualizar_banco()
    assert _barbearia(BARBEARIA)["assinatura_status"] == "isenta"
    assert assinatura.processar_evento({"id": "e", "event": "X"}) == "ignorado: barbearia desconhecida"
