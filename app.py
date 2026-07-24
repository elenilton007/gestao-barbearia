"""
app.py

Aplicação Flask do Sistema de Gestão de Barbearia — rotas para
dashboard, clientes, atendimentos e relatórios financeiros.
"""

from flask import Flask, render_template, request, redirect, url_for
import models
import reports

app = Flask(__name__)


@app.route("/")
def dashboard():
    """Página inicial com resumo do faturamento e comissões."""
    total = reports.faturamento_total()
    comissoes = reports.comissoes_por_barbeiro()
    servicos = reports.servicos_mais_vendidos()
    return render_template(
        "dashboard.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


@app.route("/clientes")
def clientes():
    """Lista todos os clientes cadastrados."""
    lista = models.listar_clientes()
    return render_template("clientes.html", clientes=lista)


@app.route("/clientes/novo", methods=["POST"])
def novo_cliente():
    """Cadastra um novo cliente."""
    nome = request.form["nome"]
    telefone = request.form.get("telefone")
    models.criar_cliente(nome, telefone)
    return redirect(url_for("clientes"))


@app.route("/atendimentos")
def atendimentos():
    """Lista todos os atendimentos registrados."""
    lista = models.listar_atendimentos()
    clientes = models.listar_clientes()
    barbeiros = models.listar_barbeiros()
    servicos = models.listar_servicos()
    return render_template(
        "atendimentos.html",
        atendimentos=lista,
        clientes=clientes,
        barbeiros=barbeiros,
        servicos=servicos,
    )


@app.route("/atendimentos/novo", methods=["POST"])
def novo_atendimento():
    """Registra um novo atendimento."""
    cliente_id = request.form["cliente_id"]
    barbeiro_id = request.form["barbeiro_id"]
    servico_id = request.form["servico_id"]
    valor_cobrado = request.form["valor_cobrado"]
    forma_pagamento = request.form.get("forma_pagamento", "dinheiro")

    models.criar_atendimento(
        cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento
    )
    return redirect(url_for("atendimentos"))


@app.route("/relatorios")
def relatorios():
    """Exibe relatórios financeiros detalhados."""
    total = reports.faturamento_total()
    comissoes = reports.comissoes_por_barbeiro()
    servicos = reports.servicos_mais_vendidos()
    return render_template(
        "relatorios.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


if __name__ == "__main__":
    app.run(debug=True)
