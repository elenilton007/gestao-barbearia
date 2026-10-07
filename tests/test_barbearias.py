"""
test_barbearias.py

Testes da separação dos dados por barbearia: cada barbearia só vê e só
altera os próprios clientes, barbeiros, serviços, atendimentos e relatórios.

A Barbearia Exemplo (id 1) vem do schema.sql; a Navalha de Ouro vem da
fixture outra_barbearia (veja conftest.py).
"""

import pytest

import database
import models
import reports
from conftest import BARBEARIA, BARBEIRO_JOAO, ID_DONO, ID_USUARIO_JOAO, logar
from database import get_connection

DADOS_DA_EXEMPLO = ["Carlos Souza", "Elenilton Silveira", "João Pereira", "Corte Masculino"]
DADOS_DA_OURO = ["Diego Ramos", "Marcos Tesoura", "Pigmentação", "123.45"]


def _html(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


# ---------- MODELS / REPORTS ----------

def test_listagens_trazem_so_a_propria_barbearia(outra_barbearia):
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00)

    assert {c["nome"] for c in models.listar_clientes(BARBEARIA)} == {
        "Carlos Souza", "Rafael Lima", "Bruno Andrade"
    }
    assert {b["nome"] for b in models.listar_barbeiros(BARBEARIA)} == {
        "Elenilton Silveira", "João Pereira"
    }
    assert len(models.listar_servicos(BARBEARIA)) == 5
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["cliente"] == "Carlos Souza"

    ouro = outra_barbearia.id
    assert [c["nome"] for c in models.listar_clientes(ouro)] == ["Diego Ramos"]
    assert [b["nome"] for b in models.listar_barbeiros(ouro)] == ["Marcos Tesoura"]
    assert [s["nome"] for s in models.listar_servicos(ouro)] == ["Pigmentação"]
    (atendimento,) = models.listar_atendimentos(ouro)
    assert atendimento["cliente"] == "Diego Ramos"


def test_relatorios_somam_so_a_propria_barbearia(outra_barbearia):
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00)

    assert reports.faturamento_total(BARBEARIA) == pytest.approx(35.00)
    assert reports.faturamento_total(outra_barbearia.id) == pytest.approx(123.45)

    assert {c["barbeiro"] for c in reports.comissoes_por_barbeiro(BARBEARIA)} == {
        "Elenilton Silveira", "João Pereira"
    }
    (comissao,) = reports.comissoes_por_barbeiro(outra_barbearia.id)
    assert comissao["barbeiro"] == "Marcos Tesoura"
    assert comissao["total_faturado"] == pytest.approx(123.45)

    assert "Pigmentação" not in {
        s["servico"] for s in reports.servicos_mais_vendidos(BARBEARIA)
    }
    (servico,) = reports.servicos_mais_vendidos(outra_barbearia.id)
    assert servico["quantidade"] == 1


def test_barbeiro_de_outra_barbearia_nao_e_encontrado(outra_barbearia):
    assert models.buscar_barbeiro(BARBEARIA, outra_barbearia.barbeiro_id) is None
    assert models.buscar_barbeiro(outra_barbearia.id, 1) is None
    assert reports.comissoes_por_barbeiro(BARBEARIA, outra_barbearia.barbeiro_id) == []


@pytest.mark.parametrize("campo", ["cliente_id", "barbeiro_id", "servico_id"])
def test_atendimento_com_dado_de_outra_barbearia_e_recusado(outra_barbearia, campo):
    ids = {"cliente_id": 1, "barbeiro_id": 1, "servico_id": 1}
    ids[campo] = getattr(outra_barbearia, campo)
    with pytest.raises(ValueError, match="não existe nesta barbearia"):
        models.criar_atendimento(
            BARBEARIA, ids["cliente_id"], ids["barbeiro_id"], ids["servico_id"], 10.00
        )
    assert models.listar_atendimentos(BARBEARIA) == []


def test_usuario_barbeiro_de_outra_barbearia_e_recusado(outra_barbearia):
    with pytest.raises(ValueError, match="não existe nesta barbearia"):
        models.criar_usuario(
            BARBEARIA, "intruso", "senha-forte", "barbeiro", outra_barbearia.barbeiro_id
        )


