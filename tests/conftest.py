"""
conftest.py

Fixtures compartilhadas: cada teste roda em um banco SQLite temporário,
inicializado a partir do schema.sql (com os dados de exemplo), sem tocar
no barbearia.db real.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O app exige SECRET_KEY ao ser importado.
os.environ.setdefault("SECRET_KEY", "chave-de-teste")

import database


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Aponta a aplicação para um banco novo a cada teste."""
    monkeypatch.setenv("BARBEARIA_DB", str(tmp_path / "teste.db"))
    database.init_db()
    yield


@pytest.fixture
def client():
    """Cliente de teste do Flask, com CSRF desligado."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client
    app.config["WTF_CSRF_ENABLED"] = True


@pytest.fixture
def client_csrf():
    """Cliente de teste do Flask com a proteção CSRF ativa."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = True
    with app.test_client() as client:
        yield client
