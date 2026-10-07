"""
test_criar_usuario.py

Testes do script de linha de comando criar_usuario.py.
"""

import pytest

import criar_usuario
import database
import models
from conftest import BARBEARIA
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
    models.criar_cliente(BARBEARIA, "Cliente Antigo")

    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "maria"]) == 0
    assert models.autenticar("maria", "senha-forte") is not None
    assert "Cliente Antigo" in {c["nome"] for c in models.listar_clientes(BARBEARIA)}


def test_init_db_apaga_usuarios():
    database.init_db()
    assert models.autenticar("dono", "senha-do-dono") is None


# ---------- BARBEARIAS ----------

def test_cria_dono_com_barbearia_nova(senhas, capsys):
    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "maria", "--nova-barbearia", "Barbearia da Maria"]) == 0
    assert "Barbearia da Maria" in capsys.readouterr().out
    maria = models.autenticar("maria", "senha-forte")
    assert models.buscar_barbearia(maria["barbearia_id"])["nome"] == "Barbearia da Maria"
    assert models.listar_clientes(maria["barbearia_id"]) == []


def test_barbeiro_nao_cria_barbearia_nova(capsys):
    assert criar_usuario.main(["barbeiro", "pedro", "--nova-barbearia", "X"]) == 1
    assert "Só o dono" in capsys.readouterr().out
    assert len(models.listar_barbearias()) == 1


def test_com_duas_barbearias_pede_barbearia_id(outra_barbearia, capsys):
    assert criar_usuario.main(["dono", "maria"]) == 1
    saida = capsys.readouterr().out
    assert "1: Barbearia Exemplo" in saida
    assert f"{outra_barbearia.id}: Navalha de Ouro" in saida


def test_cria_usuario_na_barbearia_informada(outra_barbearia, senhas):
    senhas("senha-forte", "senha-forte")
    argv = ["barbeiro", "pedro", "--barbearia-id", str(outra_barbearia.id),
            "--barbeiro-id", str(outra_barbearia.barbeiro_id)]
    assert criar_usuario.main(argv) == 0
    assert models.autenticar("pedro", "senha-forte")["barbearia_id"] == outra_barbearia.id


def test_lista_so_barbeiros_da_barbearia_informada(outra_barbearia, capsys):
    argv = ["barbeiro", "pedro", "--barbearia-id", str(outra_barbearia.id)]
    assert criar_usuario.main(argv) == 1
    saida = capsys.readouterr().out
    assert "Marcos Tesoura" in saida
    assert "João Pereira" not in saida


def test_barbeiro_de_outra_barbearia_e_recusado(outra_barbearia, senhas, capsys):
    senhas("senha-forte", "senha-forte")
    argv = ["barbeiro", "pedro", "--barbearia-id", "1",
            "--barbeiro-id", str(outra_barbearia.barbeiro_id)]
    assert criar_usuario.main(argv) == 1
    assert "não existe nesta barbearia" in capsys.readouterr().out


def test_barbearia_inexistente(senhas, capsys):
    senhas("senha-forte", "senha-forte")
    assert criar_usuario.main(["dono", "maria", "--barbearia-id", "99"]) == 1
    assert "Barbearia 99 não existe" in capsys.readouterr().out