def test_usuario_em_barbearia_inexistente_e_recusado():
    with pytest.raises(ValueError, match="Barbearia 99 não existe"):
        models.criar_usuario(99, "fantasma", "senha-forte", "dono")


def test_barbearia_nova_nao_e_criada_se_o_dono_falhar():

    with pytest.raises(database.IntegrityError):
        models.criar_barbearia_com_dono("Repetida", "dono", "senha-forte")
    with pytest.raises(ValueError, match="pelo menos 8"):
        models.criar_barbearia_com_dono("Senha Curta", "novo-dono", "curta")
    assert [b["nome"] for b in models.listar_barbearias()] == ["Barbearia Exemplo"]


# ---------- ROTAS ----------

@pytest.mark.parametrize("rota", ["/", "/clientes", "/atendimentos", "/relatorios"])
def test_dono_nao_ve_dados_da_outra_barbearia(client, outra_barbearia, rota):
    html = _html(client, rota)
    for dado in DADOS_DA_OURO:
        assert dado not in html


@pytest.mark.parametrize("rota", ["/", "/clientes", "/atendimentos", "/relatorios"])
def test_dono_da_outra_barbearia_nao_ve_dados_da_primeira(
    client_anonimo, outra_barbearia, rota
):
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00)
    logar(client_anonimo, outra_barbearia.id_dono)
    html = _html(client_anonimo, rota)
    for dado in DADOS_DA_EXEMPLO:
        assert dado not in html
    assert "R$ 35.00" not in html


def test_dono_da_outra_barbearia_ve_os_proprios_dados(client_anonimo, outra_barbearia):
    logar(client_anonimo, outra_barbearia.id_dono)
    html = _html(client_anonimo, "/")
    assert "Navalha de Ouro" in html  # nome da barbearia no menu
    assert "Marcos Tesoura" in html
    assert "R$ 123.45" in html
    assert "Diego Ramos" in _html(client_anonimo, "/clientes")


@pytest.mark.parametrize("rota", ["/", "/clientes", "/atendimentos"])
def test_barbeiro_nao_ve_dados_da_outra_barbearia(client_barbeiro, outra_barbearia, rota):
    html = _html(client_barbeiro, rota)
    for dado in DADOS_DA_OURO:
        assert dado not in html


@pytest.mark.parametrize("rota", ["/", "/clientes", "/atendimentos"])
def test_barbeiro_da_outra_barbearia_nao_ve_dados_da_primeira(
    client_anonimo, outra_barbearia, rota
):
    logar(client_anonimo, outra_barbearia.id_barbeiro)
    html = _html(client_anonimo, rota)
    for dado in DADOS_DA_EXEMPLO:
        assert dado not in html


def test_cliente_cadastrado_fica_so_na_barbearia_de_quem_cadastrou(
    client_anonimo, outra_barbearia
):
    logar(client_anonimo, outra_barbearia.id_dono)
    client_anonimo.post("/clientes/novo", data={"nome": "Cliente da Ouro"})
    assert "Cliente da Ouro" in {c["nome"] for c in models.listar_clientes(outra_barbearia.id)}
    assert "Cliente da Ouro" not in {c["nome"] for c in models.listar_clientes(BARBEARIA)}

    logar(client_anonimo, ID_DONO)
    assert "Cliente da Ouro" not in _html(client_anonimo, "/clientes")


@pytest.mark.parametrize("campo", ["cliente_id", "barbeiro_id", "servico_id"])
def test_dono_nao_registra_atendimento_com_dado_de_outra_barbearia(
    client, outra_barbearia, campo
):
    dados = {"cliente_id": "1", "barbeiro_id": "1", "servico_id": "1",
             "valor_cobrado": "35.00"}
    dados[campo] = str(getattr(outra_barbearia, campo))
    resposta = client.post("/atendimentos/novo", data=dados)
    assert resposta.status_code == 400
    assert models.listar_atendimentos(BARBEARIA) == []
    assert len(models.listar_atendimentos(outra_barbearia.id)) == 1


