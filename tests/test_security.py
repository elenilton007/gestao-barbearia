"""
test_security.py

Testes de configuração de segurança: SECRET_KEY, modo debug e CSRF.
"""

import importlib
import re
import sys

import pytest


def _importar_app_limpo():
    sys.modules.pop("app", None)
    return importlib.import_module("app")


@pytest.fixture
def reimportar_app():
    """Reimporta o app com o ambiente atual e restaura o original depois."""
    original = sys.modules.get("app")
    yield _importar_app_limpo
    if original is not None:
        sys.modules["app"] = original
    else:
        sys.modules.pop("app", None)


def _csrf_token(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_sem_secret_key_falha_fora_do_debug(monkeypatch, reimportar_app):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        reimportar_app()


def test_sem_secret_key_gera_chave_temporaria_no_debug(monkeypatch, reimportar_app):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "1")
    modulo = reimportar_app()
    assert modulo.DEBUG is True
    assert len(modulo.app.config["SECRET_KEY"]) == 64


def test_secret_key_vem_do_ambiente_e_debug_desligado(monkeypatch, reimportar_app):
    monkeypatch.setenv("SECRET_KEY", "minha-chave")
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    modulo = reimportar_app()
    assert modulo.app.config["SECRET_KEY"] == "minha-chave"
    assert modulo.DEBUG is False


@pytest.mark.parametrize("rota", ["/clientes/novo", "/atendimentos/novo"])
def test_post_sem_token_csrf_e_rejeitado(client_csrf, rota):
    resposta = client_csrf.post(rota, data={"nome": "Sem Token"})
    assert resposta.status_code == 400


@pytest.mark.parametrize("pagina", ["/clientes", "/atendimentos"])
def test_formularios_incluem_token_csrf(client_csrf, pagina):
    html = client_csrf.get(pagina).get_data(as_text=True)
    assert 'name="csrf_token"' in html


def test_post_com_token_csrf_e_aceito(client_csrf):
    token = _csrf_token(client_csrf.get("/clientes").get_data(as_text=True))
    resposta = client_csrf.post(
        "/clientes/novo", data={"nome": "Com Token", "csrf_token": token}
    )
    assert resposta.status_code == 302
    assert "Com Token" in client_csrf.get("/clientes").get_data(as_text=True)
