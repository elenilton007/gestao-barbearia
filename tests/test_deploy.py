"""
test_deploy.py

Deploy gratuito (Render + Neon): o render.yaml usa o plano gratuito e o
banco do Neon pela DATABASE_URL, sem guardar segredos, e os valores do
atendimento são conferidos antes de gravar (no PostgreSQL, um texto
inválido daria erro 500 em vez de 400).

Rodam no SQLite e, com TEST_DATABASE_URL, também no PostgreSQL.
"""

import os

import pytest

import models
from conftest import BARBEARIA, BARBEIRO_JOAO

RAIZ = os.path.join(os.path.dirname(__file__), "..")


# ---------- VALORES DO ATENDIMENTO ----------

@pytest.mark.parametrize(
    "cliente_id, valor", [("abc", "35"), ("", "35"), ("1", "caro"), ("1", "-5")]
)
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


def test_tela_recusa_atendimento_com_valor_invalido(client):
    resposta = client.post(
        "/atendimentos/novo",
        data={"cliente_id": "1", "barbeiro_id": "2", "servico_id": "1",
              "valor_cobrado": "trinta"},
    )
    assert resposta.status_code == 400
    assert models.listar_atendimentos(BARBEARIA) == []


def test_usuario_barbeiro_com_barbeiro_id_invalido_e_recusado():
    with pytest.raises(ValueError, match="não existe"):
        models.criar_usuario(BARBEARIA, "novo", "senha-forte", "barbeiro", "abc")


# ---------- RENDER + NEON ----------

def _render_yaml():
    with open(os.path.join(RAIZ, "render.yaml"), encoding="utf-8") as arquivo:
        return arquivo.read()


def test_render_yaml_usa_o_plano_gratuito_com_o_dockerfile():
    texto = _render_yaml()
    assert "plan: free" in texto
    assert "runtime: docker" in texto
    assert "healthCheckPath: /login" in texto


def test_render_yaml_usa_o_banco_do_neon_e_nao_o_do_render():
    texto = _render_yaml()
    # O banco gratuito do Render expira; o do Neon entra pela DATABASE_URL.
    assert "databases:" not in texto
    assert "fromDatabase" not in texto
    assert "key: DATABASE_URL\n        sync: false" in texto


def test_render_yaml_nao_guarda_segredos():
    texto = _render_yaml()
    assert "key: SECRET_KEY\n        generateValue: true" in texto
    assert "key: COOKIE_SEGURO\n        value: \"1\"" in texto
    assert "postgresql://" not in texto


def test_dockerfile_prepara_o_banco_e_sobe_o_gunicorn():
    with open(os.path.join(RAIZ, "Dockerfile"), encoding="utf-8") as arquivo:
        texto = arquivo.read()
    assert "python database.py --preparar && exec gunicorn app:app" in texto
    assert "${PORT}" in texto