def test_barbeiro_nao_registra_atendimento_com_servico_de_outra_barbearia(
    client_barbeiro, outra_barbearia
):
    resposta = client_barbeiro.post(
        "/atendimentos/novo",
        data={"cliente_id": "1", "servico_id": str(outra_barbearia.servico_id),
              "valor_cobrado": "35.00"},
    )
    assert resposta.status_code == 400
    assert models.listar_atendimentos(BARBEARIA, BARBEIRO_JOAO) == []


def test_menu_mostra_a_barbearia_do_usuario(client_anonimo):
    logar(client_anonimo, ID_USUARIO_JOAO)
    assert "Barbearia Exemplo" in _html(client_anonimo, "/")


# ---------- BANCO ANTIGO ----------

SCHEMA_ANTIGO = """
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS atendimentos;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS servicos;
DROP TABLE IF EXISTS barbeiros;
DROP TABLE IF EXISTS barbearias;
CREATE TABLE clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
    telefone TEXT, criado_em TEXT DEFAULT (datetime('now')));
CREATE TABLE barbeiros (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
    comissao_percentual REAL NOT NULL DEFAULT 40.0);
CREATE TABLE servicos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
    preco REAL NOT NULL, duracao_minutos INTEGER NOT NULL DEFAULT 30);
CREATE TABLE atendimentos (id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL, barbeiro_id INTEGER NOT NULL,
    servico_id INTEGER NOT NULL, data_hora TEXT NOT NULL DEFAULT (datetime('now')),
    valor_cobrado REAL NOT NULL, forma_pagamento TEXT NOT NULL DEFAULT 'dinheiro');
CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE, senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'barbeiro')), barbeiro_id INTEGER,
    criado_em TEXT DEFAULT (datetime('now')));
INSERT INTO clientes (nome) VALUES ('Cliente Antigo');
INSERT INTO barbeiros (nome, comissao_percentual) VALUES ('Barbeiro Antigo', 50.0);
INSERT INTO servicos (nome, preco) VALUES ('Corte Antigo', 30.0);
INSERT INTO atendimentos (cliente_id, barbeiro_id, servico_id, valor_cobrado)
    VALUES (1, 1, 1, 30.0);
"""


@pytest.fixture
def banco_antigo():
    """Banco criado antes da separação por barbearia, já com dados e um dono."""
    from werkzeug.security import generate_password_hash

    conn = get_connection()
    conn.executescript(SCHEMA_ANTIGO)
    conn.execute(
        "INSERT INTO usuarios (usuario, senha_hash, papel) VALUES ('antigo', ?, 'dono')",
        (generate_password_hash("senha-antiga"),),
    )
    conn.commit()
    conn.close()


def test_atualizar_banco_antigo_mantem_os_dados_numa_barbearia(banco_antigo):
    database.atualizar_banco()

    (barbearia,) = models.listar_barbearias()
    assert barbearia["nome"] == "Minha Barbearia"
    assert [c["nome"] for c in models.listar_clientes(barbearia["id"])] == ["Cliente Antigo"]
    (atendimento,) = models.listar_atendimentos(barbearia["id"])
    assert atendimento["barbeiro"] == "Barbeiro Antigo"
    assert reports.faturamento_total(barbearia["id"]) == pytest.approx(30.0)
    assert models.autenticar("antigo", "senha-antiga")["barbearia_id"] == barbearia["id"]


def test_atualizar_banco_pode_rodar_de_novo(banco_antigo):
    database.atualizar_banco()
    database.atualizar_banco()
    assert len(models.listar_barbearias()) == 1
    assert len(models.listar_clientes(1)) == 1


def test_dono_do_banco_antigo_entra_e_ve_os_dados(client_anonimo, banco_antigo):
    database.atualizar_banco()
    client_anonimo.post("/login", data={"usuario": "antigo", "senha": "senha-antiga"})
    assert "Cliente Antigo" in _html(client_anonimo, "/clientes")
    assert "R$ 30.00" in _html(client_anonimo, "/relatorios")


def test_atualizar_banco_novo_nao_muda_nada():
    database.atualizar_banco()
    assert [b["nome"] for b in models.listar_barbearias()] == ["Barbearia Exemplo"]
    assert len(models.listar_clientes(BARBEARIA)) == 3
