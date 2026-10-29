"""
test_correcoes.py

Correções antes do link público: WhatsApp padronizado e sem repetição,
ficha do cliente (editar, excluir, histórico, busca), atendimento lançado
em dobro, avisos de bloqueio e de horário com cliente marcado, e comissão
arredondada em centavos.
"""

from datetime import datetime

import pytest

import agenda
import database
import models
import reports
import telefones
from conftest import BARBEARIA, BARBEIRO_JOAO, logar
from database import get_connection

SEGUNDA = "2030-01-07"
ELENILTON, JOAO = 1, BARBEIRO_JOAO
CARLOS = 1


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    atual = {"agora": datetime(2030, 1, 7, 8, 0)}
    monkeypatch.setattr(agenda, "agora", lambda: atual["agora"])
    return lambda texto: atual.update(agora=datetime.strptime(texto, "%Y-%m-%d %H:%M"))


def _post(client, rota, dados=None):
    return client.post(rota, data=dados or {}, follow_redirects=True).get_data(as_text=True)


# ---------- WHATSAPP ----------

@pytest.mark.parametrize("digitado, padrao", [
    ("71988112040", "(71) 98811-2040"),
    ("(71) 98811-2040", "(71) 98811-2040"),
    ("+55 71 98811-2040", "(71) 98811-2040"),
    ("071 98811 2040", "(71) 98811-2040"),
    ("7133112040", "(71) 3311-2040"),
    ("", None),
    ("   ", None),
])
def test_normalizar_telefone(digitado, padrao):
    assert telefones.normalizar(digitado) == padrao


@pytest.mark.parametrize("digitado", ["123", "98811-2040", "71888112040", "00988112040", "719881120401"])
def test_telefone_invalido(digitado):
    with pytest.raises(ValueError, match="WhatsApp inválido"):
        telefones.normalizar(digitado)


def test_cliente_gravado_com_telefone_padrao_e_sem_repetir():
    cliente_id = models.criar_cliente(BARBEARIA, "  Lucas Mendes ", "71 97777 0000")
    assert models.buscar_cliente(BARBEARIA, cliente_id)["telefone"] == "(71) 97777-0000"
    assert models.buscar_cliente(BARBEARIA, cliente_id)["nome"] == "Lucas Mendes"
    with pytest.raises(ValueError, match="já é do cliente Lucas Mendes"):
        models.criar_cliente(BARBEARIA, "Outro", "+55 (71) 97777-0000")


def test_mesmo_telefone_pode_existir_em_outra_barbearia(outra_barbearia):
    models.criar_cliente(BARBEARIA, "Lucas", "71977770000")
    models.criar_cliente(outra_barbearia.id, "Lucas", "71977770000")


@pytest.mark.parametrize("nome", ["", "   ", None])
def test_cliente_sem_nome_e_recusado(nome):
    with pytest.raises(ValueError, match="não pode ficar em branco"):
        models.criar_cliente(BARBEARIA, nome, None)


def test_atualizar_banco_padroniza_telefones_antigos():
    conn = get_connection()
    conn.execute("UPDATE clientes SET telefone = '71 9 8811 2040' WHERE id = 1")
    conn.execute("UPDATE clientes SET telefone = 'ligar depois' WHERE id = 2")
    conn.commit()
    conn.close()
    database.atualizar_banco()
    assert models.buscar_cliente(BARBEARIA, 1)["telefone"] == "(71) 98811-2040"
    assert models.buscar_cliente(BARBEARIA, 2)["telefone"] == "ligar depois"  # não entendido: fica


# ---------- FICHA DO CLIENTE ----------

def test_busca_por_nome_e_por_telefone():
    assert [c["nome"] for c in models.listar_clientes(BARBEARIA, "rafa")] == ["Rafael Lima"]
    assert [c["nome"] for c in models.listar_clientes(BARBEARIA, "0003")] == ["Bruno Andrade"]
    assert models.listar_clientes(BARBEARIA, "ninguém") == []


