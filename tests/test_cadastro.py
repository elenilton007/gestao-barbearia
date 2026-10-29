"""
test_cadastro.py

Cadastro de barbearia pela internet (/cadastro): quem compra o MeuBarber
cria a própria conta, com barbearia, unidade, dono e link prontos, e cai
na agenda com os primeiros passos.
"""

import pytest

import agenda
import models
import publico


def _dados(**extra):
    dados = {
        "nome_barbearia": "Navalha do Bairro", "whatsapp": "71 98888 1234",
        "usuario": "Joao.Silva", "senha": "senha-forte-1", "confirmacao": "senha-forte-1",
        "aceite": "1",
    }
    dados.update(extra)
    return dados


def _texto(resposta):
    return resposta.get_data(as_text=True)


def test_pagina_de_cadastro_abre_sem_login(client_anonimo):
    html = _texto(client_anonimo.get("/cadastro"))
    assert "Criar minha barbearia" in html and "termos de uso" in html


def test_login_tem_link_para_criar_conta(client_anonimo):
    assert "/cadastro" in _texto(client_anonimo.get("/login"))


def test_cria_a_barbearia_e_entra_na_agenda(client_anonimo):
    resposta = client_anonimo.post("/cadastro", data=_dados())
    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/agenda")

    dono = models.buscar_usuario_por_nome("joao.silva")
    assert dono["papel"] == "dono"
    barbearia = models.buscar_barbearia(dono["barbearia_id"])
    assert barbearia["nome"] == "Navalha do Bairro"
    assert barbearia["slug"] == "navalha-do-bairro"
    assert barbearia["whatsapp"] == "(71) 98888-1234"
    assert [u["nome"] for u in agenda.listar_unidades(barbearia["id"])] == ["Principal"]

    html = _texto(client_anonimo.get("/agenda"))
    assert "Primeiros passos" in html and "Navalha do Bairro" in html
    assert models.autenticar("joao.silva", "senha-forte-1") is not None


def test_conta_nova_nao_ve_dados_de_outra_barbearia(client_anonimo):
    client_anonimo.post("/cadastro", data=_dados())
    html = _texto(client_anonimo.get("/clientes"))
    assert "Carlos Souza" not in html  # cliente da Barbearia Exemplo


def test_link_publico_da_conta_nova_ja_existe(client_anonimo):
    client_anonimo.post("/cadastro", data=_dados())
    assert client_anonimo.get("/b/navalha-do-bairro").status_code == 200


def test_primeiros_passos_somem_quando_tem_servico_e_barbeiro(client_anonimo):
    client_anonimo.post("/cadastro", data=_dados())
    barbearia_id = models.buscar_usuario_por_nome("joao.silva")["barbearia_id"]
    models.criar_servico(barbearia_id, "Corte", 35, 30)
    assert "Primeiros passos" in _texto(client_anonimo.get("/agenda"))
    models.criar_barbeiro(barbearia_id, "João", 50)
    assert "Primeiros passos" not in _texto(client_anonimo.get("/agenda"))


@pytest.mark.parametrize("extra, mensagem", [
    ({"nome_barbearia": "  "}, "Informe o nome da barbearia"),
    ({"usuario": "jo"}, "Usuário inválido"),
    ({"usuario": "joão silva"}, "Usuário inválido"),
    ({"confirmacao": "outra-senha"}, "não conferem"),
    ({"senha": "curta", "confirmacao": "curta"}, "pelo menos 8"),
    ({"whatsapp": ""}, "Informe o WhatsApp"),
    ({"whatsapp": "123"}, "WhatsApp inválido"),
    ({"usuario": "dono"}, "já existe"),  # usuário da Barbearia Exemplo
    ({"aceite": ""}, "aceite os termos"),
])
def test_cadastro_incompleto_nao_cria_nada(client_anonimo, extra, mensagem):
    antes = len(models.listar_barbearias())
    resposta = client_anonimo.post("/cadastro", data=_dados(**extra))
    assert resposta.status_code == 400
    assert mensagem in _texto(resposta)
    assert len(models.listar_barbearias()) == antes


def test_formulario_volta_preenchido_depois_do_erro(client_anonimo):
    html = _texto(client_anonimo.post("/cadastro", data=_dados(confirmacao="x")))
    assert 'value="Navalha do Bairro"' in html
    assert "senha-forte-1" not in html  # senha nunca volta para a tela


def test_robo_e_barrado(client_anonimo):
    antes = len(models.listar_barbearias())
    assert client_anonimo.post("/cadastro", data=_dados(site="spam")).status_code == 400
    assert len(models.listar_barbearias()) == antes


def test_limite_de_contas_por_aparelho(client_anonimo):
    for i in range(3):
        client_anonimo.post("/cadastro", data=_dados(usuario=f"dono{i}x", nome_barbearia=f"B {i}"))
        client_anonimo.post("/logout")
    resposta = client_anonimo.post("/cadastro", data=_dados(usuario="dono9x"))
    assert resposta.status_code == 429
    assert models.buscar_usuario_por_nome("dono9x") is None


def test_cadastro_fechado(client_anonimo, monkeypatch):
    monkeypatch.setenv("CADASTRO_ABERTO", "0")
    assert client_anonimo.get("/cadastro").status_code == 403
    assert client_anonimo.post("/cadastro", data=_dados()).status_code == 403
    assert models.buscar_usuario_por_nome("joao.silva") is None


def test_logado_vai_direto_para_a_agenda(client):
    resposta = client.get("/cadastro")
    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/agenda")


def test_termos(client_anonimo):
    assert "13.709/2018" in _texto(client_anonimo.get("/termos"))


def test_criar_barbearia_recusa_nome_ou_usuario_em_branco():
    with pytest.raises(ValueError):
        models.criar_barbearia_com_dono("  ", "alguem", "senha-forte")
    with pytest.raises(ValueError):
        models.criar_barbearia_com_dono("Barbearia", "  ", "senha-forte")


def test_nome_repetido_ganha_link_proprio(client_anonimo):
    client_anonimo.post("/cadastro", data=_dados(nome_barbearia="Barbearia Exemplo"))
    barbearia = models.buscar_barbearia(models.buscar_usuario_por_nome("joao.silva")["barbearia_id"])
    assert barbearia["slug"] == "barbearia-exemplo-2"
    assert publico.buscar_por_slug("barbearia-exemplo")["id"] != barbearia["id"]
