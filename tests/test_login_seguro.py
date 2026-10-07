"""
test_login_seguro.py

Testes do limite de tentativas no login, da troca de senha pelo dono e da
expiração da sessão por inatividade.
"""

import time

import pytest

import models
from conftest import ID_DONO, logar


def _entrar(client, usuario="dono", senha="senha-do-dono"):
    return client.post("/login", data={"usuario": usuario, "senha": senha})


def _errar(client, vezes, usuario="dono"):
    for _ in range(vezes):
        resposta = _entrar(client, usuario, "senha-errada")
    return resposta


@pytest.fixture
def relogio(monkeypatch):
    """Relógio falso do models: relogio.avancar(segundos) adianta o tempo."""
    class Relogio:
        agora = 1_000_000.0

        def avancar(self, segundos):
            self.agora += segundos

    r = Relogio()
    monkeypatch.setattr(models, "_agora", lambda: r.agora)
    return r


# ---------- LIMITE DE TENTATIVAS ----------

def test_quatro_erros_ainda_deixam_entrar(client_anonimo):
    assert _errar(client_anonimo, 4).status_code == 401
    assert _entrar(client_anonimo).status_code == 302


def test_login_certo_zera_a_contagem(client_anonimo):
    _errar(client_anonimo, 4)
    _entrar(client_anonimo)
    client_anonimo.post("/logout")
    assert _errar(client_anonimo, 4).status_code == 401
    assert _entrar(client_anonimo).status_code == 302


def test_quinto_erro_bloqueia(client_anonimo):
    resposta = _errar(client_anonimo, 5)
    assert resposta.status_code == 429
    assert "Tente de novo em 15 minutos" in resposta.get_data(as_text=True)


def test_bloqueado_nem_a_senha_certa_entra(client_anonimo):
    _errar(client_anonimo, 5)
    resposta = _entrar(client_anonimo)
    assert resposta.status_code == 429
    assert "Muitas tentativas" in resposta.get_data(as_text=True)
    assert client_anonimo.get("/").status_code == 302


def test_bloqueio_e_so_do_usuario_errado(client_anonimo):
    _errar(client_anonimo, 5)
    assert _entrar(client_anonimo, "joao", "senha-do-joao").status_code == 302


def test_usuario_que_nao_existe_tambem_e_bloqueado(client_anonimo):
    # Mesmo comportamento de um usuário real: não revela quem existe.
    assert _errar(client_anonimo, 5, "ninguem").status_code == 429


def test_bloqueio_acaba_depois_de_15_minutos(client_anonimo, relogio):
    _errar(client_anonimo, 5)
    relogio.avancar(14 * 60)
    resposta = _entrar(client_anonimo)
    assert resposta.status_code == 429
    assert "Tente de novo em 1 minuto." in resposta.get_data(as_text=True)
    relogio.avancar(60)
    assert _entrar(client_anonimo).status_code == 302


def test_depois_do_bloqueio_a_contagem_recomeca(relogio):
    for _ in range(5):
        models.registrar_falha_login("dono")
    relogio.avancar(models.TEMPO_BLOQUEIO_LOGIN)
    assert models.segundos_de_bloqueio("dono") == 0
    models.registrar_falha_login("dono")
    assert models.segundos_de_bloqueio("dono") == 0  # 1 erro só, não 6
    for _ in range(4):
        models.registrar_falha_login("dono")
    assert models.segundos_de_bloqueio("dono") == models.TEMPO_BLOQUEIO_LOGIN


# ---------- TROCA DE SENHA ----------

def _trocar(client, atual="senha-do-dono", nova="senha-nova-123", confirmacao=None):
    return client.post(
        "/conta/senha",
        data={
            "senha_atual": atual,
            "nova_senha": nova,
            "confirmacao": nova if confirmacao is None else confirmacao,
        },
    )


