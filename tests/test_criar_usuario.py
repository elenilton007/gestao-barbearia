"""
test_criar_usuario.py

Testes do script de linha de comando criar_usuario.py.
"""

import pytest

import criar_usuario
import database
import models
from database import get_connection


@pytest.fixture
def senhas(monkeypatch):
    """Simula o que é digitado nos prompts de senha."""
    def definir(*digitadas):
        respostas = iter(digitadas)
        monkeypatch.setattr(criar_usuario.getpass, "getpass", lambda _: next(respostas))
    return definir


def test_cria_dono(senhas):
    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "maria"]) == 0
    assert models.autenticar("maria", "senha-forte")["papel"] == "dono"


def test_cria_barbeiro(senhas):
    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["barbeiro", "elenilton", "--barbeiro-id", "1"]) == 0
    assert models.autenticar("elenilton", "senha-forte")["barbeiro_id"] == 1


def test_barbeiro_sem_id_lista_barbeiros(capsys):
    assert criar_usuario.main(["barbeiro", "fulano"]) == 1
    saida = capsys.readouterr().out
    assert "1: Elenilton Silveira" in saida
    assert "2: João Pereira" in saida


def test_senhas_diferentes(senhas, capsys):
    senhas("senha-forte", "outra-senha")
    assert criar_usuario.main(["dono", "maria"]) == 1
    assert "não conferem" in capsys.readouterr().out
    assert models.autenticar("maria", "senha-forte") is None


def test_senha_curta(senhas, capsys):
    senhas("curta", "curta")
    assert criar_usuario.main(["dono", "maria"]) == 1
    assert "pelo menos 8" in capsys.readouterr().out


def test_usuario_repetido(senhas, capsys):
    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "dono"]) == 1
    assert "Já existe" in capsys.readouterr().out


def test_cria_tabela_em_banco_antigo_sem_apagar_dados(senhas):
    # Simula um banco criado antes do login existir, já com dados.
    conn = get_connection()
    conn.execute("DROP TABLE usuarios")
    conn.commit()
    conn.close()
    models.criar_cliente("Cliente Antigo")

    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "maria"]) == 0
    assert models.autenticar("maria", "senha-forte") is not None
    assert "Cliente Antigo" in {c["nome"] for c in models.listar_clientes()}


def test_init_db_apaga_usuarios():
    database.init_db()
    assert models.autenticar("dono", "senha-do-dono") is None
