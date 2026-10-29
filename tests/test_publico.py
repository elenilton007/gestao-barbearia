"""
test_publico.py

Link público de agendamento (/b/<endereço>): a página do cliente, marcar
sem login, reconhecer o cliente pelo WhatsApp, limites contra abuso,
ver e cancelar pelo link secreto, arquivo de calendário e a tela do dono
para configurar o link.

Relógio parado na segunda-feira 07/01/2030 às 08:00.
"""

from datetime import datetime

import pytest

import agenda
import database
import models
import publico
from conftest import BARBEARIA
from database import get_connection

SEGUNDA, TERCA = "2030-01-07", "2030-01-08"
ELENILTON = 1
CARLOS_TEL = "(71) 90000-0001"  # Carlos Souza, cliente 1 dos dados de exemplo


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    atual = {"agora": datetime(2030, 1, 7, 8, 0)}
    monkeypatch.setattr(agenda, "agora", lambda: atual["agora"])
    return lambda texto: atual.update(agora=datetime.strptime(texto, "%Y-%m-%d %H:%M"))


@pytest.fixture
def slug():
    return models.buscar_barbearia(BARBEARIA)["slug"]


def _pedido(slug, **extra):
    dados = {
        "unidade_id": "1", "servico_id": "1", "data": SEGUNDA, "hora": "10:00",
        "barbeiro_id": "", "nome": "Pedro Novo", "whatsapp": "71 98888 7777", "aceite": "1",
    }
    dados.update(extra)
    return dados


def _agendar(client, slug, **extra):
    return client.post(f"/b/{slug}/agendar", data=_pedido(slug, **extra))


def _texto(resposta):
    return resposta.get_data(as_text=True)


# ---------- ENDEREÇO ----------

def test_endereco_gerado_pelo_nome(outra_barbearia, slug):
    assert slug == "barbearia-exemplo"
    assert models.buscar_barbearia(outra_barbearia.id)["slug"] == "navalha-de-ouro"


def test_nome_repetido_ganha_numero():
    nova = models.criar_barbearia_com_dono("Barbearia Exemplo", "dono-2", "senha-forte")
    assert models.buscar_barbearia(nova)["slug"] == "barbearia-exemplo-2"


def test_acentos_e_simbolos_saem_do_endereco():
    nova = models.criar_barbearia_com_dono("Salão do Zé & Cia!", "dono-3", "senha-forte")
    assert models.buscar_barbearia(nova)["slug"] == "salao-do-ze-cia"


def test_banco_antigo_ganha_endereco_e_regras():
    conn = get_connection()
    conn.execute("UPDATE barbearias SET slug = NULL")
    conn.commit()
    conn.close()
    database.atualizar_banco()
    barbearia = models.buscar_barbearia(BARBEARIA)
    assert barbearia["slug"] == "barbearia-exemplo"
    assert barbearia["online_ativo"] == 1 and barbearia["cancelamento_horas"] == 2


# ---------- PÁGINA ----------

def test_pagina_publica_abre_sem_login(client_anonimo, slug):
    html = _texto(client_anonimo.get(f"/b/{slug}"))
    assert "Barbearia Exemplo" in html and "Marque seu horário" in html
    assert "Corte Masculino" in html and "R$ 35,00" in html
    assert "Elenilton Silveira" in html and "Sem preferência" in html
    assert "Como usamos seus dados" in html


def test_endereco_desconhecido_da_404(client_anonimo):
    assert client_anonimo.get("/b/nao-existe").status_code == 404


def test_pagina_publica_nao_vaza_dados_de_clientes(client_anonimo, slug):
    html = _texto(client_anonimo.get(f"/b/{slug}"))
    assert "Carlos Souza" not in html and "90000-0001" not in html


def test_horarios_publicos_nao_mostram_quem_esta_livre(client_anonimo, slug):
    dados = client_anonimo.get(f"/b/{slug}/horarios?unidade=1&data={SEGUNDA}&servicos=1").get_json()
    assert dados["horarios"][0] == {"hora": "09:00"}


def test_privacidade(client_anonimo, slug):
    html = _texto(client_anonimo.get(f"/b/{slug}/privacidade"))
    assert "13.709/2018" in html


def test_cabecalhos_de_privacidade(client_anonimo, slug):
    assert client_anonimo.get(f"/b/{slug}").headers["Referrer-Policy"] == "no-referrer"


# ---------- MARCAR ----------

def test_cliente_novo_marca_pelo_link(client_anonimo, slug):
    resposta = _agendar(client_anonimo, slug, servico_id=["1", "2"])
    assert resposta.status_code == 302 and "/horario/" in resposta.headers["Location"]
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["origem"] == "online" and item["token"]
    assert item["cliente"] == "Pedro Novo" and item["telefone"] == "(71) 98888-7777"
    assert item["servicos"] == ["Corte Masculino", "Barba"]

    html = _texto(client_anonimo.get(resposta.headers["Location"]))
    assert "Horário marcado" in html and "Segunda, 7 de janeiro, às 10:00" in html
    assert "Guarde este link" in html


