"""
test_deploy.py

Preparação para o deploy gratuito (Render + Neon): o banco escolhido pela
DATABASE_URL, a tradução do SQL para o PostgreSQL, o preparar_banco (que
roda a cada vez que o servidor sobe e nunca apaga dados), a validação dos
valores do atendimento e o render.yaml.

Rodam no SQLite e, com TEST_DATABASE_URL, também no PostgreSQL.
"""

import os
import subprocess
import sys

import pytest

import database
import models
from conftest import BARBEARIA, BARBEIRO_JOAO
from database import get_connection
from test_barbearias import banco_antigo  # noqa: F401 (fixture)
from test_security import reimportar_app  # noqa: F401 (fixture)

RAIZ = os.path.join(os.path.dirname(__file__), "..")

TABELAS = (
    "tentativas_login", "usuarios", "atendimentos",
    "clientes", "servicos", "barbeiros", "barbearias",
)


def _banco_vazio():
    conn = get_connection()
    for tabela in TABELAS:
        conn.execute(f"DROP TABLE IF EXISTS {tabela}")
    conn.commit()
    conn.close()


# ---------- QUAL BANCO ----------

def test_sem_database_url_usa_o_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not database.usando_postgres()
    conn = get_connection()
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    conn.close()


def test_com_database_url_usa_o_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://usuario:senha@host/banco")
    assert database.usando_postgres()
    assert database.get_database_url() == "postgresql://usuario:senha@host/banco"


def test_database_url_vazia_usa_o_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    assert not database.usando_postgres()


# ---------- TRADUÇÃO PARA O POSTGRESQL ----------

def test_traduz_o_schema_para_o_postgres():
    sql = database._sql_postgres(
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, preco REAL NOT NULL, "
        "criado_em TEXT DEFAULT (datetime('now')))",
        com_parametros=False,
    )
    assert "SERIAL PRIMARY KEY" in sql
    assert "preco DOUBLE PRECISION NOT NULL" in sql
    assert "AUTOINCREMENT" not in sql
    assert "datetime" not in sql


def test_traduz_os_parametros_e_protege_o_porcento():
    sql = database._sql_postgres(
        "SELECT * FROM t WHERE a = ? AND b LIKE '10%' AND c = ?", com_parametros=True
    )
    assert sql == "SELECT * FROM t WHERE a = %s AND b LIKE '10%%' AND c = %s"


def test_sem_parametros_o_porcento_fica_como_esta():
    assert database._sql_postgres("SELECT '10%'", com_parametros=False) == "SELECT '10%'"


def test_linha_do_postgres_funciona_como_a_do_sqlite():
    linha = database.Linha([("id", 7), ("nome", "Ana")])
    assert linha["nome"] == "Ana"
    assert linha[0] == 7
    assert linha[1] == "Ana"
    assert list(linha.keys()) == ["id", "nome"]


# ---------- PREPARAR O BANCO (DEPLOY) ----------

def test_preparar_banco_vazio_cria_as_tabelas_sem_dados_de_exemplo():
    _banco_vazio()
    database.preparar_banco()

    assert models.listar_barbearias() == []
    barbearia_id = models.criar_barbearia_com_dono("Barbearia Nova", "maria", "senha-forte")
    assert models.autenticar("maria", "senha-forte")["barbearia_id"] == barbearia_id
    assert models.listar_clientes(barbearia_id) == []


def test_preparar_banco_de_novo_nao_apaga_nada():
    models.criar_cliente(BARBEARIA, "Cliente Que Fica")
    database.preparar_banco()
    database.preparar_banco()

    assert "Cliente Que Fica" in {c["nome"] for c in models.listar_clientes(BARBEARIA)}
    assert models.autenticar("dono", "senha-do-dono") is not None


def test_preparar_banco_atualiza_banco_antigo_sem_perder_dados(banco_antigo):  # noqa: F811
    database.preparar_banco()

    (barbearia,) = models.listar_barbearias()
    assert [c["nome"] for c in models.listar_clientes(barbearia["id"])] == ["Cliente Antigo"]
    assert models.autenticar("antigo", "senha-antiga") is not None


