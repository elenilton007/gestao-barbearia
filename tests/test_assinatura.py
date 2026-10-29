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
    """Barbearia criada pelo cadastro (começa no teste grátis de 7 dias), já logada."""
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

def test_conta_nova_comeca_no_teste_de_7_dias(conta_nova):
    barbearia = _barbearia(conta_nova.id)
    assert barbearia["assinatura_status"] == "teste"
    assert barbearia["teste_ate"] == "2030-03-08"
    html = conta_nova.client.get("/agenda").get_data(as_text=True)
    assert "Teste grátis: faltam 7 dias" in html


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
    assert plano["nextDueDate"] == "2030-03-08"  # vence no fim do teste: não perde dias
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


# ---------- PAGAR NO CADASTRO (TESTE_DIAS=0) ----------

@pytest.fixture
def conta_paga_no_cadastro(cobranca, client_anonimo, monkeypatch):
    monkeypatch.setenv("TESTE_DIAS", "0")
    resposta = client_anonimo.post("/cadastro", data={
        "nome_barbearia": "Corte Fino", "whatsapp": "71988885678", "usuario": "maria.souza",
        "senha": "senha-forte-1", "confirmacao": "senha-forte-1", "aceite": "1",
    })
    dono = models.buscar_usuario_por_nome("maria.souza")
    return type("Conta", (), {"client": client_anonimo, "id": dono["barbearia_id"], "resposta": resposta})


def test_sem_teste_o_cadastro_leva_direto_ao_pagamento(conta_paga_no_cadastro):
    conta = conta_paga_no_cadastro
    assert conta.resposta.headers["Location"].endswith("/assinatura")
    assert _barbearia(conta.id)["assinatura_status"] == "pendente"
    assert conta.client.get("/agenda").status_code == 302
    html = conta.client.get("/assinatura").get_data(as_text=True)
    assert "Aguardando o primeiro pagamento" in html and "Gerar fatura" in html


def test_pendente_gera_fatura_para_hoje_e_libera_ao_pagar(conta_paga_no_cadastro, cobranca, client_anonimo):
    conta = conta_paga_no_cadastro
    conta.client.post("/assinatura/assinar", data={"documento": CPF_VALIDO, "email": "maria@exemplo.com"})
    criada = [d for m, c, d in cobranca.chamadas if c == "/subscriptions"][0]
    assert criada["nextDueDate"] == "2030-03-01"
    assert "https://www.asaas.com/i/pay_1" in conta.client.get("/assinatura").get_data(as_text=True)
    _aviso(client_anonimo, {"id": "evt_p", "event": "PAYMENT_CONFIRMED",
                            "payment": {"id": "pay_1", "subscription": "sub_1"}})
    assert _barbearia(conta.id)["assinatura_status"] == "ativa"
    assert conta.client.get("/agenda").status_code == 200


def test_pendente_com_fatura_vencida_continua_bloqueado(conta_paga_no_cadastro, cobranca, client_anonimo):
    conta = conta_paga_no_cadastro
    conta.client.post("/assinatura/assinar", data={"documento": CPF_VALIDO, "email": "maria@exemplo.com"})
    _aviso(client_anonimo, {"id": "evt_v", "event": "PAYMENT_OVERDUE",
                            "payment": {"id": "pay_1", "subscription": "sub_1",
                                        "invoiceUrl": "https://www.asaas.com/i/pay_9"}})
    barbearia = _barbearia(conta.id)
    assert barbearia["assinatura_status"] == "pendente"  # sem os 3 dias de tolerância
    assert barbearia["link_pagamento"] == "https://www.asaas.com/i/pay_9"
    assert conta.client.get("/agenda").status_code == 302


def test_sem_cobranca_ligada_conta_pendente_usa_normalmente(conta_paga_no_cadastro, monkeypatch):
    monkeypatch.setenv("COBRANCA_ATIVA", "0")
    assert conta_paga_no_cadastro.client.get("/agenda").status_code == 200