def test_cliente_conhecido_entra_no_proprio_cadastro(client_anonimo, slug):
    antes = len(models.listar_clientes(BARBEARIA))
    _agendar(client_anonimo, slug, nome="Outro Nome", whatsapp="71900000001")
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["cliente_id"] == 1 and item["cliente"] == "Carlos Souza"
    assert len(models.listar_clientes(BARBEARIA)) == antes


def test_limite_de_horarios_por_whatsapp(client_anonimo, slug):
    _agendar(client_anonimo, slug, hora="10:00")
    _agendar(client_anonimo, slug, hora="11:00")
    resposta = client_anonimo.post(f"/b/{slug}/agendar", data=_pedido(slug, hora="12:00"),
                                   follow_redirects=True)
    assert "já tem 2 horários marcados" in _texto(resposta)
    assert len(agenda.listar_agenda(BARBEARIA, SEGUNDA)) == 2


@pytest.mark.parametrize("extra, mensagem", [
    ({"aceite": ""}, "confirme que leu"),
    ({"nome": "  "}, "Informe o seu nome"),
    ({"whatsapp": ""}, "Informe o seu WhatsApp"),
    ({"whatsapp": "123"}, "WhatsApp inválido"),
    ({"hora": "08:00"}, "acabou de ser ocupado"),
    ({"servico_id": []}, "pelo menos um serviço"),
])
def test_pedido_incompleto_nao_marca(client_anonimo, slug, extra, mensagem):
    resposta = client_anonimo.post(f"/b/{slug}/agendar", data=_pedido(slug, **extra),
                                   follow_redirects=True)
    assert mensagem in _texto(resposta)
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


def test_horario_tomado_nao_cria_cliente_sobrando(client_anonimo, slug):
    agenda.criar_agendamento(BARBEARIA, 1, 1, [1], SEGUNDA, "10:00", 1)
    agenda.criar_agendamento(BARBEARIA, 1, 2, [1], SEGUNDA, "10:00", 2)
    antes = len(models.listar_clientes(BARBEARIA))
    _agendar(client_anonimo, slug)
    assert len(models.listar_clientes(BARBEARIA)) == antes


def test_robo_que_preenche_o_campo_escondido_e_barrado(client_anonimo, slug):
    assert _agendar(client_anonimo, slug, site="http://spam").status_code == 400
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


def test_limite_de_pedidos_por_aparelho(client_anonimo, slug):
    for _ in range(10):
        client_anonimo.post(f"/b/{slug}/agendar", data=_pedido(slug, whatsapp="123"))
    resposta = client_anonimo.post(f"/b/{slug}/agendar", data=_pedido(slug), follow_redirects=True)
    assert "Muitos agendamentos seguidos" in _texto(resposta)
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


def test_limite_reabre_depois_da_janela(monkeypatch):
    agora = {"t": 1000.0}
    monkeypatch.setattr(publico, "_agora_segundos", lambda: agora["t"])
    assert all(publico.pode_tentar("x", 2, 60) for _ in range(2))
    assert not publico.pode_tentar("x", 2, 60)
    agora["t"] += 61
    assert publico.pode_tentar("x", 2, 60)


def test_link_pausado_nao_marca(client_anonimo, slug):
    publico.salvar_configuracao(BARBEARIA, slug, "", False, 2, 2)
    assert "pausado" in _texto(client_anonimo.get(f"/b/{slug}"))
    assert client_anonimo.get(f"/b/{slug}/horarios?unidade=1&data={SEGUNDA}&servicos=1").get_json()["horarios"] == []
    resposta = client_anonimo.post(f"/b/{slug}/agendar", data=_pedido(slug), follow_redirects=True)
    assert "pausado" in _texto(resposta)
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


def test_csrf_protege_o_agendamento_publico(slug):
    from app import app

    app.config["WTF_CSRF_ENABLED"] = True
    try:
        with app.test_client() as client:
            assert client.post(f"/b/{slug}/agendar", data=_pedido(slug)).status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_marcado_pelo_link_aparece_na_agenda_da_barbearia(client_anonimo, client, slug):
    _agendar(client_anonimo, slug)
    assert "pelo link" in _texto(client.get(f"/agenda?data={SEGUNDA}"))


# ---------- VER E CANCELAR ----------

def _token(client, slug, **extra):
    resposta = _agendar(client, slug, **extra)
    return resposta.headers["Location"].split("/horario/")[1].split("?")[0]


def test_cliente_cancela_dentro_do_prazo(client_anonimo, slug):
    token = _token(client_anonimo, slug)
    html = _texto(client_anonimo.post(f"/b/{slug}/horario/{token}/cancelar", follow_redirects=True))
    assert "Horário cancelado" in html
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["status"] == "cancelado"


