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

import database


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Aponta a aplicação para um banco novo a cada teste."""
    monkeypatch.setenv("BARBEARIA_DB", str(tmp_path / "teste.db"))
    database.init_db()
    yield


@pytest.fixture
def client():
    """Cliente de teste do Flask."""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