def test_tela_de_troca_de_senha_carrega(client):
    resposta = client.get("/conta/senha")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert 'name="senha_atual"' in html
    assert 'name="nova_senha"' in html
    assert 'name="confirmacao"' in html
    assert "Trocar senha" in client.get("/").get_data(as_text=True)  # no menu


def test_troca_de_senha_exige_login(client_anonimo):
    resposta = client_anonimo.get("/conta/senha")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")


def test_barbeiro_nao_acessa_troca_de_senha(client_barbeiro):
    assert client_barbeiro.get("/conta/senha").status_code == 403
    assert _trocar(client_barbeiro, "senha-do-joao").status_code == 403
    assert "Trocar senha" not in client_barbeiro.get("/").get_data(as_text=True)


def test_troca_de_senha_certa(client):
    resposta = _trocar(client)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    assert "Senha alterada" in client.get("/").get_data(as_text=True)  # segue logado
    assert models.autenticar("dono", "senha-do-dono") is None
    assert models.autenticar("dono", "senha-nova-123") is not None


@pytest.mark.parametrize(
    "atual, nova, confirmacao, mensagem",
    [
        ("senha-errada", "senha-nova-123", None, "senha atual está errada"),
        ("senha-do-dono", "curta", None, "pelo menos 8"),
        ("senha-do-dono", "senha-nova-123", "outra-senha-1", "confirmação não é igual"),
        ("senha-do-dono", "senha-do-dono", None, "diferente da atual"),
    ],
)
def test_troca_de_senha_recusada(client, atual, nova, confirmacao, mensagem):
    resposta = _trocar(client, atual, nova, confirmacao)
    assert resposta.status_code == 400
    assert mensagem in resposta.get_data(as_text=True)
    assert models.autenticar("dono", "senha-do-dono") is not None


def test_troca_de_senha_encerra_as_outras_sessoes(client):
    from app import app

    outro_aparelho = app.test_client()
    logar(outro_aparelho, ID_DONO)
    assert outro_aparelho.get("/").status_code == 200
    _trocar(client)
    assert outro_aparelho.get("/").status_code == 302
    assert client.get("/").status_code == 200


def test_troca_de_senha_sem_token_csrf_e_rejeitada(client_csrf):
    assert _trocar(client_csrf).status_code == 400
    assert models.autenticar("dono", "senha-do-dono") is not None


# ---------- EXPIRAÇÃO POR INATIVIDADE ----------

def _parado_ha(client, segundos):
    with client.session_transaction() as sessao:
        sessao["ultimo_acesso"] = time.time() - segundos


def test_tempo_de_inatividade_padrao_e_30_minutos():
    from app import app

    assert app.config["TEMPO_INATIVIDADE"] == 30 * 60


def test_sessao_parada_ha_mais_de_30_minutos_expira(client):
    _parado_ha(client, 31 * 60)
    resposta = client.get("/")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/login")
    assert "expirou por inatividade" in client.get("/login").get_data(as_text=True)
    assert client.get("/").status_code == 302  # não volta sozinha


def test_sessao_em_uso_nao_expira(client):
    _parado_ha(client, 29 * 60)
    assert client.get("/").status_code == 200
    with client.session_transaction() as sessao:
        assert time.time() - sessao["ultimo_acesso"] < 60  # renovada


def test_post_com_sessao_expirada_nao_grava(client):
    _parado_ha(client, 31 * 60)
    resposta = client.post("/clientes/novo", data={"nome": "Depois do Prazo"})
    assert resposta.status_code == 302
    assert "Depois do Prazo" not in {c["nome"] for c in models.listar_clientes(1)}


def test_sessao_sem_marca_da_senha_vira_anonima(client_anonimo):
    # Cookie antigo, de antes desta versão: só tinha o usuario_id.
    with client_anonimo.session_transaction() as sessao:
        sessao["usuario_id"] = ID_DONO
        sessao["ultimo_acesso"] = time.time()
    assert client_anonimo.get("/").status_code == 302