def test_busca_pela_tela(client):
    html = client.get("/clientes?busca=rafa").get_data(as_text=True)
    lista = html.split("Lista de clientes")[1]
    assert "Rafael Lima" in lista and "Carlos Souza" not in lista


def test_ficha_mostra_historico_e_proximos(client):
    models.criar_atendimento(BARBEARIA, CARLOS, ELENILTON, 1, 35)
    agenda.criar_agendamento(BARBEARIA, 1, CARLOS, [2], SEGUNDA, "10:00", JOAO)
    html = client.get(f"/clientes/{CARLOS}").get_data(as_text=True)
    assert "Corte Masculino" in html and "R$ 35,00" in html
    assert "07/01/2030 10:00 com João Pereira" in html


def test_editar_cliente_pela_ficha(client):
    html = _post(client, f"/clientes/{CARLOS}", {"nome": "Carlos S. Souza", "telefone": "71 99999 1234"})
    assert "Cliente salvo" in html
    cliente = models.buscar_cliente(BARBEARIA, CARLOS)
    assert cliente["nome"] == "Carlos S. Souza" and cliente["telefone"] == "(71) 99999-1234"


def test_editar_para_telefone_de_outro_e_recusado(client):
    html = _post(client, f"/clientes/{CARLOS}", {"nome": "Carlos", "telefone": "(71) 90000-0002"})
    assert "já é do cliente Rafael Lima" in html
    assert models.buscar_cliente(BARBEARIA, CARLOS)["nome"] == "Carlos Souza"


def test_exclui_cliente_sem_historico(client):
    cliente_id = models.criar_cliente(BARBEARIA, "Cadastro Errado")
    html = _post(client, f"/clientes/{cliente_id}/excluir")
    assert "excluído" in html
    assert models.buscar_cliente(BARBEARIA, cliente_id) is None


def test_nao_exclui_cliente_com_historico(client):
    models.criar_atendimento(BARBEARIA, CARLOS, ELENILTON, 1, 35)
    html = _post(client, f"/clientes/{CARLOS}/excluir")
    assert "não pode ser excluído" in html
    assert models.buscar_cliente(BARBEARIA, CARLOS) is not None


def test_barbeiro_nao_exclui_cliente(client_barbeiro):
    cliente_id = models.criar_cliente(BARBEARIA, "Cadastro Errado")
    assert client_barbeiro.post(f"/clientes/{cliente_id}/excluir").status_code == 403


def test_ficha_de_cliente_de_outra_barbearia_da_404(client, outra_barbearia):
    assert client.get(f"/clientes/{outra_barbearia.cliente_id}").status_code == 404


# ---------- AGENDA RECONHECE O CLIENTE PELO WHATSAPP ----------

def test_cliente_novo_com_whatsapp_conhecido_usa_o_cadastro(client):
    clientes_antes = len(models.listar_clientes(BARBEARIA))
    html = _post(client, "/agenda/novo", {
        "unidade_id": "1", "data": SEGUNDA, "hora": "10:00", "servico_id": "1",
        "barbeiro_id": "", "novo_cliente_nome": "Carlinhos", "novo_cliente_telefone": "71900000001",
    })
    assert "já era de Carlos Souza" in html
    assert len(models.listar_clientes(BARBEARIA)) == clientes_antes
    (item,) = agenda.listar_agenda(BARBEARIA, SEGUNDA)
    assert item["cliente_id"] == CARLOS


def test_cliente_novo_com_whatsapp_invalido_nao_marca(client):
    html = _post(client, "/agenda/novo", {
        "unidade_id": "1", "data": SEGUNDA, "hora": "10:00", "servico_id": "1",
        "barbeiro_id": "", "novo_cliente_nome": "Fulano", "novo_cliente_telefone": "123",
    })
    assert "WhatsApp inválido" in html
    assert agenda.listar_agenda(BARBEARIA, SEGUNDA) == []