# ---------- ANTECIPAÇÃO DO CARTÃO ----------

def _pagamento_cartao(client, evento_id="evt_c", tipo="PAYMENT_CONFIRMED", forma="CREDIT_CARD"):
    return _aviso(client, {"id": evento_id, "event": tipo,
                           "payment": {"id": "pay_c", "subscription": "sub_1", "billingType": forma}})


def _com_antecipacao(cobranca, monkeypatch, falhar=False):
    original = assinatura._chamar

    def chamar(metodo, caminho, dados=None, formulario=False):
        if caminho == "/anticipations":
            assert formulario
            cobranca.chamadas.append((metodo, caminho, dados))
            if falhar:
                raise assinatura.ErroCobranca("Limite de antecipação atingido")
            return {"id": "ant_1", "status": "PENDING"}
        return original(metodo, caminho, dados)

    monkeypatch.setattr(assinatura, "_chamar", chamar)
    monkeypatch.setenv("ANTECIPAR_CARTAO", "1")


def test_pagamento_de_cartao_pede_antecipacao(conta_nova, cobranca, client_anonimo, monkeypatch):
    _assinada(conta_nova)
    _com_antecipacao(cobranca, monkeypatch)
    _pagamento_cartao(client_anonimo)
    assert ("POST", "/anticipations", {"payment": "pay_c"}) in cobranca.chamadas
    assert _barbearia(conta_nova.id)["assinatura_status"] == "ativa"


def test_aviso_repetido_nao_antecipa_de_novo(conta_nova, cobranca, client_anonimo, monkeypatch):
    _assinada(conta_nova)
    _com_antecipacao(cobranca, monkeypatch)
    _pagamento_cartao(client_anonimo)
    _pagamento_cartao(client_anonimo)
    assert sum(1 for _, c, _ in cobranca.chamadas if c == "/anticipations") == 1


@pytest.mark.parametrize("forma, tipo, ligado", [
    ("PIX", "PAYMENT_CONFIRMED", "1"),
    ("BOLETO", "PAYMENT_RECEIVED", "1"),
    ("CREDIT_CARD", "PAYMENT_RECEIVED", "1"),  # cartão já liquidado: nada a antecipar
    ("CREDIT_CARD", "PAYMENT_CONFIRMED", "0"),
])
def test_so_antecipa_cartao_confirmado_com_a_opcao_ligada(conta_nova, cobranca, client_anonimo, monkeypatch, forma, tipo, ligado):
    _assinada(conta_nova)
    _com_antecipacao(cobranca, monkeypatch)
    monkeypatch.setenv("ANTECIPAR_CARTAO", ligado)
    _pagamento_cartao(client_anonimo, tipo=tipo, forma=forma)
    assert not any(c == "/anticipations" for _, c, _ in cobranca.chamadas)


def test_antecipacao_recusada_nao_atrapalha_o_pagamento(conta_nova, cobranca, client_anonimo, monkeypatch):
    _assinada(conta_nova)
    _com_antecipacao(cobranca, monkeypatch, falhar=True)
    resposta = _pagamento_cartao(client_anonimo)
    assert resposta.status_code == 200
    assert _barbearia(conta_nova.id)["assinatura_status"] == "ativa"
    assert conta_nova.client.get("/agenda").status_code == 200


def test_formulario_vai_em_multipart(monkeypatch):
    enviados = {}

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"id": "ant_1"}'

    def abrir(pedido, timeout):
        enviados["tipo"] = pedido.get_header("Content-type")
        enviados["corpo"] = pedido.data
        return Resposta()

    monkeypatch.setenv("ASAAS_API_KEY", "chave")
    monkeypatch.setattr(assinatura.urllib.request, "urlopen", abrir)
    assert assinatura._chamar("POST", "/anticipations", {"payment": "pay_9"}, formulario=True) == {"id": "ant_1"}
    assert enviados["tipo"].startswith("multipart/form-data; boundary=")
    assert b'name="payment"\r\n\r\npay_9\r\n' in enviados["corpo"]
