"""
test_comissao_gravada.py

O percentual de comissão é gravado em cada atendimento no momento do
registro: mudar a comissão do barbeiro depois não altera os atendimentos
antigos, só os novos.
"""

import pytest

import database
import models
import reports
from conftest import BARBEARIA, BARBEIRO_JOAO
from database import get_connection
from test_barbearias import banco_antigo  # noqa: F401 (fixture)

ELENILTON = 1


def _mudar_comissao(barbeiro_id, percentual):
    conn = get_connection()
    conn.execute(
        "UPDATE barbeiros SET comissao_percentual = ? WHERE id = ?",
        (percentual, barbeiro_id),
    )
    conn.commit()
    conn.close()


def _comissao_de(barbeiro_id):
    (linha,) = reports.comissoes_por_barbeiro(BARBEARIA, barbeiro_id)
    return linha


def test_atendimento_guarda_o_percentual_do_barbeiro():
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 35.00)
    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["comissao_percentual"] == 40.0


def test_mudar_comissao_nao_altera_atendimentos_antigos():
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 100.00)  # 40%
    _mudar_comissao(BARBEIRO_JOAO, 60.0)

    (atendimento,) = models.listar_atendimentos(BARBEARIA)
    assert atendimento["comissao_percentual"] == 40.0
    joao = _comissao_de(BARBEIRO_JOAO)
    assert joao["comissao_valor"] == pytest.approx(40.00)
    assert joao["comissao_percentual"] == 60.0  # o percentual atual


def test_atendimentos_novos_usam_a_comissao_nova():
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 100.00)  # 40%
    _mudar_comissao(BARBEIRO_JOAO, 60.0)
    models.criar_atendimento(BARBEARIA, 2, BARBEIRO_JOAO, 1, 50.00)  # 60%

    percentuais = sorted(
        a["comissao_percentual"] for a in models.listar_atendimentos(BARBEARIA)
    )
    assert percentuais == [40.0, 60.0]
    joao = _comissao_de(BARBEIRO_JOAO)
    assert joao["total_faturado"] == pytest.approx(150.00)
    assert joao["comissao_valor"] == pytest.approx(40.00 + 30.00)


def test_mudar_comissao_de_um_barbeiro_nao_afeta_outro():
    models.criar_atendimento(BARBEARIA, 1, ELENILTON, 1, 100.00)  # 50%
    models.criar_atendimento(BARBEARIA, 2, BARBEIRO_JOAO, 1, 100.00)  # 40%
    _mudar_comissao(ELENILTON, 10.0)
    models.criar_atendimento(BARBEARIA, 3, BARBEIRO_JOAO, 1, 100.00)  # 40%

    assert _comissao_de(ELENILTON)["comissao_valor"] == pytest.approx(50.00)
    assert _comissao_de(BARBEIRO_JOAO)["comissao_valor"] == pytest.approx(80.00)


def test_atendimento_de_barbeiro_de_outra_barbearia_nao_grava_nada(outra_barbearia):
    with pytest.raises(ValueError):
        models.criar_atendimento(BARBEARIA, 1, outra_barbearia.barbeiro_id, 1, 10.00)
    assert models.listar_atendimentos(BARBEARIA) == []


def test_tela_de_atendimentos_mostra_a_comissao_gravada(client):
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 100.00)  # 40%
    _mudar_comissao(BARBEIRO_JOAO, 60.0)

    html = client.get("/atendimentos").get_data(as_text=True)
    assert "40.0% (R$ 40.00)" in html


def test_relatorio_usa_a_comissao_gravada(client):
    models.criar_atendimento(BARBEARIA, 1, BARBEIRO_JOAO, 1, 100.00)  # 40%
    _mudar_comissao(BARBEIRO_JOAO, 60.0)

    html = client.get("/relatorios").get_data(as_text=True)
    assert "R$ 40.00" in html
    assert "R$ 60.00" not in html


# ---------- BANCO ANTIGO ----------

def test_banco_antigo_ganha_a_coluna_com_o_percentual_atual(banco_antigo):  # noqa: F811
    database.atualizar_banco()

    (barbearia,) = models.listar_barbearias()
    (atendimento,) = models.listar_atendimentos(barbearia["id"])
    assert atendimento["comissao_percentual"] == 50.0
    (linha,) = reports.comissoes_por_barbeiro(barbearia["id"])
    assert linha["comissao_valor"] == pytest.approx(15.00)


def test_atualizar_banco_de_novo_nao_sobrescreve_o_percentual(banco_antigo):  # noqa: F811
    database.atualizar_banco()
    (barbearia,) = models.listar_barbearias()
    _mudar_comissao(1, 80.0)
    database.atualizar_banco()

    (atendimento,) = models.listar_atendimentos(barbearia["id"])
    assert atendimento["comissao_percentual"] == 50.0
