"""
reports.py

Cálculos de relatórios financeiros do Sistema de Gestão de Barbearia:
faturamento total, comissões por barbeiro e serviços mais vendidos.
"""

from database import get_connection


def faturamento_total():
    """Retorna o faturamento total de todos os atendimentos registrados."""
    conn = get_connection()
    resultado = conn.execute(
        "SELECT COALESCE(SUM(valor_cobrado), 0) AS total FROM atendimentos"
    ).fetchone()
    conn.close()
    return resultado["total"]


def comissoes_por_barbeiro(barbeiro_id=None):
    """
    Calcula o total faturado e a comissão devida a cada barbeiro,
    com base no percentual de comissão configurado. Com barbeiro_id,
    retorna só a linha daquele barbeiro.
    """
    filtro = ""
    parametros = ()
    if barbeiro_id is not None:
        filtro = "WHERE barbeiros.id = ?"
        parametros = (barbeiro_id,)

    conn = get_connection()
    resultado = conn.execute(
        f"""
        SELECT
            barbeiros.id AS barbeiro_id,
            barbeiros.nome AS barbeiro,
            barbeiros.comissao_percentual,
            COALESCE(SUM(atendimentos.valor_cobrado), 0) AS total_faturado
        FROM barbeiros
        LEFT JOIN atendimentos ON atendimentos.barbeiro_id = barbeiros.id
        {filtro}
        GROUP BY barbeiros.id
        ORDER BY total_faturado DESC
        """,
        parametros,
    ).fetchall()
    conn.close()

    relatorio = []
    for linha in resultado:
        comissao = linha["total_faturado"] * (linha["comissao_percentual"] / 100)
        relatorio.append({
            "barbeiro_id": linha["barbeiro_id"],
            "barbeiro": linha["barbeiro"],
            "total_faturado": linha["total_faturado"],
            "comissao_percentual": linha["comissao_percentual"],
            "comissao_valor": round(comissao, 2),
        })
    return relatorio


def servicos_mais_vendidos():
    """Retorna os serviços ordenados pela quantidade de vezes vendidos."""
    conn = get_connection()
    resultado = conn.execute(
        """
        SELECT
            servicos.nome AS servico,
            COUNT(atendimentos.id) AS quantidade,
            COALESCE(SUM(atendimentos.valor_cobrado), 0) AS total_faturado
        FROM servicos
        LEFT JOIN atendimentos ON atendimentos.servico_id = servicos.id
        GROUP BY servicos.id
        ORDER BY quantidade DESC
        """
    ).fetchall()
    conn.close()
    return resultado
