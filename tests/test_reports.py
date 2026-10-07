"""
test_reports.py

Testes automatizados para os cálculos de relatórios financeiros
do Sistema de Gestão de Barbearia.
"""

import pytest

import models
import reports
from conftest import BARBEARIA


def _comissao_de(nome):
    return next(c for c in reports.comissoes_por_barbeiro(BARBEARIA) if c["barbeiro"] == nome)


def test_faturamento_total_sem_atendimentos_e_zero():
    assert reports.faturamento_total(BARBEARIA) == 0


def test_faturamento_total_soma_atendimentos():
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00, "pix")
    models.criar_atendimento(BARBEARIA, 2, 2, 3, 55.00, "cartao")
    models.criar_atendimento(BARBEARIA, 3, 1, 2, 25.50)
    assert reports.faturamento_total(BARBEARIA) == pytest.approx(115.50)


def test_comissoes_listam_todos_os_barbeiros_mesmo_sem_atendimento():
    comissoes = reports.comissoes_por_barbeiro(BARBEARIA)
    assert {c["barbeiro"] for c in comissoes} == {"Elenilton Silveira", "João Pereira"}
    for c in comissoes:
        assert c["total_faturado"] == 0
        assert c["comissao_valor"] == 0


def test_comissao_calculada_pelo_percentual_de_cada_barbeiro():
    # Elenilton (id 1) tem 50%; João (id 2) tem 40%
    models.criar_atendimento(BARBEARIA, 1, 1, 1, 35.00)
    models.criar_atendimento(BARBEARIA, 2, 1, 3, 55.00)
    models.criar_atendimento(BARBEARIA, 3, 2, 2, 25.00)

    elenilton = _comissao_de("Elenilton Silveira")
    joao = _comissao_de("João Pereira")

    assert elenilton["total_faturado"] == pytest.approx(90.00)
    assert elenilton["comissao_valor"] == pytest.approx(45.00)
    assert joao["total_faturado"] == pytest.approx(25.00)
    assert joao["comissao_valor"] == pytest.approx(10.00)


def test_comissao_arredondada_em_duas_casas():
    models.criar_atendimento(BARBEARIA, 1, 2, 1, 33.33)  # 40% de 33,33 = 13,332
    assert _comissao_de("João Pereira")["comissao_valor"] == 13.33


def test_comissoes_ordenadas_por_faturamento():
    models.criar_atendimento(BARBEARIA, 1, 2, 3, 55.00)
    comissoes = reports.comissoes_por_barbeiro(BARBEARIA)
    assert comissoes[0]["barbeiro"] == "João Pereira"


def test_servicos_mais_vendidos_ordenados_por_quantidade():
    models.criar_atendimento(BARBEARIA, 1, 1, 2, 25.00)  # Barba
    models.criar_atendimento(BARBEARIA, 2, 1, 2, 25.00)  # Barba
    models.criar_atendimento(BARBEARIA, 3, 2, 1, 35.00)  # Corte Masculino

    servicos = reports.servicos_mais_vendidos(BARBEARIA)
    assert len(servicos) == 5  # todos os serviços aparecem, mesmo sem venda
    assert servicos[0]["servico"] == "Barba"
    assert servicos[0]["quantidade"] == 2
    assert servicos[0]["total_faturado"] == pytest.approx(50.00)
    assert servicos[1]["servico"] == "Corte Masculino"
    assert servicos[1]["quantidade"] == 1
