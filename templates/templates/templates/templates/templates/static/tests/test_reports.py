"""
test_reports.py

Testes automatizados para os cálculos de relatórios financeiros
do Sistema de Gestão de Barbearia.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import reports


def test_faturamento_total_retorna_numero():
    """O faturamento total deve ser um número (int ou float)."""
    total = reports.faturamento_total()
    assert isinstance(total, (int, float))


def test_comissoes_por_barbeiro_retorna_lista():
    """As comissões por barbeiro devem retornar uma lista de dicionários."""
    comissoes = reports.comissoes_por_barbeiro()
    assert isinstance(comissoes, list)
    if comissoes:
        assert "barbeiro" in comissoes[0]
        assert "comissao_valor" in comissoes[0]


def test_comissao_calculada_corretamente():
    """A comissão deve ser o percentual correto sobre o total faturado."""
    comissoes = reports.comissoes_por_barbeiro()
    for c in comissoes:
        esperado = round(c["total_faturado"] * (c["comissao_percentual"] / 100), 2)
        assert c["comissao_valor"] == esperado


def test_servicos_mais_vendidos_retorna_resultado():
    """A lista de serviços mais vendidos deve ser retornada sem erros."""
    servicos = reports.servicos_mais_vendidos()
    assert servicos is not None


if __name__ == "__main__":
    test_faturamento_total_retorna_numero()
    test_comissoes_por_barbeiro_retorna_lista()
    test_comissao_calculada_corretamente()
    test_servicos_mais_vendidos_retorna_resultado()
    print("Todos os testes passaram com sucesso!")
