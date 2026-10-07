"""
app.py

Aplicação Flask do Sistema de Gestão de Barbearia — rotas para
login, dashboard, clientes, atendimentos e relatórios financeiros.

Cada usuário pertence a uma barbearia e só vê os dados dela.

Segurança do login:
  - 5 senhas erradas seguidas bloqueiam o usuário por 15 minutos
  - a sessão expira depois de 30 minutos sem uso (SESSAO_INATIVIDADE_MINUTOS)

Papéis de acesso:
  dono     -> vê e faz tudo na própria barbearia
  barbeiro -> vê só os próprios atendimentos e comissões
"""

import functools
import math
import os
import secrets
import time

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

import database
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
# Minutos sem nenhuma requisição até a sessão expirar e pedir login de novo.
app.config["SESSAO_INATIVIDADE_MINUTOS"] = int(
    os.environ.get("SESSAO_INATIVIDADE_MINUTOS", "30")
)

csrf = CSRFProtect(app)


# ---------- AUTENTICAÇÃO ----------

def _sessao_expirada():
    """
    True se a sessão ficou parada mais que o limite. Sessão sem a hora do
    último acesso (criada antes desta regra) também conta como expirada.
    """
    ultimo_acesso = session.get("ultimo_acesso")
    limite = app.config["SESSAO_INATIVIDADE_MINUTOS"] * 60
    return ultimo_acesso is None or time.time() - ultimo_acesso > limite


@app.before_request
def carregar_usuario():
    """Coloca o usuário logado (ou None) em g.usuario, e a barbearia dele em g.barbearia."""
    usuario_id = session.get("usuario_id")
    if usuario_id is not None:
        if _sessao_expirada():
            session.clear()
            flash("Sua sessão expirou por inatividade. Entre de novo.")
            usuario_id = None
        else:
            session["ultimo_acesso"] = int(time.time())
    g.usuario = models.buscar_usuario(usuario_id) if usuario_id else None
    g.barbearia = (
        models.buscar_barbearia(g.usuario["barbearia_id"]) if g.usuario else None
    )


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


def barbearia_logada():
    """id da barbearia do usuário logado; todas as consultas filtram por ele."""
    return g.usuario["barbearia_id"]


def barbeiro_logado():
    """id do barbeiro se o usuário logado for barbeiro; None para o dono."""
    if g.usuario["papel"] == "barbeiro":
        return g.usuario["barbeiro_id"]
    return None


def _login_bloqueado(segundos):
    minutos = max(1, math.ceil(segundos / 60))
    flash(
        "Muitas tentativas com a senha errada. "
        f"Tente de novo em {minutos} minuto{'s' if minutos > 1 else ''}."
    )
    return render_template("login.html"), 429


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("usuario", "")
        # Bloqueado: recusa sem nem conferir a senha.
        espera = models.segundos_de_bloqueio(nome)
        if espera:
            return _login_bloqueado(espera)
        usuario = models.autenticar(nome, request.form.get("senha", ""))
        if usuario is None:
            if models.registrar_falha_de_login(nome):
                return _login_bloqueado(models.segundos_de_bloqueio(nome))
            flash("Usuário ou senha inválidos.")
            return render_template("login.html"), 401
        models.limpar_falhas_de_login(nome)
        session.clear()  # evita reaproveitar uma sessão anterior
        session["usuario_id"] = usuario["id"]
        session["ultimo_acesso"] = int(time.time())
        return redirect(url_for("dashboard"))
    if g.usuario is not None:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/senha", methods=["GET", "POST"])
@somente_dono
def trocar_senha():
    """Tela para o dono trocar a própria senha."""
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "")
        if nova_senha != request.form.get("confirmacao", ""):
            flash("A confirmação não é igual à nova senha.")
            return render_template("senha.html"), 400
        try:
            models.trocar_senha(
                g.usuario["id"], request.form.get("senha_atual", ""), nova_senha
            )
        except ValueError as erro:
            flash(str(erro))
            return render_template("senha.html"), 400
        flash("Senha alterada.")
        return redirect(url_for("dashboard"))
    return render_template("senha.html")


# ---------- PÁGINAS ----------

@app.route("/")
@login_obrigatorio
def dashboard():
    """
    Página inicial. O dono vê o resumo da barbearia inteira; o barbeiro
    vê só a própria comissão.
    """
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is not None:
        return render_template(
            "dashboard.html",
            comissoes=reports.comissoes_por_barbeiro(barbearia_id, barbeiro_id),
        )

    total = reports.faturamento_total(barbearia_id)
    comissoes = reports.comissoes_por_barbeiro(barbearia_id)
    servicos = reports.servicos_mais_vendidos(barbearia_id)
    return render_template(
        "dashboard.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


@app.route("/clientes")
@login_obrigatorio
def clientes():
    """Lista os clientes da barbearia."""
    lista = models.listar_clientes(barbearia_logada())
    return render_template("clientes.html", clientes=lista)


@app.route("/clientes/novo", methods=["POST"])
@login_obrigatorio
def novo_cliente():
    """Cadastra um novo cliente."""
    nome = request.form["nome"]
    telefone = request.form.get("telefone")
    models.criar_cliente(barbearia_logada(), nome, telefone)
    return redirect(url_for("clientes"))


@app.route("/atendimentos")
@login_obrigatorio
def atendimentos():
    """Lista os atendimentos (o barbeiro vê só os dele)."""
    barbearia_id = barbearia_logada()
    barbeiro_id = barbeiro_logado()
    lista = models.listar_atendimentos(barbearia_id, barbeiro_id)
    clientes = models.listar_clientes(barbearia_id)
    if barbeiro_id is not None:
        barbeiros = [models.buscar_barbeiro(barbearia_id, barbeiro_id)]
    else:
        barbeiros = models.listar_barbeiros(barbearia_id)
    servicos = models.listar_servicos(barbearia_id)
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
    """
    Registra um novo atendimento (o barbeiro só registra em seu nome).
    Cliente, barbeiro ou serviço de outra barbearia dá erro 400.
    """
    cliente_id = request.form["cliente_id"]
    barbeiro_id = barbeiro_logado()
    if barbeiro_id is None:
        barbeiro_id = request.form["barbeiro_id"]
    servico_id = request.form["servico_id"]
    valor_cobrado = request.form["valor_cobrado"]
    forma_pagamento = request.form.get("forma_pagamento", "dinheiro")

    try:
        models.criar_atendimento(
            barbearia_logada(), cliente_id, barbeiro_id, servico_id,
            valor_cobrado, forma_pagamento,
        )
    except ValueError:
        abort(400)
    return redirect(url_for("atendimentos"))


@app.route("/relatorios")
@somente_dono
def relatorios():
    """Exibe relatórios financeiros detalhados da barbearia."""
    barbearia_id = barbearia_logada()
    total = reports.faturamento_total(barbearia_id)
    comissoes = reports.comissoes_por_barbeiro(barbearia_id)
    servicos = reports.servicos_mais_vendidos(barbearia_id)
    return render_template(
        "relatorios.html",
        total=total,
        comissoes=comissoes,
        servicos=servicos,
    )


if __name__ == "__main__":
    database.atualizar_banco()  # banco antigo: separa os dados por barbearia
    app.run(debug=DEBUG)
