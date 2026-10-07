"""
app.py

Aplicação Flask do Sistema de Gestão de Barbearia — rotas para
login, dashboard, clientes, atendimentos e relatórios financeiros.

Papéis de acesso:
  dono     -> vê e faz tudo
  barbeiro -> vê só os próprios atendimentos e comissões
"""

import functools
import os
import secrets

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect

import models
import reports

DEBUG = os.environ.get("FLASK_DEBUG") == "1"

app = Flask(__name__)

# A SECRET_KEY assina a sessão e os tokens CSRF. Em produção ela é
# obrigatória; só no modo debug usamos uma chave aleatória temporária.
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if not DEBUG:
        raise RuntimeError(
            "Defina a variável de ambiente SECRET_KEY "
            "(ou FLASK_DEBUG=1 para desenvolvimento local)."
        )
    _secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = _secret_key
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

csrf = CSRFProtect(app)


# ---------- AUTENTICAÇÃO ----------

@app.before_request
def carregar_usuario():
    """Coloca o usuário logado (ou None) em g.usuario."""
    usuario_id = session.get("usuario_id")
    g.usuario = models.buscar_usuario(usuario_id) if usuario_id else None


def login_obrigatorio(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def somente_dono(view):
    @functools.wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if g.usuario["papel"] != "dono":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def barbeiro_logado():
    """id do barbeiro se o usuário logado for barbeiro; None para o dono."""
    if g.usuario["papel"] == "barbeiro":
        return g.usuario["barbeiro_id"]
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = models.autenticar(
            request.form.get("usuario", ""), request.form.get("senha", "")
        )
        if usuario is None:
            flash("Usuário ou senha inválidos.")
            return render_template("login.html"), 401
        session.clear()  # evita reaproveitar uma sessão anterior
        session["usuario_id"] = usuario["id"]
        return redirect(url_for("dashboard"))
    if g.usuario is not None:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- PÁGINAS ----------

@app.route("/")
@login_obrigatorio
def dashboard():
    """
    Página inicial. O dono vê o resumo da barbearia inteira; o barbeiro
    vê só a própria comissão.
    """
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is not None:
        return render_template(
            "dashboard.html",
            comissoes=reports.comissoes_por_barbeiro(barbeiro_id),
        )

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
@login_obrigatorio
def clientes():
    """Lista todos os clientes cadastrados."""
    lista = models.listar_clientes()
    return render_template("clientes.html", clientes=lista)


@app.route("/clientes/novo", methods=["POST"])
@login_obrigatorio
def novo_cliente():
    """Cadastra um novo cliente."""
    nome = request.form["nome"]
    telefone = request.form.get("telefone")
    models.criar_cliente(nome, telefone)
    return redirect(url_for("clientes"))


@app.route("/atendimentos")
@login_obrigatorio
def atendimentos():
    """Lista os atendimentos (o barbeiro vê só os dele)."""
    barbeiro_id = barbeiro_logado()
    lista = models.listar_atendimentos(barbeiro_id)
    clientes = models.listar_clientes()
    if barbeiro_id is not None:
        barbeiros = [models.buscar_barbeiro(barbeiro_id)]
    else:
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
@login_obrigatorio
def novo_atendimento():
    """Registra um novo atendimento (o barbeiro só registra em seu nome)."""
    cliente_id = request.form["cliente_id"]
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.form["barbeiro_id"]
    servico_id = request.form["servico_id"]
    valor_cobrado = request.form["valor_cobrado"]
    forma_pagamento = request.form.get("forma_pagamento", "dinheiro")

    models.criar_atendimento(
        cliente_id, barbeiro_id, servico_id, valor_cobrado, forma_pagamento
    )
    return redirect(url_for("atendimentos"))


@app.route("/relatorios")
@somente_dono
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
    app.run(debug=DEBUG)
