"""
conftest.py

Fixtures compartilhadas: cada teste roda em um banco SQLite temporário,
inicializado a partir do schema.sql (com os dados de exemplo), sem tocar
no barbearia.db real.

Usuários criados em todo teste:
  dono  / senha-do-dono   (papel dono)
  joao  / senha-do-joao   (papel barbeiro, barbeiro_id 2 = João Pereira)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O app exige SECRET_KEY ao ser importado.
os.environ.setdefault("SECRET_KEY", "chave-de-teste")

import database
import models

ID_DONO = 1
ID_USUARIO_JOAO = 2
BARBEIRO_JOAO = 2


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Aponta a aplicação para um banco novo a cada teste."""
    monkeypatch.setenv("BARBEARIA_DB", str(tmp_path / "teste.db"))
    database.init_db()
    models.criar_usuario("dono", "senha-do-dono", "dono")
    models.criar_usuario("joao", "senha-do-joao", "barbeiro", BARBEIRO_JOAO)
    yield


def _logar(client, usuario_id):
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = usuario_id


@pytest.fixture
def client_anonimo():
    """Cliente de teste do Flask sem login, com CSRF desligado."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client
    app.config["WTF_CSRF_ENABLED"] = True


@pytest.fixture
def client(client_anonimo):
    """Cliente de teste logado como dono, com CSRF desligado."""
    _logar(client_anonimo, ID_DONO)
    return client_anonimo


@pytest.fixture
def client_barbeiro(client_anonimo):
    """Cliente de teste logado como o barbeiro João, com CSRF desligado."""
    _logar(client_anonimo, ID_USUARIO_JOAO)
    return client_anonimo


@pytest.fixture
def client_csrf():
    """Cliente de teste logado como dono, com a proteção CSRF ativa."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = True
    with app.test_client() as client:
        _logar(client, ID_DONO)
        yield client
