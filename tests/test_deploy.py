"""
test_deploy.py

Deploy gratuito no Render com o banco no Neon: o render.yaml (site no
plano Free, DATABASE_URL do Neon informada no painel), o preparar_banco.py
(cria as tabelas sem apagar nada e o primeiro dono, uma vez só) e os ids
e valores do formulário convertidos antes de gravar (o PostgreSQL não
aceita texto onde espera número).

O resto da preparação para produção fica em test_producao.py.
"""

import os

import pytest

import database
import models
import preparar_banco
from conftest import BARBEARIA, BARBEIRO_JOAO

RAIZ = os.path.join(os.path.dirname(__file__), "..")


def _arquivo(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def banco_sem_tabelas(monkeypatch):
    """Banco sem nenhuma tabela, como o Neon no primeiro deploy."""
    conn = database.get_connection()
    for tabela in ("tentativas_login", "usuarios", "atendimentos", "clientes",
                   "servicos", "barbeiros", "barbearias"):
        conn.execute(f"DROP TABLE IF EXISTS {tabela}")
    conn.commit()
    conn.close()
    for variavel in ("DONO_USUARIO", "DONO_SENHA", "BARBEARIA_NOME"):
        monkeypatch.delenv(variavel, raising=False)


# ---------- RENDER + NEON ----------

def test_render_yaml_cria_o_site_no_plano_free_sem_banco_do_render():
    render = _arquivo("render.yaml")
    assert "type: web" in render
    assert "runtime: docker" in render
    assert "plan: free" in render
    # O banco é o do Neon: nada de PostgreSQL do Render (que expira).
    assert "databases:" not in render
    assert "fromDatabase" not in render


def test_render_yaml_pede_a_database_url_do_neon_no_painel():
    render = _arquivo("render.yaml")
    assert "- key: DATABASE_URL\n        sync: false" in render
    for variavel in ("DONO_USUARIO", "DONO_SENHA", "BARBEARIA_NOME"):
        assert f"- key: {variavel}\n        sync: false" in render
    assert "- key: SECRET_KEY\n        generateValue: true" in render
    assert "neon.tech" not in render  # nenhuma senha no repositório


def test_dockerfile_prepara_o_banco_e_sobe_o_gunicorn():
    dockerfile = _arquivo("Dockerfile")
    assert "python preparar_banco.py && exec gunicorn app:app" in dockerfile


def test_connection_string_do_neon_usa_o_postgres(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        " postgresql://neondb_owner:senha@ep-exemplo-pooler.sa-east-1.aws.neon.tech"
        "/neondb?sslmode=require ",
    )
    assert database.usando_postgres()
    assert database.get_database_url().endswith("/neondb?sslmode=require")


# ---------- PREPARAR O BANCO NO DEPLOY ----------

def test_script_cria_as_tabelas_e_o_primeiro_dono(banco_sem_tabelas, monkeypatch, capsys):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    monkeypatch.setenv("BARBEARIA_NOME", "Barbearia do Elenilton")

    assert preparar_banco.main() == 0

    dono = models.autenticar("elenilton", "senha-do-elenilton")
    assert dono["papel"] == "dono"
    assert models.buscar_barbearia(dono["barbearia_id"])["nome"] == "Barbearia do Elenilton"
    saida = capsys.readouterr().out
    assert "Banco de dados pronto" in saida
    assert "criada com o dono 'elenilton'" in saida


def test_script_usa_nome_padrao_da_barbearia(banco_sem_tabelas, monkeypatch):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    preparar_banco.main()
    assert [b["nome"] for b in models.listar_barbearias()] == ["Minha Barbearia"]


def test_script_roda_de_novo_sem_apagar_nem_criar_outro_dono(banco_sem_tabelas, monkeypatch):
    monkeypatch.setenv("DONO_USUARIO", "elenilton")
    monkeypatch.setenv("DONO_SENHA", "senha-do-elenilton")
    preparar_banco.main()
    (barbearia,) = models.listar_barbearias()
    models.criar_cliente(barbearia["id"], "Cliente Fiel")
    monkeypatch.setenv("DONO_USUARIO", "outro")
    monkeypatch.setenv("DONO_SENHA", "outra-senha-forte")

    assert preparar_banco.main() == 0  # o próximo deploy
    assert len(models.listar_barbearias()) == 1
    assert models.autenticar("outro", "outra-senha-forte") is None
    assert [c["nome"] for c in models.listar_clientes(barbearia["id"])] == ["Cliente Fiel"]


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


# ---------- DADOS VINDOS DO FORMULÁRIO ----------
# O PostgreSQL não compara id com texto nem grava texto em coluna de
# número (dá erro 500), então o models converte antes. No SQLite isso
# passava calado: "35,50" era gravado como texto.

def test_atendimento_com_id_que_nao_e_numero_e_recusado():
    with pytest.raises(ValueError, match="Cliente abc não existe"):
        models.criar_atendimento(BARBEARIA, "abc", BARBEIRO_JOAO, 1, 35.0)


def test_atendimento_aceita_ids_em_texto_e_valor_com_virgula():
    models.criar_atendimento(BARBEARIA, "1", str(BARBEIRO_JOAO), "1", "35,50")
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["valor_cobrado"] == pytest.approx(35.50)


@pytest.mark.parametrize("valor", ["", "abc", "-1"])
def test_atendimento_com_valor_invalido_e_recusado(valor):
    with pytest.raises(ValueError, match="valor cobrado"):
        models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, valor)
    assert models.listar_atendimentos(BARBEARIA) == []


@pytest.mark.parametrize("campo, valor", [
    ("valor_cobrado", "trinta"),
    ("cliente_id", "abc"),
])
def test_tela_recusa_atendimento_invalido(client, campo, valor):
    dados = {"cliente_id": "1", "barbeiro_id": "1", "servico_id": "1",
             "valor_cobrado": "35"}
    dados[campo] = valor
    assert client.post("/atendimentos/novo", data=dados).status_code == 400


def test_usuario_barbeiro_com_id_que_nao_e_numero_e_recusado():
    with pytest.raises(ValueError, match="Barbeiro xyz não existe"):
        models.criar_usuario(BARBEARIA, "novo", "senha-forte", "barbeiro", "xyz")
