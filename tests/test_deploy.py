"""
test_deploy.py

Testes da preparação para o deploy: escolha do banco pela DATABASE_URL,
tradução do SQL para o PostgreSQL, preparar_banco.py (cria as tabelas sem
apagar dados e cadastra o primeiro dono) e o render.yaml.
"""

import os
import sqlite3

import pytest

import database
import models
import preparar_banco
from conftest import BARBEARIA, BARBEIRO_JOAO, POSTGRES_DE_TESTE, somente_sqlite

RAIZ = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def banco_sem_tabelas(tmp_path, monkeypatch):
    """Banco novo, sem nenhuma tabela (como o Neon no primeiro deploy)."""
    if POSTGRES_DE_TESTE:
        conn = database.get_connection()
        conn.executescript(
            "DROP TABLE IF EXISTS tentativas_login, usuarios, atendimentos, "
            "clientes, servicos, barbeiros, barbearias CASCADE"
        )
        conn.commit()
        conn.close()
    else:
        monkeypatch.setenv("BARBEARIA_DB", str(tmp_path / "vazio.db"))
    for variavel in ("DONO_USUARIO", "DONO_SENHA", "BARBEARIA_NOME"):
        monkeypatch.delenv(variavel, raising=False)


# ---------- ESCOLHA DO BANCO ----------

@somente_sqlite
def test_sem_database_url_usa_o_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database.get_database_url() is None
    assert not database.usando_postgres()
    conn = database.get_connection()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