def test_cliente_nao_cancela_depois_do_prazo(client_anonimo, slug, relogio):
    token = _token(client_anonimo, slug)  # 10:00, cancela até 08:00 (2 horas antes)
    relogio(f"{SEGUNDA} 08:30")
    html = _texto(client_anonimo.get(f"/b/{slug}/horario/{token}"))
    assert "prazo para cancelar pelo link já passou" in html
    html = _texto(client_anonimo.post(f"/b/{slug}/horario/{token}/cancelar", follow_redirects=True))
    assert "vai até 2 horas antes" in html
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["status"] == "marcado"


def test_token_errado_ou_de_outra_barbearia_da_404(client_anonimo, slug, outra_barbearia):
    token = _token(client_anonimo, slug)
    outro_slug = models.buscar_barbearia(outra_barbearia.id)["slug"]
    assert client_anonimo.get(f"/b/{outro_slug}/horario/{token}").status_code == 404
    assert client_anonimo.get(f"/b/{slug}/horario/token-que-nao-existe").status_code == 404
    assert client_anonimo.post(f"/b/{outro_slug}/horario/{token}/cancelar").status_code == 404


def test_pagina_do_horario_nao_fica_em_cache(client_anonimo, slug):
    token = _token(client_anonimo, slug)
    assert client_anonimo.get(f"/b/{slug}/horario/{token}").headers["Cache-Control"] == "no-store"


def test_arquivo_de_calendario(client_anonimo, slug):
    token = _token(client_anonimo, slug, servico_id=["1", "2"])
    resposta = client_anonimo.get(f"/b/{slug}/horario/{token}/calendario.ics")
    assert resposta.mimetype == "text/calendar"
    texto = _texto(resposta)
    assert "DTSTART:20300107T100000" in texto and "DTEND:20300107T105000" in texto
    assert "Corte Masculino\\, Barba na Barbearia Exemplo" in texto


# ---------- CONFIGURAÇÃO PELO DONO ----------

def test_dono_configura_o_link(client):
    html = _texto(client.post("/configuracoes/link", data={
        "nome": "  Barbearia Ponto Certo ", "slug": "ponto-certo", "whatsapp": "71 3311 2040", "online_ativo": "1",
        "cancelamento_horas": "6", "limite_por_cliente": "3",
    }, follow_redirects=True))
    assert "Link de agendamento salvo" in html
    barbearia = models.buscar_barbearia(BARBEARIA)
    assert barbearia["slug"] == "ponto-certo" and barbearia["whatsapp"] == "(71) 3311-2040"
    assert barbearia["nome"] == "Barbearia Ponto Certo"
    assert barbearia["cancelamento_horas"] == 6 and barbearia["limite_por_cliente"] == 3
    assert "/b/ponto-certo" in html


@pytest.mark.parametrize("slug_novo", ["a", "Com Espaço", "acentuação", "-comeca-com-hifen", "dois--hifens"])
def test_endereco_invalido_e_recusado(client, slug_novo):
    html = _texto(client.post("/configuracoes/link", data={
        "slug": slug_novo, "online_ativo": "1", "cancelamento_horas": "2", "limite_por_cliente": "2",
    }, follow_redirects=True))
    assert "Endereço inválido" in html
    assert models.buscar_barbearia(BARBEARIA)["slug"] == "barbearia-exemplo"


def test_endereco_de_outra_barbearia_e_recusado(client, outra_barbearia):
    html = _texto(client.post("/configuracoes/link", data={
        "slug": "navalha-de-ouro", "online_ativo": "1", "cancelamento_horas": "2", "limite_por_cliente": "2",
    }, follow_redirects=True))
    assert "já é de outra barbearia" in html


def test_regras_fora_da_lista_sao_recusadas(client):
    html = _texto(client.post("/configuracoes/link", data={
        "slug": "barbearia-exemplo", "online_ativo": "1", "cancelamento_horas": "999", "limite_por_cliente": "2",
    }, follow_redirects=True))
    assert "Regras do agendamento inválidas" in html


def test_qrcode_do_link(client):
    resposta = client.get("/configuracoes/link/qrcode.svg")
    assert resposta.mimetype == "image/svg+xml" and b"<svg" in resposta.data


def test_barbeiro_nao_configura_o_link(client_barbeiro):
    assert client_barbeiro.get("/configuracoes/link").status_code == 403
    assert client_barbeiro.get("/configuracoes/link/qrcode.svg").status_code == 403


def test_nome_em_branco_e_recusado(client):
    html = _texto(client.post("/configuracoes/link", data={
        "nome": "  ", "slug": "barbearia-exemplo", "online_ativo": "1",
        "cancelamento_horas": "2", "limite_por_cliente": "2",
    }, follow_redirects=True))
    assert "não pode ficar em branco" in html
    assert models.buscar_barbearia(BARBEARIA)["nome"] == "Barbearia Exemplo"
