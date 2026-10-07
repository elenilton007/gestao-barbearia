"""
conftest.py

Fixtures compartilhadas: cada teste roda em um banco SQLite temporário,
inicializado a partir do schema.sql (com os dados de exemplo), sem tocar
no barbearia.db real.

Com a variável TEST_DATABASE_URL, os testes rodam no PostgreSQL desse
endereço. Atenção: o banco é apagado e recriado a cada teste, então use
um banco só para os testes. A DATABASE_URL do ambiente é sempre ignorada,
para os testes nunca apagarem o banco de produção.

Usuários criados em todo teste, na barbearia 1 (Barbearia Exemplo):
  dono  / senha-do-dono   (papel dono)
  joao  / senha-do-joao   (papel barbeiro, barbeiro_id 2 = João Pereira)

A fixture outra_barbearia cria uma segunda barbearia, com dados próprios,
para os testes que conferem que uma barbearia não vê os dados da outra.
"""

import os
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O app exige SECRET_KEY ao ser importado.
os.environ.setdefault("SECRET_KEY", "chave-de-teste")

import database
import models

BARBEARIA = 1
ID_DONO = 1
ID_USUARIO_JOAO = 2
BARBEIRO_JOAO = 2


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Aponta a aplicação para um banco novo a cada teste."""
    monkeypatch.setenv("BARBEARIA_DB", str(tmp_path / "teste.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if os.environ.get("TEST_DATABASE_URL"):
        monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    database.init_db()
    models.criar_usuario(BARBEARIA, "dono", "senha-do-dono", "dono")
    models.criar_usuario(BARBEARIA, "joao", "senha-do-joao", "barbeiro", BARBEIRO_JOAO)
    yield


@pytest.fixture
def outra_barbearia():
    """
    Segunda barbearia, com um dono, um barbeiro (também com login), um
    serviço, um cliente e um atendimento de R$ 123,45 — nomes e valores
    que não existem na Barbearia Exemplo.
    """
    barbearia_id = models.criar_barbearia_com_dono(
        "Navalha de Ouro", "dona-ouro", "senha-da-dona"
    )
    barbeiro_id = models.criar_barbeiro(barbearia_id, "Marcos Tesoura", 30.0)
    servico_id = models.criar_servico(barbearia_id, "Pigmentação", 123.45)
    models.criar_cliente(barbearia_id, "Diego Ramos", "(11) 95555-0000")
    (cliente,) = models.listar_clientes(barbearia_id)
    models.criar_atendimento(barbearia_id, cliente["id"], barbeiro_id, servico_id, 123.45)
    models.criar_usuario(barbearia_id, "marcos", "senha-do-marcos", "barbeiro", barbeiro_id)
    return SimpleNamespace(
        id=barbearia_id,
        cliente_id=cliente["id"],
        barbeiro_id=barbeiro_id,
        servico_id=servico_id,
        id_dono=models.autenticar("dona-ouro", "senha-da-dona")["id"],
        id_barbeiro=models.autenticar("marcos", "senha-do-marcos")["id"],
    )


def logar(client, usuario_id):
    """Abre a sessão como o app faz no login certo (veja app._iniciar_sessao)."""
    from app import _marca_da_senha

    with client.session_transaction() as sessao:
        sessao["usuario_id"] = usuario_id
        sessao["senha"] = _marca_da_senha(models.buscar_usuario(usuario_id))
        sessao["ultimo_acesso"] = time.time()


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
    logar(client_anonimo, ID_DONO)
    return client_anonimo


@pytest.fixture
def client_barbeiro(client_anonimo):
    """Cliente de teste logado como o barbeiro João, com CSRF desligado."""
    logar(client_anonimo, ID_USUARIO_JOAO)
    return client_anonimo


@pytest.fixture
def client_csrf():
    """Cliente de teste logado como dono, com a proteção CSRF ativa."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = True
    with app.test_client() as client:
        logar(client, ID_DONO)
        yield client
