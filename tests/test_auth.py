"""
test_auth.py

Testes de login, logout e permissões por papel (dono x barbeiro).
"""

import pytest

import database
import models
import reports
from conftest import BARBEARIA, BARBEIRO_JOAO

ROTAS_PROTEGIDAS = ["/", "/clientes", "/atendimentos", "/relatorios"]


def _registrar_atendimentos_dos_dois_barbeiros():
    models.criar_atendimento(BARBEARIA, 1, 1, 3, 55.00)  # Elenilton, 50% -> 27,50
    models.criar_atendimento(BARBEARIA, 2, 2, 1, 35.00)  # João, 40% -> 14,00


# ---------- LOGIN / LOGOUT ----------

@pytest.mark.parametrize("rota", ROTAS_PROTEGIDAS)
def test_sem_login_redireciona_para_login(client_anonimo, rota):
    resposta = client_anonimo.get(rota)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")


@pytest.mark.parametrize("rota", ["/clientes/novo", "/atendimentos/novo"])
def test_post_sem_login_nao_grava_nada(client_anonimo, rota):
    resposta = client_anonimo.post(
        rota,
        data={
            "nome": "Intruso",
            "cliente_id": "1",
            "barbeiro_id": "1",
            "servico_id": "1",
            "valor_cobrado": "999",
        },
    )
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")
    assert "Intruso" not in {c["nome"] for c in models.listar_clientes(BARBEARIA)}
    assert models.listar_atendimentos(BARBEARIA) == []


def test_pagina_de_login_carrega(client_anonimo):
    resposta = client_anonimo.get("/login")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'name="senha"' in html
    assert "Relatórios" not in html  # menu escondido para quem não entrou


def test_login_com_senha_correta(client_anonimo):
    resposta = client_anonimo.post(
        "/login", data={"usuario": "dono", "senha": "senha-do-dono"}
    )
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    assert client_anonimo.get("/").status_code == 200


@pytest.mark.parametrize(
    "usuario, senha",
    [("dono", "senha-errada"), ("ninguem", "senha-do-dono"), ("", "")],
)
def test_login_invalido_e_recusado(client_anonimo, usuario, senha):
    resposta = client_anonimo.post("/login", data={"usuario": usuario, "senha": senha})
    assert resposta.status_code == 401
    assert "Usuário ou senha inválidos" in resposta.get_data(as_text=True)
    assert client_anonimo.get("/").status_code == 302


def test_logado_em_login_vai_para_dashboard(client):
    resposta = client.get("/login")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


def test_logout_encerra_a_sessao(client):
    resposta = client.post("/logout")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")
    assert client.get("/").status_code == 302


def test_logout_nao_aceita_get(client):
    assert client.get("/logout").status_code == 405


def test_sessao_de_usuario_apagado_vira_anonima(client):
    from database import get_connection

    conn = get_connection()
    conn.execute("DELETE FROM usuarios WHERE usuario = 'dono'")
    conn.commit()
    conn.close()
    assert client.get("/").status_code == 302


# ---------- DONO ----------

def test_dono_ve_comissoes_de_todos(client):
    _registrar_atendimentos_dos_dois_barbeiros()
    html = client.get("/").get_data(as_text=True)
    assert "Elenilton Silveira" in html
    assert "João Pereira" in html
    assert "R$ 90.00" in html  # faturamento total
    assert "Serviços Mais Vendidos" in html
    assert "Relatórios" in html


def test_dono_ve_todos_os_atendimentos(client):
    _registrar_atendimentos_dos_dois_barbeiros()
    html = client.get("/atendimentos").get_data(as_text=True)
    assert "Carlos Souza" in html
    assert "Rafael Lima" in html


def test_dono_registra_atendimento_para_qualquer_barbeiro(client):
    client.post(
        "/atendimentos/novo",
        data={"cliente_id": "1", "barbeiro_id": "1", "servico_id": "1",
              "valor_cobrado": "35.00"},
    )
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["barbeiro"] == "Elenilton Silveira"