def test_comando_preparar_pela_linha_de_comando():
    resultado = subprocess.run(
        [sys.executable, "database.py", "--preparar"],
        cwd=RAIZ, env=os.environ.copy(), capture_output=True, text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "Banco de dados pronto." in resultado.stdout
    # Banco que já tinha dados: continua com eles.
    assert models.autenticar("dono", "senha-do-dono") is not None


def test_ids_e_valores_gravados_com_o_tipo_certo():
    barbearia_id = models.criar_barbearia_com_dono("Outra", "dona", "senha-forte")
    barbeiro_id = models.criar_barbeiro(barbearia_id, "Novo", "35,5")
    servico_id = models.criar_servico(barbearia_id, "Corte", "123.45", "40")
    assert isinstance(barbearia_id, int)
    assert isinstance(barbeiro_id, int)
    barbeiro = models.buscar_barbeiro(barbearia_id, barbeiro_id)
    assert barbeiro["comissao_percentual"] == 35.5
    assert models.buscar_servico(barbearia_id, servico_id)["preco"] == 123.45


# ---------- VALORES DO ATENDIMENTO ----------

@pytest.mark.parametrize("cliente_id, valor", [("abc", "35"), ("", "35"), ("1", "caro"), ("1", "-5")])
def test_atendimento_com_valor_invalido_e_recusado(cliente_id, valor):
    with pytest.raises(ValueError):
        models.criar_atendimento(BARBEARIA, cliente_id, BARBEIRO_JOAO, 1, valor)
    assert models.listar_atendimentos(BARBEARIA) == []


def test_atendimento_aceita_texto_do_formulario_com_virgula():
    models.criar_atendimento(BARBEARIA, "1", str(BARBEIRO_JOAO), "1", "35,50")
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["valor_cobrado"] == 35.50
    assert atendimento["comissao_percentual"] == 40.0


def test_tela_recusa_atendimento_com_id_invalido(client):
    resposta = client.post(
        "/atendimentos/novo",
        data={"cliente_id": "abc", "barbeiro_id": "2", "servico_id": "1",
              "valor_cobrado": "35"},
    )
    assert resposta.status_code == 400


def test_usuario_barbeiro_com_barbeiro_id_invalido_e_recusado():
    with pytest.raises(ValueError, match="não existe"):
        models.criar_usuario(BARBEARIA, "novo", "senha-forte", "barbeiro", "abc")


# ---------- RENDER ----------

def _render_yaml():
    with open(os.path.join(RAIZ, "render.yaml"), encoding="utf-8") as arquivo:
        return arquivo.read()


def test_render_yaml_usa_o_plano_gratuito_e_o_gunicorn():
    texto = _render_yaml()
    assert "plan: free" in texto
    assert "python database.py --preparar && gunicorn app:app" in texto
    assert "--bind 0.0.0.0:$PORT" in texto


def test_render_yaml_nao_guarda_segredos():
    texto = _render_yaml()
    assert "key: DATABASE_URL\n        sync: false" in texto
    assert "key: SECRET_KEY\n        generateValue: true" in texto
    assert "postgresql://" not in texto


def test_dependencias_de_producao():
    with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as arquivo:
        texto = arquivo.read()
    assert "gunicorn==" in texto
    assert "psycopg[binary]==" in texto


def test_cookie_seguro_ligado_pela_variavel(monkeypatch, reimportar_app):  # noqa: F811
    monkeypatch.setenv("SESSAO_COOKIE_SEGURO", "1")
    assert reimportar_app().app.config["SESSION_COOKIE_SECURE"] is True


def test_cookie_seguro_desligado_por_padrao(monkeypatch, reimportar_app):  # noqa: F811
    monkeypatch.delenv("SESSAO_COOKIE_SEGURO", raising=False)
    assert reimportar_app().app.config["SESSION_COOKIE_SECURE"] is False
