"""
reports.py

Cálculos de relatórios financeiros do Sistema de Gestão de Barbearia:
faturamento total, comissões por barbeiro e serviços mais vendidos.

Todos os relatórios são de uma barbearia só (o barbearia_id é o
primeiro argumento de cada função).
"""

from database import get_connection


def faturamento_total(barbearia_id):
    """Retorna o faturamento total dos atendimentos da barbearia."""
    conn = get_connection()
    resultado = conn.execute(
        """
        SELECT COALESCE(SUM(valor_cobrado), 0) AS total
        FROM atendimentos
        WHERE barbearia_id = ?
        """,
        (barbearia_id,),
    ).fetchone()
    conn.close()
    return resultado["total"]


def comissoes_por_barbeiro(barbearia_id, barbeiro_id=None):
    """
    Calcula o total faturado e a comissão devida a cada barbeiro da
    barbearia. A comissão de cada atendimento usa o percentual gravado
    nele no momento do registro; comissao_percentual é o percentual atual
    do barbeiro. Com barbeiro_id, retorna só a linha daquele barbeiro.
    """
    filtro = ""
    parametros = (barbearia_id,)
    if barbeiro_id is not None:
        filtro = "AND barbeiros.id = ?"
        parametros = (barbearia_id, barbeiro_id)

    conn = get_connection()
    resultado = conn.execute(
        f"""
        SELECT
            barbeiros.id AS barbeiro_id,
            barbeiros.nome AS barbeiro,
            barbeiros.comissao_percentual,
            COALESCE(SUM(atendimentos.valor_cobrado), 0) AS total_faturado,
            COALESCE(SUM(
                atendimentos.valor_cobrado * atendimentos.comissao_percentual / 100
            ), 0) AS comissao_valor
        FROM barbeiros
        LEFT JOIN atendimentos
            ON atendimentos.barbeiro_id = barbeiros.id
            AND atendimentos.barbearia_id = barbeiros.barbearia_id
        WHERE barbeiros.barbearia_id = ? {filtro}
        GROUP BY barbeiros.id
        ORDER BY total_faturado DESC
        """,
        parametros,
    ).fetchall()
    conn.close()

    relatorio = []
    for linha in resultado:
        relatorio.append({
            "barbeiro_id": linha["barbeiro_id"],
            "barbeiro": linha["barbeiro"],
            "total_faturado": linha["total_faturado"],
            "comissao_percentual": linha["comissao_percentual"],
            "comissao_valor": round(linha["comissao_valor"], 2),
        })
    return relatorio


def servicos_mais_vendidos(barbearia_id):
    """Retorna os serviços da barbearia ordenados pela quantidade vendida."""
    conn = get_connection()
    resultado = conn.execute(
        """
        SELECT
            servicos.nome AS servico,
            COUNT(atendimentos.id) AS quantidade,
            COALESCE(SUM(atendimentos.valor_cobrado), 0) AS total_faturado
        FROM servicos
        LEFT JOIN atendimentos
            ON atendimentos.servico_id = servicos.id
            AND atendimentos.barbearia_id = servicos.barbearia_id
        WHERE servicos.barbearia_id = ?
        GROUP BY servicos.id
        ORDER BY quantidade DESC
        """,
        (barbearia_id,),
    ).fetchall()
    conn.close()
    return resultado