# ---------- BARBEIRO ----------

def test_barbeiro_ve_so_a_propria_comissao(client_barbeiro):
    _registrar_atendimentos_dos_dois_barbeiros()
    html = client_barbeiro.get("/").get_data(as_text=True)
    assert "Minhas Comissões" in html
    assert "João Pereira" in html
    assert "R$ 14.00" in html
    assert "Elenilton Silveira" not in html
    assert "R$ 27.50" not in html
    assert "Faturamento Total" not in html
    assert "R$ 90.00" not in html
    assert "Serviços Mais Vendidos" not in html


def test_barbeiro_nao_acessa_relatorios(client_barbeiro):
    assert client_barbeiro.get("/relatorios").status_code == 403
    assert "Relatórios" not in client_barbeiro.get("/").get_data(as_text=True)


def test_barbeiro_ve_so_os_proprios_atendimentos(client_barbeiro):
    _registrar_atendimentos_dos_dois_barbeiros()
    html = client_barbeiro.get("/atendimentos").get_data(as_text=True)
    historico = html.split("Histórico de Atendimentos")[1]
    assert "Rafael Lima" in historico  # atendido pelo João
    assert "Carlos Souza" not in historico  # atendido pelo Elenilton
    assert "Elenilton Silveira" not in html  # nem aparece no formulário


def test_barbeiro_so_registra_atendimento_em_seu_nome(client_barbeiro):
    resposta = client_barbeiro.post(
        "/atendimentos/novo",
        data={"cliente_id": "1", "barbeiro_id": "1", "servico_id": "1",
              "valor_cobrado": "35.00"},
    )
    assert resposta.status_code == 302
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["barbeiro"] == "João Pereira"


def test_barbeiro_pode_cadastrar_cliente(client_barbeiro):
    client_barbeiro.post("/clientes/novo", data={"nome": "Cliente do João"})
    assert "Cliente do João" in {c["nome"] for c in models.listar_clientes(BARBEARIA)}


# ---------- MODELS / REPORTS ----------

def test_senha_guardada_em_hash():
    usuario = models.autenticar("dono", "senha-do-dono")
    assert usuario["senha_hash"] != "senha-do-dono"
    assert "senha-do-dono" not in usuario["senha_hash"]


@pytest.mark.parametrize(
    "papel, senha, barbeiro_id, mensagem",
    [
        ("gerente", "12345678", None, "Papel inválido"),
        ("dono", "curta", None, "pelo menos 8"),
        ("barbeiro", "12345678", None, "barbeiro_id"),
        ("barbeiro", "12345678", 99, "não existe"),
    ],
)
def test_criar_usuario_valida_dados(papel, senha, barbeiro_id, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        models.criar_usuario(BARBEARIA, "novo", senha, papel, barbeiro_id)


def test_usuario_repetido_e_recusado():

    with pytest.raises(database.IntegrityError):
        models.criar_usuario(BARBEARIA, "dono", "outra-senha", "dono")


def test_dono_nao_fica_vinculado_a_barbeiro():
    models.criar_usuario(BARBEARIA, "socio", "senha-do-socio", "dono", 1)
    assert models.autenticar("socio", "senha-do-socio")["barbeiro_id"] is None


def test_comissoes_filtradas_por_barbeiro():
    _registrar_atendimentos_dos_dois_barbeiros()
    (linha,) = reports.comissoes_por_barbeiro(BARBEARIA, BARBEIRO_JOAO)
    assert linha["barbeiro"] == "João Pereira"
    assert linha["comissao_valor"] == pytest.approx(14.00)


def test_atendimentos_filtrados_por_barbeiro():
    _registrar_atendimentos_dos_dois_barbeiros()
    (atendimento,) = models.listar_atendimentos(BARBEARIA, BARBEIRO_JOAO)
    assert atendimento["barbeiro"] == "João Pereira"
