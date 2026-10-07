"""
test_login_seguranca.py

Testes do limite de tentativas no login, da troca de senha pelo dono e da
expiração da sessão por inatividade.
"""

import time

import pytest

import database
import models
from conftest import ID_DONO, logar
from database import get_connection

LIMITE = models.MAXIMO_TENTATIVAS_LOGIN
BLOQUEIO = models.TEMPO_BLOQUEIO_LOGIN


@pytest.fixture
def relogio(monkeypatch):
    """Relógio controlado pelo teste para o limite de tentativas."""
    class Relogio:
        agora = 1_000_000.0

        def avancar(self, segundos):
            self.agora += segundos

    r = Relogio()
    monkeypatch.setattr(models, "_agora", lambda: r.agora)
    return r


def _entrar(client, usuario="dono", senha="senha-do-dono"):
    return client.post("/login", data={"usuario": usuario, "senha": senha})


def _errar(client, vezes, usuario="dono"):
    for _ in range(vezes):
        resposta = _entrar(client, usuario, "senha-errada")
    return resposta


# ---------- LIMITE DE TENTATIVAS ----------

def test_erros_antes_do_limite_ainda_deixam_entrar(client_anonimo, relogio):
    resposta = _errar(client_anonimo, LIMITE - 1)
    assert resposta.status_code == 401
    assert "Usuário ou senha inválidos." in resposta.get_data(as_text=True)

    assert _entrar(client_anonimo).status_code == 302


def test_quinto_erro_bloqueia(client_anonimo, relogio):
    resposta = _errar(client_anonimo, LIMITE)
    assert resposta.status_code == 429
    assert "Tente de novo em 15 minutos." in resposta.get_data(as_text=True)


def test_bloqueado_nao_entra_nem_com_a_senha_certa(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE)
    resposta = _entrar(client_anonimo)
    assert resposta.status_code == 429
    with client_anonimo.session_transaction() as sessao:
        assert "usuario_id" not in sessao


def test_bloqueado_nao_confere_a_senha(client_anonimo, relogio, monkeypatch):
    _errar(client_anonimo, LIMITE)
    monkeypatch.setattr(models, "autenticar", lambda *a: pytest.fail("conferiu a senha"))
    assert _entrar(client_anonimo).status_code == 429


def test_mensagem_mostra_o_tempo_que_falta(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE)
    relogio.avancar(BLOQUEIO - 50)
    html = _entrar(client_anonimo).get_data(as_text=True)
    assert "Tente de novo em 1 minuto." in html


def test_bloqueio_acaba_depois_de_15_minutos(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE)
    relogio.avancar(BLOQUEIO - 1)
    assert _entrar(client_anonimo).status_code == 429
    relogio.avancar(1)
    assert _entrar(client_anonimo).status_code == 302


def test_depois_do_bloqueio_a_contagem_recomeca(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE)
    relogio.avancar(BLOQUEIO)
    assert _errar(client_anonimo, 1).status_code == 401
    assert _errar(client_anonimo, LIMITE - 2).status_code == 401
    assert _errar(client_anonimo, 1).status_code == 429


def test_login_certo_zera_a_contagem(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE - 1)
    _entrar(client_anonimo)
    client_anonimo.post("/logout")
    assert _errar(client_anonimo, LIMITE - 1).status_code == 401


def test_erros_antigos_deixam_de_contar(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE - 1)
    relogio.avancar(BLOQUEIO + 1)
    assert _errar(client_anonimo, 1).status_code == 401


def test_bloqueio_vale_so_para_o_usuario_errado(client_anonimo, relogio):
    _errar(client_anonimo, LIMITE, usuario="joao")
    assert _entrar(client_anonimo).status_code == 302  # dono continua entrando


def test_usuario_inexistente_tambem_e_bloqueado(client_anonimo, relogio):
    """Mesma resposta que um usuário real: o bloqueio não revela quem existe."""
    assert _errar(client_anonimo, LIMITE - 1, usuario="fantasma").status_code == 401
    assert _errar(client_anonimo, 1, usuario="fantasma").status_code == 429


def test_banco_antigo_ganha_a_tabela_de_tentativas(client_anonimo, relogio):
    conn = get_connection()
    conn.execute("DROP TABLE tentativas_login")
    conn.commit()
    conn.close()

    database.atualizar_banco()
    assert _errar(client_anonimo, LIMITE).status_code == 429


# ---------- TROCA DE SENHA ----------

def _trocar(client, atual="senha-do-dono", nova="senha-nova-123", confirmacao=None):
    return client.post(
        "/senha",
        data={
            "senha_atual": atual,
            "nova_senha": nova,
            "confirmacao": nova if confirmacao is None else confirmacao,
        },
    )