@pytest.mark.parametrize("url", [
    "postgresql://usuario:senha@ep-exemplo.neon.tech/neondb?sslmode=require",
    "postgres://usuario:senha@localhost/barbearia",
])
def test_database_url_postgres_e_aceita(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", f"  {url}  ")
    assert database.get_database_url() == url
    assert database.usando_postgres()


def test_database_url_vazia_usa_o_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    assert database.get_database_url() is None


def test_database_url_de_outro_banco_e_recusada(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://usuario@localhost/barbearia")
    with pytest.raises(RuntimeError, match="postgresql://"):
        database.get_database_url()


def test_testes_nunca_usam_a_database_url_de_producao():
    assert os.environ.get("DATABASE_URL") == POSTGRES_DE_TESTE


# ---------- TRADUÇÃO PARA O POSTGRESQL ----------

def test_traduz_o_schema_para_o_postgres():
    sql = database.para_postgres(
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "valor REAL NOT NULL, criado_em TEXT DEFAULT (datetime('now')))"
    )
    assert "SERIAL PRIMARY KEY" in sql
    assert "AUTOINCREMENT" not in sql
    assert "valor DOUBLE PRECISION NOT NULL" in sql
    assert "datetime" not in sql
    assert "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')" in sql


def test_traduz_os_parametros_e_protege_o_sinal_de_porcento():
    sql = database.para_postgres(
        "SELECT * FROM clientes WHERE nome LIKE '50%' AND id = ? AND barbearia_id = ?",
        com_parametros=True,
    )
    assert sql == (
        "SELECT * FROM clientes WHERE nome LIKE '50%%' AND id = %s AND barbearia_id = %s"
    )


def test_sem_parametros_o_sql_nao_muda():
    assert database.para_postgres("SELECT 1 WHERE 'a%' = ?") == "SELECT 1 WHERE 'a%' = ?"


def test_palavra_parecida_com_real_nao_e_traduzida():
    assert database.para_postgres("SELECT realizado FROM t") == "SELECT realizado FROM t"


def test_linha_funciona_como_a_sqlite3_row():
    linha = database.Linha(["id", "nome"], (7, "Carlos"))
    assert linha["nome"] == "Carlos"
    assert linha[0] == 7
    assert linha.keys() == ["id", "nome"]
    assert dict(linha) == {"id": 7, "nome": "Carlos"}
    assert tuple(linha) == (7, "Carlos")
    assert len(linha) == 2
    with pytest.raises(ValueError):
        linha["telefone"]


def test_postgres_sem_psycopg_da_erro_claro(monkeypatch):
    monkeypatch.setattr(database, "psycopg", None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/barbearia")
    with pytest.raises(RuntimeError, match="psycopg"):
        database.get_connection()


# ---------- DADOS VINDOS DO FORMULÁRIO ----------
# O PostgreSQL não compara id com texto nem grava texto em coluna de
# número, então o models converte antes (no SQLite isso passava calado).

def test_atendimento_com_id_que_nao_e_numero_e_recusado():
    with pytest.raises(ValueError, match="Cliente abc não existe"):
        models.criar_atendimento(BARBEARIA, "abc", BARBEIRO_JOAO, 1, 35.0)


def test_atendimento_aceita_valor_com_virgula():
    models.criar_atendimento(BARBEARIA, "1", str(BARBEIRO_JOAO), "1", "35,50")
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["valor_cobrado"] == pytest.approx(35.50)


@pytest.mark.parametrize("valor", ["", "abc", "-1"])
def test_atendimento_com_valor_invalido_e_recusado(valor):
    with pytest.raises(ValueError, match="valor cobrado"):
        models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, valor)
    assert models.listar_atendimentos(BARBEARIA) == []


def test_tela_recusa_valor_invalido(client):
    resposta = client.post("/atendimentos/novo", data={
        "cliente_id": "1", "barbeiro_id": "1", "servico_id": "1",
        "valor_cobrado": "trinta",
    })
    assert resposta.status_code == 400


def test_usuario_barbeiro_com_id_que_nao_e_numero_e_recusado():
    with pytest.raises(ValueError, match="Barbeiro xyz não existe"):
        models.criar_usuario(BARBEARIA, "novo", "senha-forte", "barbeiro", "xyz")


# ---------- PREPARAR O BANCO NO DEPLOY ----------

def test_preparar_banco_vazio_cria_as_tabelas_sem_dados_de_exemplo(banco_sem_tabelas):
    assert database.banco_vazio()
    assert database.preparar_banco() is True
    assert not database.banco_vazio()
    assert models.listar_barbearias() == []


def test_preparar_banco_de_novo_nao_apaga_nada(banco_sem_tabelas):
    database.preparar_banco()
    barbearia_id = models.criar_barbearia_com_dono("Navalha", "maria", "senha-da-maria")
    models.criar_cliente(barbearia_id, "Cliente Fiel")

    assert database.preparar_banco() is False
    assert [c["nome"] for c in models.listar_clientes(barbearia_id)] == ["Cliente Fiel"]
    assert models.autenticar("maria", "senha-da-maria") is not None


def test_preparar_banco_que_ja_tem_dados_nao_apaga_nada():
    assert database.preparar_banco() is False
    assert [b["nome"] for b in models.listar_barbearias()] == ["Barbearia Exemplo"]
    assert len(models.listar_clientes(BARBEARIA)) == 3
    assert models.autenticar("dono", "senha-do-dono") is not None


def test_script_cria_o_primeiro_dono(banco_sem_tabelas, monkeypatch, capsys):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    monkeypatch.setenv("BARBEARIA_NOME", "Barbearia do Elenilton")

    assert preparar_banco.main() == 0

    dono = models.autenticar("elenilton", "senha-do-elenilton")
    assert dono["papel"] == "dono"
    assert models.buscar_barbearia(dono["barbearia_id"])["nome"] == "Barbearia do Elenilton"
    assert "criada com o dono 'elenilton'" in capsys.readouterr().out


def test_script_usa_nome_padrao_da_barbearia(banco_sem_tabelas, monkeypatch):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    preparar_banco.main()
    assert [b["nome"] for b in models.listar_barbearias()] == ["Minha Barbearia"]


def test_script_roda_de_novo_sem_criar_outro_dono(banco_sem_tabelas, monkeypatch):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    preparar_banco.main()
    monkeypatch.setenv("DONO_USUARIO", "outro")
    monkeypatch.setenv("DONO_SENHA", "outra-senha-forte")

    assert preparar_banco.main() == 0
    assert len(models.listar_barbearias()) == 1
    assert models.autenticar("outro", "outra-senha-forte") is None


def test_script_sem_variaveis_avisa_como_criar_o_dono(banco_sem_tabelas, capsys):
    assert preparar_banco.main() == 0
    assert "DONO_USUARIO e DONO_SENHA" in capsys.readouterr().out
    assert models.listar_barbearias() == []


def test_script_com_senha_curta_falha_sem_criar_nada(banco_sem_tabelas, monkeypatch, capsys):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "curta")
    assert preparar_banco.main() == 1
    assert "pelo menos 8" in capsys.readouterr().out
    assert models.listar_barbearias() == []


def test_script_nao_mexe_no_banco_que_ja_tem_usuarios(monkeypatch):
    monkeypatch.setenv("DONO_USUARIO", "novo-dono")
    monkeypatch.setenv("DONO_SENHA", "senha-do-novo")
    assert preparar_banco.main() == 0
    assert models.autenticar("novo-dono", "senha-do-novo") is None
    assert len(models.listar_clientes(BARBEARIA)) == 3


# ---------- RENDER ----------

def _arquivo(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def test_render_yaml_usa_o_plano_free_com_gunicorn():
    render = _arquivo("render.yaml")
    assert "type: web" in render
    assert "runtime: python" in render
    assert "plan: free" in render
    assert "buildCommand: pip install -r requirements.txt" in render
    assert (
        "startCommand: python preparar_banco.py && gunicorn app:app --bind 0.0.0.0:$PORT"
        in render
    )


def test_render_yaml_nao_guarda_segredos():
    render = _arquivo("render.yaml")
    # SECRET_KEY gerada pelo Render; DATABASE_URL e senha pedidas no painel.
    assert "- key: SECRET_KEY\n        generateValue: true" in render
    for variavel in ("DATABASE_URL", "DONO_USUARIO", "DONO_SENHA"):
        assert f"- key: {variavel}\n        sync: false" in render
    assert "neon.tech" not in render


def test_requirements_tem_gunicorn_e_psycopg():
    requisitos = _arquivo("requirements.txt")
    assert "gunicorn==" in requisitos
    assert "psycopg[binary]==" in requisitos


def test_app_e_importavel_pelo_gunicorn():
    from app import app

    assert callable(app.wsgi_app)
