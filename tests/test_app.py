"""
test_app.py

Testes das rotas da aplicação Flask.
"""

import pytest

import models
import reports


@pytest.mark.parametrize("rota", ["/", "/clientes", "/atendimentos", "/relatorios"])
def test_paginas_carregam(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 200
    assert "Gestão de Barbearia" in resposta.get_data(as_text=True)


def test_dashboard_mostra_faturamento(client):
    models.criar_atendimento(1, 1, 1, 35.00)
    html = client.get("/").get_data(as_text=True)
    assert "R$ 35.00" in html
    assert "R$ 17.50" in html  # comissão de 50%


def test_cadastrar_cliente_pelo_formulario(client):
    resposta = client.post(
        "/clientes/novo", data={"nome": "Lucas Mendes", "telefone": "(71) 97777-0000"}
    )
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/clientes")
    assert "Lucas Mendes" in client.get("/clientes").get_data(as_text=True)


def test_cadastrar_cliente_sem_nome_retorna_erro(client):
    resposta = client.post("/clientes/novo", data={"telefone": "123"})
    assert resposta.status_code == 400


def test_registrar_atendimento_pelo_formulario(client):
    resposta = client.post(
        "/atendimentos/novo",
        data={
            "cliente_id": "2",
            "barbeiro_id": "1",
            "servico_id": "2",
            "valor_cobrado": "25.00",
            "forma_pagamento": "cartao",
        },
    )
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/atendimentos")

    html = client.get("/atendimentos").get_data(as_text=True)
    assert "Rafael Lima" in html
    assert "cartao" in html
    assert reports.faturamento_total() == pytest.approx(25.00)