def test_tela_de_troca_de_senha_carrega(client):
    resposta = client.get("/senha")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'name="senha_atual"' in html
    assert 'name="nova_senha"' in html
    assert 'name="confirmacao"' in html


def test_menu_do_dono_tem_trocar_senha(client):
    assert "Trocar senha" in client.get("/").get_data(as_text=True)


def test_dono_troca_a_propria_senha(client):
    resposta = _trocar(client)
    assert resposta.status_code == 302
    assert "Senha alterada." in client.get("/").get_data(as_text=True)
    assert models.autenticar("dono", "senha-do-dono") is None
    assert models.autenticar("dono", "senha-nova-123")["id"] == ID_DONO


def test_dono_entra_com_a_senha_nova(client):
    _trocar(client)
    client.post("/logout")
    assert _entrar(client, senha="senha-do-dono").status_code == 401
    assert _entrar(client, senha="senha-nova-123").status_code == 302


def test_troca_so_muda_a_senha_do_proprio_dono(client):
    _trocar(client)
    assert models.autenticar("joao", "senha-do-joao") is not None


@pytest.mark.parametrize(
    "dados, mensagem",
    [
        ({"atual": "senha-errada"}, "A senha atual está incorreta."),
        ({"nova": "curta"}, "pelo menos 8 caracteres"),
        ({"confirmacao": "outra-senha-123"}, "A confirmação não é igual à nova senha."),
        ({"nova": "senha-do-dono"}, "diferente da atual"),
    ],
)
def test_troca_de_senha_recusada(client, dados, mensagem):
    resposta = _trocar(client, **dados)
    assert resposta.status_code == 400
    assert mensagem in resposta.get_data(as_text=True)
    assert models.autenticar("dono", "senha-do-dono") is not None


def test_barbeiro_nao_acessa_troca_de_senha(client_barbeiro):
    assert client_barbeiro.get("/senha").status_code == 403
    assert _trocar(client_barbeiro, atual="senha-do-joao").status_code == 403
    assert models.autenticar("joao", "senha-do-joao") is not None
    assert "Trocar senha" not in client_barbeiro.get("/").get_data(as_text=True)


def test_troca_de_senha_exige_login(client_anonimo):
    resposta = client_anonimo.get("/senha")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")


def test_troca_de_senha_exige_token_csrf(client_csrf):
    assert _trocar(client_csrf).status_code == 400
    assert models.autenticar("dono", "senha-do-dono") is not None


# ---------- EXPIRAÇÃO DA SESSÃO ----------

def _parar_por(client, minutos):
    with client.session_transaction() as sessao:
        sessao["ultimo_acesso"] = int(time.time() - minutos * 60)


def test_sessao_parada_expira(client):
    _parar_por(client, 31)
    resposta = client.get("/clientes")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")
    with client.session_transaction() as sessao:
        assert "usuario_id" not in sessao


def test_aviso_de_sessao_expirada(client):
    _parar_por(client, 31)
    html = client.get("/clientes", follow_redirects=True).get_data(as_text=True)
    assert "Sua sessão expirou por inatividade." in html
    assert 'name="senha"' in html


def test_sessao_expirada_nao_grava_nada(client):
    _parar_por(client, 31)
    resposta = client.post("/clientes/novo", data={"nome": "Depois do Prazo"})
    assert resposta.status_code == 302
    assert "Depois do Prazo" not in {c["nome"] for c in models.listar_clientes(1)}


def test_sessao_usada_antes_do_limite_continua(client):
    _parar_por(client, 29)
    assert client.get("/clientes").status_code == 200


def test_cada_acesso_renova_o_prazo(client):
    _parar_por(client, 29)
    client.get("/clientes")
    with client.session_transaction() as sessao:
        assert time.time() - sessao["ultimo_acesso"] < 5


def test_sessao_sem_hora_do_ultimo_acesso_expira(client_anonimo):
    with client_anonimo.session_transaction() as sessao:
        sessao["usuario_id"] = ID_DONO  # cookie de antes desta regra
    assert client_anonimo.get("/clientes").status_code == 302


def test_login_marca_o_ultimo_acesso(client_anonimo):
    _entrar(client_anonimo)
    with client_anonimo.session_transaction() as sessao:
        assert time.time() - sessao["ultimo_acesso"] < 5
    assert client_anonimo.get("/clientes").status_code == 200


def test_limite_de_inatividade_configuravel(client):
    from app import app

    app.config["SESSAO_INATIVIDADE_MINUTOS"] = 5
    try:
        _parar_por(client, 6)
        assert client.get("/clientes").status_code == 302
        logar(client, ID_DONO)
        _parar_por(client, 4)
        assert client.get("/clientes").status_code == 200
    finally:
        app.config["SESSAO_INATIVIDADE_MINUTOS"] = 30