# ---------- LANÇAMENTO EM DOBRO ----------

def test_atendimento_avulso_de_quem_tem_horario_hoje_vai_para_a_agenda(client):
    agenda.criar_agendamento(BARBEARIA, 1, CARLOS, [1], SEGUNDA, "10:00", ELENILTON)
    antes = reports.faturamento_total(BARBEARIA)
    html = _post(client, "/atendimentos/novo", {
        "cliente_id": str(CARLOS), "barbeiro_id": str(ELENILTON), "servico_id": "1",
        "valor_cobrado": "35", "forma_pagamento": "pix",
    })
    assert "Conclua pela agenda" in html
    assert reports.faturamento_total(BARBEARIA) == pytest.approx(antes)


def test_atendimento_avulso_com_outro_barbeiro_passa(client):
    agenda.criar_agendamento(BARBEARIA, 1, CARLOS, [1], SEGUNDA, "10:00", ELENILTON)
    antes = reports.faturamento_total(BARBEARIA)
    client.post("/atendimentos/novo", data={
        "cliente_id": str(CARLOS), "barbeiro_id": str(JOAO), "servico_id": "2",
        "valor_cobrado": "25", "forma_pagamento": "pix",
    })
    assert reports.faturamento_total(BARBEARIA) == pytest.approx(antes + 25)


# ---------- AVISOS ----------

def test_bloqueio_avisa_quem_continua_marcado(client):
    agenda.criar_agendamento(BARBEARIA, 1, CARLOS, [1], SEGUNDA, "12:15", ELENILTON)
    html = _post(client, "/agenda/bloqueios/novo", {
        "barbeiro_id": str(ELENILTON), "inicio": f"{SEGUNDA}T12:00", "fim": f"{SEGUNDA}T13:00",
    })
    assert "continuam marcados" in html and "Carlos Souza em 07/01 às 12:15" in html


def test_bloqueio_sem_conflito_confirma(client):
    html = _post(client, "/agenda/bloqueios/novo", {
        "barbeiro_id": str(ELENILTON), "inicio": f"{SEGUNDA}T12:00", "fim": f"{SEGUNDA}T13:00",
    })
    assert "Horário bloqueado" in html


def test_mudar_horario_avisa_quem_ficou_fora(client):
    agenda.criar_agendamento(BARBEARIA, 1, CARLOS, [1], SEGUNDA, "18:00", ELENILTON)
    dados = {"nome": "Principal"}
    dados.update({f"abre_{d}_1": "09:00" for d in range(6)})
    dados.update({f"fecha_{d}_1": "17:00" for d in range(6)})
    html = _post(client, "/unidades/1/editar", dados)
    assert "ficaram fora" in html and "Carlos Souza em 07/01 às 18:00" in html


# ---------- DINHEIRO ----------

def test_comissao_arredondada_em_centavos_por_atendimento():
    # 3 x R$ 33,33 com 50%: cada comissão é R$ 16,67 (arredondada), total R$ 50,01.
    for _ in range(3):
        models.criar_atendimento(BARBEARIA, CARLOS, ELENILTON, 1, "33,33")
    (linha,) = reports.comissoes_por_barbeiro(BARBEARIA, ELENILTON)
    assert linha["comissao_valor"] == pytest.approx(50.01)
    assert linha["total_faturado"] == pytest.approx(99.99)


def test_valor_com_mais_de_duas_casas_e_arredondado():
    models.criar_atendimento(BARBEARIA, CARLOS, ELENILTON, 1, "35.105")
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["valor_cobrado"] == pytest.approx(35.11) or atendimento["valor_cobrado"] == pytest.approx(35.1)


def test_soma_de_muitos_valores_quebrados_fecha_no_centavo():
    for _ in range(3):
        models.criar_atendimento(BARBEARIA, CARLOS, ELENILTON, 1, "35,10")
    assert reports.faturamento_total(BARBEARIA) == 105.3
